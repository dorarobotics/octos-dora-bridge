"""Unit tests for the pick-and-place pose builder."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from pick_place_poses import build_pick_place, top_down_pose  # noqa: E402


def test_top_down_orientation_is_down():
    p = top_down_pose(0.3, 0.0, 0.1)
    assert p["orientation"] == [1.0, 0.0, 0.0, 0.0]
    assert p["position"] == [0.3, 0.0, 0.1]


def test_sequence_order_and_count():
    steps = build_pick_place(
        ball_xy=(0.35, 0.0), place_xy=(0.30, 0.25), approach_z=0.25, grasp_z=0.10
    )
    labels = [s["label"] for s in steps]
    assert labels == [
        "home", "open gripper", "above ball", "descend to ball", "close on ball",
        "lift", "above place", "descend to place", "release", "retract", "home",
    ]


def test_grasp_targets_ball_xy():
    steps = build_pick_place(
        ball_xy=(0.35, -0.02), place_xy=(0.30, 0.25), approach_z=0.25, grasp_z=0.10
    )
    descend = next(s for s in steps if s["label"] == "descend to ball")
    assert descend["args"]["pose"]["position"][:2] == [0.35, -0.02]
    assert descend["args"]["pose"]["position"][2] == 0.10


def test_place_targets_place_xy():
    steps = build_pick_place(
        ball_xy=(0.35, 0.0), place_xy=(0.30, 0.25), approach_z=0.25, grasp_z=0.10
    )
    place = next(s for s in steps if s["label"] == "descend to place")
    assert place["args"]["pose"]["position"][:2] == [0.30, 0.25]


def test_gripper_open_close_widths():
    steps = build_pick_place(
        ball_xy=(0.35, 0.0), place_xy=(0.30, 0.25), approach_z=0.25, grasp_z=0.10
    )
    close = next(s for s in steps if s["label"] == "close on ball")
    rel = next(s for s in steps if s["label"] == "release")
    assert close["args"]["width"] == 0.0
    assert rel["args"]["width"] == 0.085


def test_approach_above_grasp():
    steps = build_pick_place(
        ball_xy=(0.35, 0.0), place_xy=(0.30, 0.25), approach_z=0.25, grasp_z=0.10
    )
    above = next(s for s in steps if s["label"] == "above ball")
    descend = next(s for s in steps if s["label"] == "descend to ball")
    assert above["args"]["pose"]["position"][2] > descend["args"]["pose"]["position"][2]
