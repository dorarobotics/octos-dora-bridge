#!/usr/bin/env python3
"""Offline-render a recorded LeKiwi qpos trajectory to an MP4.

The live sim runs headless (a live MuJoCo/rerun window stalls the dora loop), and
records its qpos trajectory via LEKIWI_TRAJ. This script replays that trajectory
through a MuJoCo offscreen renderer (EGL) and writes a video you can watch — the
actual 3D robot with the base driving and wheels 7/8/9 spinning.

Usage:
  LEKIWI_SIM_DIR=/path/to/LeKiwi-sim \\
  python lekiwi_render_video.py <traj.npy> <out.mp4> [fps]
"""
from __future__ import annotations

import os
import sys

import imageio.v2 as imageio
import mujoco
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from lekiwi_scene import build_scene  # noqa: E402

W, H = 640, 480   # MuJoCo's default offscreen framebuffer max


def main() -> int:
    traj_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/lekiwi_traj.npy"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/lekiwi.mp4"
    fps = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    sim_dir = os.environ["LEKIWI_SIM_DIR"]
    xml = build_scene(os.path.join(sim_dir, "mjcf_lcmm_robot.xml"), meshdir=sim_dir)
    model = mujoco.MjModel.from_xml_string(xml)
    data = mujoco.MjData(model)

    jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "base_free")
    base_qadr = model.jnt_qposadr[jid]

    traj = np.load(traj_path)
    print(f"[render] {len(traj)} frames from {traj_path}", flush=True)

    renderer = mujoco.Renderer(model, H, W)
    cam = mujoco.MjvCamera()
    mujoco.mjv_defaultFreeCamera(model, cam)
    cam.distance, cam.elevation, cam.azimuth = 2.4, -22.0, 130.0

    writer = imageio.get_writer(out_path, fps=fps, macro_block_size=None)
    try:
        for q in traj:
            data.qpos[:] = q
            mujoco.mj_forward(model, data)
            cam.lookat[0] = q[base_qadr]      # follow base x
            cam.lookat[1] = q[base_qadr + 1]  # follow base y
            cam.lookat[2] = 0.1
            renderer.update_scene(data, cam)
            writer.append_data(renderer.render())
    finally:
        writer.close()
        renderer.close()
    print(f"[render] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
