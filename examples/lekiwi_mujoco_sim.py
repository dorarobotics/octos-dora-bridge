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

    # Live view: render the scene OFFSCREEN (EGL) and stream frames to a rerun
    # window. The MuJoCo GLFW passive viewer stalls the dora event loop (it starves
    # the GUI thread of the GIL while `for event in node` blocks), so we avoid it.
    # rerun runs in its own process, so there is no GL/GIL contention here.
    # Disable with LEKIWI_RERUN=0 (headless / CI). Render cadence: LEKIWI_RENDER_EVERY.
    renderer = None
    rr = None
    cam = None
    render_every = max(1, int(os.environ.get("LEKIWI_RENDER_EVERY", "3")))
    if os.environ.get("LEKIWI_RERUN", "1") == "1":
        try:
            import rerun as rr_mod
            # dora launches this via the conda python's absolute path, so the env's
            # bin/ (with the bundled `rerun` viewer) isn't on PATH; add rerun_cli.
            cli = os.path.join(os.path.dirname(os.path.dirname(rr_mod.__file__)), "rerun_cli")
            if os.path.isdir(cli):
                os.environ["PATH"] = cli + os.pathsep + os.environ.get("PATH", "")
            rr_mod.init("lekiwi_mujoco_sim", spawn=True)
            renderer = mujoco.Renderer(model, 480, 640)
            cam = mujoco.MjvCamera()
            mujoco.mjv_defaultFreeCamera(model, cam)
            cam.distance, cam.elevation, cam.azimuth = 2.2, -25.0, 120.0
            rr = rr_mod
            print("[lekiwi_sim] rerun viewer up; offscreen rendering enabled", flush=True)
        except Exception as exc:  # rerun missing / no GL — fall back to headless
            print(f"[lekiwi_sim] rerun/offscreen render unavailable ({exc}); headless", flush=True)
            renderer = rr = cam = None

    base = LeKiwiBase()
    node = Node()
    frame_i = 0

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

    def publish_frame() -> None:
        # camera follows the base; offscreen render -> rerun image stream
        cam.lookat[0], cam.lookat[1], cam.lookat[2] = base.x, base.y, 0.1
        renderer.update_scene(data, cam)
        rr.log("lekiwi/view", rr.Image(renderer.render()))

    try:
        for event in node:
            if event["type"] == "STOP":
                break
            if event["type"] != "INPUT":
                continue
            eid = event["id"]
            if eid == "tick":
                frame_i += 1
                base.step(dt)
                render()
                if renderer is not None and frame_i % render_every == 0:
                    publish_frame()
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
        if renderer is not None:
            renderer.close()


if __name__ == "__main__":
    main()
