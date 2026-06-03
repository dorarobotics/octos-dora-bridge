#!/usr/bin/env python3
"""gripper_merge — fold a gripper width into the arm joint-command control vector.

The MuJoCo sim node takes a single `control_input` vector. The arm planner/executor
produce arm joint commands; moveit_arm_node emits a separate `gripper_command`
({"width": w}). This node merges them so the gripper actuator(s) ride the same
control vector.

NOTE: gripper_index, gripper_ctrl_range, and the width->ctrl mapping direction must
match ur5e.xml's actuator layout — verified on epyc (set via env vars below).
"""
from __future__ import annotations

import json
from typing import Optional


def merge_control(
    *,
    arm_joints: list[float],
    gripper_width: Optional[float],
    gripper_index: int,
    gripper_open_width: float,
    gripper_ctrl_range: tuple[float, float],
    last_gripper_ctrl: float = 0.0,
) -> list[float]:
    """Return a control vector = arm_joints with the gripper ctrl placed at
    gripper_index. width maps linearly: open_width -> ctrl_min, 0 -> ctrl_max
    (Robotiq convention: higher ctrl = more closed). gripper_width None -> reuse
    last_gripper_ctrl."""
    out = list(arm_joints)
    cmin, cmax = gripper_ctrl_range
    if gripper_width is None:
        ctrl = last_gripper_ctrl
    else:
        frac = max(0.0, min(1.0, gripper_width / gripper_open_width))
        ctrl = cmax - frac * (cmax - cmin)
    while len(out) <= gripper_index:
        out.append(0.0)
    out[gripper_index] = ctrl
    return out


def main() -> None:  # pragma: no cover - requires dora runtime
    import os
    import pyarrow as pa
    from dora import Node

    gripper_index = int(os.environ.get("GRIPPER_CTRL_INDEX", "6"))
    open_width = float(os.environ.get("GRIPPER_OPEN_WIDTH", "0.085"))
    cmin = float(os.environ.get("GRIPPER_CTRL_MIN", "0.0"))
    cmax = float(os.environ.get("GRIPPER_CTRL_MAX", "255.0"))

    node = Node()
    last_arm: list[float] = []
    last_ctrl = cmax
    for event in node:
        if event["type"] != "INPUT":
            continue
        val = event["value"].to_pylist()[0]
        if event["id"] == "joint_commands":
            last_arm = list(json.loads(val)) if isinstance(val, str) else list(val)
            out = merge_control(
                arm_joints=last_arm, gripper_width=None, gripper_index=gripper_index,
                gripper_open_width=open_width, gripper_ctrl_range=(cmin, cmax),
                last_gripper_ctrl=last_ctrl,
            )
            node.send_output("control_input", pa.array(out))
        elif event["id"] == "gripper_command":
            payload = json.loads(val) if isinstance(val, str) else val
            merged = merge_control(
                arm_joints=last_arm or [0.0] * gripper_index, gripper_width=payload["width"],
                gripper_index=gripper_index, gripper_open_width=open_width,
                gripper_ctrl_range=(cmin, cmax),
            )
            last_ctrl = merged[gripper_index]
            node.send_output("control_input", pa.array(merged))


if __name__ == "__main__":
    main()
