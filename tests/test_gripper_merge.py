"""Regression tests for gripper_merge decoding (examples/gripper_merge.py).

The original bug: joint_commands arrives as a raw float array, but the node
decoded every input as `to_pylist()[0]` (correct only for the JSON-string
gripper_command). Taking [0] of the float array gave a single float, then
`list(float)` raised "TypeError: 'float' object is not iterable" — gripper_merge
crashed at startup, so control_input never reached the sim and the arm never moved.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from gripper_merge import decode_joint_commands, merge_control  # noqa: E402


def test_decode_joint_commands_from_float_array():
    # what pa.array([...], float32).to_pylist() yields — the FULL vector
    items = [0.0, -1.5708, 1.5708, 0.0, 0.0, 0.0, 0.1]
    assert decode_joint_commands(items) == items


def test_decode_joint_commands_preserves_all_six_arm_joints():
    # the exact regression: must not collapse to just the first element
    items = [-0.5, -1.2, 1.0, -1.4, -1.57, 0.3]
    out = decode_joint_commands(items)
    assert len(out) == 6
    assert out == items


def test_decode_joint_commands_tolerates_json_string():
    assert decode_joint_commands(["[0.1, 0.2, 0.3]"]) == [0.1, 0.2, 0.3]


def test_merge_control_places_gripper_at_index():
    out = merge_control(
        arm_joints=[0.0] * 6, gripper_width=0.0, gripper_index=6,
        gripper_open_width=0.085, gripper_ctrl_range=(0.0, 255.0),
    )
    assert len(out) == 7
    assert out[6] == 255.0  # width 0 -> fully closed (cmax)


def test_merge_control_open_width_maps_to_cmin():
    out = merge_control(
        arm_joints=[0.0] * 6, gripper_width=0.085, gripper_index=6,
        gripper_open_width=0.085, gripper_ctrl_range=(0.0, 255.0),
    )
    assert out[6] == 0.0  # full open -> cmin
