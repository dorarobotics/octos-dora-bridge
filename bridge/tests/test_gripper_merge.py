"""gripper_merge folds a gripper width into the arm joint-command control vector."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "examples"))

from gripper_merge import merge_control  # noqa: E402


def test_merge_appends_gripper_dof_at_configured_index():
    arm = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
    out = merge_control(arm_joints=arm, gripper_width=0.0, gripper_index=6,
                        gripper_open_width=0.085, gripper_ctrl_range=(0.0, 255.0))
    assert out[:6] == arm
    assert out[6] == 255.0  # width 0.0 (closed) -> max ctrl (Robotiq: 255=closed)


def test_open_width_maps_to_min_ctrl():
    out = merge_control(arm_joints=[0.0] * 6, gripper_width=0.085, gripper_index=6,
                        gripper_open_width=0.085, gripper_ctrl_range=(0.0, 255.0))
    assert out[6] == 0.0  # fully open -> 0 ctrl


def test_missing_gripper_uses_last_known():
    out = merge_control(arm_joints=[0.0] * 6, gripper_width=None, gripper_index=6,
                        gripper_open_width=0.085, gripper_ctrl_range=(0.0, 255.0),
                        last_gripper_ctrl=128.0)
    assert out[6] == 128.0
