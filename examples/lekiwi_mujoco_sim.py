"""MuJoCo sim backend for the LeKiwi base — drop-in for nav_toy_sim.

Mirrors nav_toy_sim's I/O contract (inputs tick/goal/cancel/cmd_vel; outputs
pose/status/obstacles) so nav_base needs no change.

Virtual omni-drive: octos commands a (linear, angular) twist; we derive the 3
omniwheel speeds (LeKiwi kinematics) and command the wheel VELOCITY actuators
(drive_motor_1/2/3 == lerobot motors 7/8/9), stepping real physics (mj_step) so
the wheels physically spin. The base body is placed by the holonomic
forward-kinematics each tick. Gravity and contacts are disabled (the shipped
omniwheels are single rigid bodies without rollers, so wheel-ground contact can't
produce correct holonomic motion) — the wheels are genuinely actuated, the base
pose comes from the kinematic integrator.

Headless by design (no live viewer — it stalls the dora loop). For a watchable
result set LEKIWI_TRAJ=<path>: the qpos trajectory is recorded and lekiwi_render_video.py
renders it to an MP4 offline.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

from lekiwi_kinematics import LeKiwiBase
from lekiwi_scene import BASE_Z, build_scene

DRIVE_ACTUATORS = ("drive_motor_1", "drive_motor_2", "drive_motor_3")
OBSTACLES: list = []   # empty map for milestone 1 (nav_base runs with NAV_FAKE_MAP=1)


def _yaw_quat(theta: float) -> tuple[float, float, float, float]:
    return (math.cos(theta / 2.0), 0.0, 0.0, math.sin(theta / 2.0))


def main() -> None:  # pragma: no cover — needs a running dora daemon + mujoco
    import mujoco
    import numpy as np
    import pyarrow as pa
    from dora import Node

    sim_dir = os.environ["LEKIWI_SIM_DIR"]
    # SIM_DT: control-tick integration step (seconds); set per-node in the dataflow env
    dt = float(os.environ.get("SIM_DT", "0.05"))
    traj_path = os.environ.get("LEKIWI_TRAJ", "")

    scene_xml = build_scene(
        os.path.join(sim_dir, "mjcf_lcmm_robot.xml"),
        # meshdir is the model's own dir: the MJCF mesh file= paths already
        # include the "meshes/" prefix, so pointing at sim_dir/meshes doubles it.
        meshdir=sim_dir,
    )
    model = mujoco.MjModel.from_xml_string(scene_xml)
    data = mujoco.MjData(model)
    n_sub = max(1, int(round(dt / model.opt.timestep)))   # physics substeps per tick

    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "base_free")
    base_qadr = model.jnt_qposadr[jid]
    base_vadr = model.jnt_dofadr[jid]
    drive_adr = [
        mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_ACTUATOR, a) for a in DRIVE_ACTUATORS
    ]

    base = LeKiwiBase()
    node = Node()
    traj = [] if traj_path else None
    print(f"[lekiwi_sim] virtual omni-drive up (n_sub={n_sub}, traj={'on' if traj else 'off'})", flush=True)

    def emit(out_id: str, payload: Any) -> None:
        node.send_output(out_id, pa.array([json.dumps(payload)]))

    def decode(value: Any) -> Any:
        items = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
        if not items:
            return None
        return json.loads(items[0]) if isinstance(items[0], str) else items[0]

    def control_step() -> None:
        # command the 3 wheel velocity actuators with the IK wheel speeds (motors 7/8/9)
        w1, w2, w3 = base.wheel_velocities(base._v, 0.0, base._w)
        data.ctrl[drive_adr[0]] = w1
        data.ctrl[drive_adr[1]] = w2
        data.ctrl[drive_adr[2]] = w3
        for _ in range(n_sub):
            mujoco.mj_step(model, data)   # wheels physically spin (contacts/gravity off)
        # virtual base drive: place the base by forward-kinematics, freeze its vel
        qw, qx, qy, qz = _yaw_quat(base.theta)
        data.qpos[base_qadr : base_qadr + 7] = [base.x, base.y, BASE_Z, qw, qx, qy, qz]
        data.qvel[base_vadr : base_vadr + 6] = 0.0
        mujoco.mj_forward(model, data)
        if traj is not None:
            traj.append(data.qpos.copy())

    try:
        for event in node:
            if event["type"] == "STOP":
                break
            if event["type"] != "INPUT":
                continue
            eid = event["id"]
            if eid == "tick":
                base.step(dt)
                control_step()
                emit("pose", base.pose)
                emit("status", base.status)
                emit("obstacles", OBSTACLES)
            elif eid == "cmd_vel":
                cmd = decode(event["value"]) or {}
                base.set_velocity(float(cmd.get("linear", 0.0)), float(cmd.get("angular", 0.0)))
            elif eid == "cancel":
                base.cancel()
            elif eid == "goal":
                # milestone 1 is teleop-only; a goal just stops (no planner).
                base.cancel()
    finally:
        if traj:
            np.save(traj_path, np.asarray(traj))
            print(f"[lekiwi_sim] wrote {len(traj)} frames -> {traj_path}.npy", flush=True)


if __name__ == "__main__":
    main()
