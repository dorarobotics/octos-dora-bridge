#!/usr/bin/env python3
"""Diagnostic dora node: print MuJoCo's full qpos so we can see the true arm slice.

Subscribes to mujoco_sim/joint_positions (the full qpos vector) and periodically
prints the ball slice, the true arm slice (qpos[7:13]), and the gripper slice.
Used to confirm the ARM_QPOS_START offset. Not part of the product dataflow.
"""
from __future__ import annotations


def main() -> None:
    from dora import Node

    node = Node()
    i = 0
    j = 0
    last_ctrl = None
    for event in node:
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        if eid == "joint_positions":
            q = event["value"].to_numpy()
            i += 1
            if i % 40 == 0:
                ql = [round(float(x), 4) for x in q]
                print(
                    f"QPOS n={len(ql)} ball_xyz={ql[0:3]} arm[7:13]={ql[7:13]} "
                    f"slice0_6={ql[0:6]}",
                    flush=True,
                )
        elif eid == "control_input":
            c = [round(float(x), 4) for x in event["value"].to_numpy()]
            j += 1
            # print on change or every 40th to see the commanded arm vector
            if c != last_ctrl or j % 40 == 0:
                print(f"CTRL_IN n={len(c)} arm={c[0:6]} gripper={c[6:]}", flush=True)
                last_ctrl = c


if __name__ == "__main__":
    main()
