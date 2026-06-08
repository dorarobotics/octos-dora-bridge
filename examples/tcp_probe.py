#!/usr/bin/env python3
"""Diagnostic node: report the gripper TCP (pinch site) world position via FK.

Loads the same ur5e.xml, subscribes to the full qpos (mujoco_sim/joint_positions),
runs mj_forward, and prints the 'pinch' site world xyz alongside the ball body xyz.
Lets us check whether move_to_pose actually places the TCP at the commanded
Cartesian target. Not part of the product dataflow.
"""
from __future__ import annotations

import os


def main() -> None:
    import mujoco
    import numpy as np
    from dora import Node

    model_path = os.environ["MODEL_NAME"]
    m = mujoco.MjModel.from_xml_path(model_path)
    d = mujoco.MjData(m)
    pinch = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SITE, "pinch")
    ball = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "red_ball")

    node = Node()
    i = 0
    for event in node:
        if event["type"] != "INPUT":
            continue
        q = event["value"].to_numpy()
        i += 1
        if i % 40 != 0:
            continue
        n = min(len(q), m.nq)
        d.qpos[:n] = q[:n]
        mujoco.mj_forward(m, d)
        tcp = d.site_xpos[pinch] if pinch >= 0 else np.zeros(3)
        bxyz = d.xpos[ball] if ball >= 0 else np.zeros(3)
        print(
            f"TCP pinch=[{tcp[0]:.3f}, {tcp[1]:.3f}, {tcp[2]:.3f}] "
            f"ball=[{bxyz[0]:.3f}, {bxyz[1]:.3f}, {bxyz[2]:.3f}]",
            flush=True,
        )


if __name__ == "__main__":
    main()
