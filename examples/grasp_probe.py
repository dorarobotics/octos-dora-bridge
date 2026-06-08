#!/usr/bin/env python3
"""Offline grasp-physics probe: place the ball, close the gripper at the grasp
config, and report the ACTUAL MuJoCo contacts on the ball (where the pads touch),
then test a lift. Reveals why the grasp cradles vs clamps. Fast (no dora boot).

Run on epyc: MODEL_NAME=...ur5e.xml GRASP_CONFIGS=...grasp_configs.json python grasp_probe.py
"""
from __future__ import annotations

import json
import os

import mujoco
import numpy as np

ARM_QPOS = slice(7, 13)


def gname(m, gid):
    return mujoco.mj_id2name(m, mujoco.mjtObj.mjOBJ_GEOM, gid) or f"geom{gid}"


def report_contacts(m, d, ball_gid, tag):
    pinch = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "pinch")
    ball_b = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "red_ball")
    p = d.site_xpos[pinch]
    b = d.xpos[ball_b]
    print(f"[{tag}] pinch=({p[0]:.3f},{p[1]:.3f},{p[2]:.3f}) "
          f"ball=({b[0]:.3f},{b[1]:.3f},{b[2]:.3f}) ball-above-pinch={b[2]-p[2]:+.3f}", flush=True)
    n = 0
    for i in range(d.ncon):
        c = d.contact[i]
        if c.geom1 == ball_gid or c.geom2 == ball_gid:
            other = c.geom2 if c.geom1 == ball_gid else c.geom1
            cp = c.pos
            print(f"    contact: {gname(m, other):20s} at ({cp[0]:.3f},{cp[1]:.3f},{cp[2]:.3f}) "
                  f"dist={c.dist:+.4f}", flush=True)
            n += 1
    if n == 0:
        print("    NO contacts on ball", flush=True)


def main() -> None:
    m = mujoco.MjModel.from_xml_path(os.environ["MODEL_NAME"])
    d = mujoco.MjData(m)
    with open(os.environ["GRASP_CONFIGS"]) as f:
        cfg = json.load(f)
    ball_gid = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball")

    # Reset to keyframe, place ball at its settled spot, arm at at_ball, gripper open.
    if m.nkey > 0:
        mujoco.mj_resetDataKeyframe(m, d, 0)
    d.qpos[0:3] = [0.35, 0.0, 0.028]
    d.qpos[3:7] = [1.0, 0.0, 0.0, 0.0]
    d.qpos[ARM_QPOS] = cfg["at_ball"]
    d.ctrl[0:6] = cfg["at_ball"]
    d.ctrl[6] = 0.0  # gripper open
    mujoco.mj_forward(m, d)
    report_contacts(m, d, ball_gid, "at_ball / open (settle)")

    # Close the gripper on the ball.
    d.ctrl[6] = 255.0
    for _ in range(800):
        d.ctrl[0:6] = cfg["at_ball"]
        mujoco.mj_step(m, d)
    report_contacts(m, d, ball_gid, "after close")
    print(f"    gripper driver joints qpos[13:21]={[round(float(x),3) for x in d.qpos[13:21]]}", flush=True)

    # Lift.
    for _ in range(1200):
        d.ctrl[0:6] = cfg["lift"]
        d.ctrl[6] = 255.0
        mujoco.mj_step(m, d)
    report_contacts(m, d, ball_gid, "after lift")


if __name__ == "__main__":
    main()
