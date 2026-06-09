"""MuJoCo sim backend for the LeKiwi base — drop-in for nav_toy_sim.

Mirrors nav_toy_sim's I/O contract exactly so nav_base needs no change:
  inputs : tick, goal, cancel, cmd_vel
  outputs: pose {x,y,theta}, status (str), obstacles (list)

The base is KINEMATIC: each tick we integrate LeKiwiBase, write the base free
joint qpos (x, y, z, yaw-quat) and the 3 wheel-joint qpos, then mj_forward (no
dynamics). A passive viewer renders it when a display is available.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

from lekiwi_kinematics import LeKiwiBase
from lekiwi_scene import BASE_Z, build_scene

WHEEL_JOINTS = (
    "ST3215_Servo_Motor-v1-2_Hub---Servo",
    "ST3215_Servo_Motor-v1-1_Hub-2---Servo",
    "ST3215_Servo_Motor-v1_Revolute-40",
)
OBSTACLES: list = []   # empty map for milestone 1 (nav_base runs with NAV_FAKE_MAP=1)


def _yaw_quat(theta: float) -> tuple[float, float, float, float]:
    return (math.cos(theta / 2.0), 0.0, 0.0, math.sin(theta / 2.0))


def main() -> None:  # pragma: no cover — needs a running dora daemon + mujoco
    import mujoco
    import pyarrow as pa
    from dora import Node

    sim_dir = os.environ["LEKIWI_SIM_DIR"]
    # SIM_DT: this node's tick integration step (seconds); set per-node in the dataflow env
    dt = float(os.environ.get("SIM_DT", "0.05"))
    scene_xml = build_scene(
        os.path.join(sim_dir, "mjcf_lcmm_robot.xml"),
        # meshdir is the model's own dir: the MJCF mesh file= paths already
        # include the "meshes/" prefix, so pointing at sim_dir/meshes doubles it.
        meshdir=sim_dir,
    )
    model = mujoco.MjModel.from_xml_string(scene_xml)
    data = mujoco.MjData(model)

    base_qadr = model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "base_free")]
    wheel_qadr = [
        model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, j)]
        for j in WHEEL_JOINTS
    ]

    viewer = None
    try:
        import mujoco.viewer
        viewer = mujoco.viewer.launch_passive(model, data)
    except Exception as exc:  # headless or no display — run without a window
        print(f"[lekiwi_sim] viewer unavailable ({exc}); running headless", flush=True)

    base = LeKiwiBase()
    node = Node()

    def emit(out_id: str, payload: Any) -> None:
        node.send_output(out_id, pa.array([json.dumps(payload)]))

    def decode(value: Any) -> Any:
        items = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
        if not items:
            return None
        return json.loads(items[0]) if isinstance(items[0], str) else items[0]

    def render() -> None:
        qw, qx, qy, qz = _yaw_quat(base.theta)
        data.qpos[base_qadr : base_qadr + 7] = [base.x, base.y, BASE_Z, qw, qx, qy, qz]
        for adr, ang in zip(wheel_qadr, base.wheel_angle):
            data.qpos[adr] = ang
        mujoco.mj_forward(model, data)
        if viewer is not None:
            viewer.sync()

    try:
        for event in node:
            if event["type"] == "STOP":
                break
            if event["type"] != "INPUT":
                continue
            eid = event["id"]
            if eid == "tick":
                base.step(dt)
                render()
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
        if viewer is not None:
            viewer.close()


if __name__ == "__main__":
    main()
