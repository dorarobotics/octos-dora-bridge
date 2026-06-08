#!/usr/bin/env python3
"""Offline MuJoCo IK: solve arm joint configs that place the gripper pinch site at
given world targets, pointing straight down. Prints joint configs + FK check.

Run on epyc (needs mujoco + the ur5e model). Used to precompute the pick-and-place
joint waypoints, since the dora-moveit2 Cartesian move_to_pose IK is unreliable.

Arm qpos slice = qpos[7:13]; arm qvel slice = qvel[6:12] (ball freejoint = 6 dof).
"""
from __future__ import annotations

import json
import os

import mujoco
import numpy as np

ARM_QPOS = slice(7, 13)
ARM_QVEL = slice(6, 12)
HOME = np.array([-1.5708, -1.5708, 1.5708, -1.5708, -1.5708, 0.0])

# (name, world xyz the pinch site should reach)
# Pinch-site world targets. at_ball/at_place sit at ~ball-center height (ball
# center rests at z=0.028, r=0.028) so the 2F-85 pads straddle the sphere.
BALL_XY = (0.35, 0.0)
# Place on the green target marker (site place_target at 0.25,0 — radial, in front
# of the base on the pick heading). Radial carry = no base-pan rotation, so the
# gripper stays level and the grasp holds reliably the whole way onto the plate.
PLACE_XY = (0.25, 0.0)
CARRY_Z = 0.22
N_CARRY = 3  # down-pointing waypoints along the (short, radial) carry

# The live arm undershoots shoulder_lift by ~0.03 rad, raising the actual TCP
# ~1.7cm above the commanded pinch. Command the grasp ~1.7cm LOWER so the live
# gripper clamps the ball's equator (center z=0.028), not its upper hemisphere.
GRASP_BIAS = 0.017
TARGETS = [
    ("above_ball", [BALL_XY[0], BALL_XY[1], 0.22]),
    ("at_ball", [BALL_XY[0], BALL_XY[1], 0.03 - GRASP_BIAS]),
    # Gentle staged lift: a single 0.03->0.22 move accelerates hard enough to fling
    # the just-clamped ball up into an unstable perch. Lift in steps instead.
    ("lift_a", [BALL_XY[0], BALL_XY[1], 0.07]),
    ("lift_b", [BALL_XY[0], BALL_XY[1], 0.13]),
    ("lift", [BALL_XY[0], BALL_XY[1], CARRY_Z]),
]
# Carry arc: linearly interpolate xy from ball -> place at constant height, every
# point solved down-pointing. Dense points keep the gripper vertical THROUGHOUT
# (linear joint interp between far-apart configs tilts the EE and the caged ball
# rolls out — only adjacent near-identical down-poses stay vertical between them).
for i in range(1, N_CARRY + 1):
    t = i / (N_CARRY + 1)
    cx = BALL_XY[0] + t * (PLACE_XY[0] - BALL_XY[0])
    cy = BALL_XY[1] + t * (PLACE_XY[1] - BALL_XY[1])
    TARGETS.append((f"carry{i}", [cx, cy, CARRY_Z]))
TARGETS += [
    ("above_place", [PLACE_XY[0], PLACE_XY[1], CARRY_Z]),
    ("at_place", [PLACE_XY[0], PLACE_XY[1], 0.04 - GRASP_BIAS]),
]


def solve(m, d, site, target_xyz, seed, iters=400, pos_w=1.0, rot_w=0.5, target_R=None):
    """Damped least-squares IK.

    Orientation: if target_R is given, drive the FULL site orientation to it
    (keeps the gripper's world yaw fixed so the V-cradle valley never rotates and
    the ball can't roll out during a base-panning carry). Otherwise just make the
    site local z point world -z (down), leaving yaw free.
    """
    q = seed.copy()
    target = np.array(target_xyz)
    jacp = np.zeros((3, m.nv))
    jacr = np.zeros((3, m.nv))
    lower = m.jnt_range[1:7, 0]
    upper = m.jnt_range[1:7, 1]
    for _ in range(iters):
        d.qpos[ARM_QPOS] = q
        mujoco.mj_forward(m, d)
        pos = d.site_xpos[site].copy()
        Rc = d.site_xmat[site].reshape(3, 3)  # columns = site axes in world
        e_pos = (target - pos) * pos_w
        if target_R is not None:
            # standard orientation servo error: 0.5 * sum cross(current_axis, target_axis)
            e_rot = 0.5 * (
                np.cross(Rc[:, 0], target_R[:, 0])
                + np.cross(Rc[:, 1], target_R[:, 1])
                + np.cross(Rc[:, 2], target_R[:, 2])
            ) * rot_w
        else:
            e_rot = np.cross(Rc[:, 2], np.array([0.0, 0.0, -1.0])) * rot_w
        err = np.concatenate([e_pos, e_rot])
        if np.linalg.norm(e_pos) < 1e-3 and np.linalg.norm(e_rot) < 1e-2:
            break
        mujoco.mj_jacSite(m, d, jacp, jacr, site)
        J = np.vstack([jacp[:, ARM_QVEL], jacr[:, ARM_QVEL]])  # 6x6
        dq = J.T @ np.linalg.solve(J @ J.T + 1e-4 * np.eye(6), err)
        q = np.clip(q + dq, lower, upper)
    d.qpos[ARM_QPOS] = q
    mujoco.mj_forward(m, d)
    return q, d.site_xpos[site].copy(), d.site_xmat[site].reshape(3, 3).copy()


def main() -> None:
    m = mujoco.MjModel.from_xml_path(os.environ["MODEL_NAME"])
    d = mujoco.MjData(m)
    site = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "pinch")

    # Establish the grasp orientation once (down-pointing at the ball), then hold
    # that SAME full world orientation for every grasp/carry/place waypoint so the
    # gripper never rolls about vertical during the base-panning carry.
    _, _, R_grasp = solve(m, d, site, [BALL_XY[0], BALL_XY[1], 0.03 - GRASP_BIAS], HOME.copy())

    configs = {}
    seed = HOME.copy()
    for name, tgt in TARGETS:
        # above_ball is pre-grasp (gripper open, approaching) — down-only is fine;
        # everything from the grasp onward holds the fixed grasp orientation.
        tR = None if name == "above_ball" else R_grasp
        q, pos, Rc = solve(m, d, site, tgt, seed, target_R=tR)
        seed = q
        err = float(np.linalg.norm(np.array(tgt) - pos))
        print(
            f"{name}: target={tgt} reached=[{pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f}] "
            f"err={err*100:.1f}cm down_z={Rc[2,2]:.2f} q={[round(float(x),4) for x in q]}",
            flush=True,
        )
        configs[name] = [round(float(x), 5) for x in q]

    out = os.environ.get("IK_OUT", "/home/demo/dorarobotics-test/grasp_configs.json")
    with open(out, "w") as f:
        json.dump(configs, f, indent=2)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
