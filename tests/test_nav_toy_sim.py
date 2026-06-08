"""Unit tests for the nav toy-sim kinematics (examples/nav_toy_sim.py)."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from nav_toy_sim import ToySim, target_from_goal  # noqa: E402


def _drive(sim: ToySim, steps: int = 2000, dt: float = 0.05) -> None:
    for _ in range(steps):
        sim.step(dt)
        if sim.status == "arrived":
            return


def test_target_from_spec_pose():
    assert target_from_goal({"position": [2.0, 1.0, 0.0], "orientation": [0, 0, 0, 1]}) == (2.0, 1.0)


def test_target_from_flat_pose():
    assert target_from_goal({"x": -1.0, "y": 3.0, "theta": 0.0}) == (-1.0, 3.0)


def test_target_from_garbage():
    assert target_from_goal({"nope": 1}) is None
    assert target_from_goal("not a dict") is None


def test_goal_drives_to_target_and_arrives():
    sim = ToySim()
    sim.set_goal(2.0, 0.0)
    assert sim.status == "following"
    _drive(sim)
    assert sim.status == "arrived"
    assert math.hypot(sim.x - 2.0, sim.y - 0.0) < 0.15


def test_goal_reaches_offset_target():
    sim = ToySim()
    sim.set_goal(-1.5, 2.0)
    _drive(sim)
    assert sim.status == "arrived"
    assert math.hypot(sim.x + 1.5, sim.y - 2.0) < 0.15


def test_cancel_goes_idle_and_stops():
    sim = ToySim()
    sim.set_goal(5.0, 5.0)
    sim.step(0.05)
    sim.cancel()
    assert sim.status == "idle"
    x_before, y_before = sim.x, sim.y
    sim.step(0.05)
    assert (sim.x, sim.y) == (x_before, y_before)


def test_set_velocity_integrates_forward():
    sim = ToySim()
    sim.set_velocity(0.5, 0.0)  # straight ahead along +x (theta=0)
    assert sim.status == "following"
    for _ in range(10):
        sim.step(0.1)
    assert sim.x > 0.4
    assert abs(sim.y) < 1e-6


def test_set_velocity_turns():
    sim = ToySim()
    sim.set_velocity(0.0, 1.0)
    for _ in range(10):
        sim.step(0.1)
    assert abs(sim.theta - 1.0) < 1e-6


def test_zero_velocity_is_idle():
    sim = ToySim()
    sim.set_velocity(0.0, 0.0)
    assert sim.status == "idle"


def test_pose_is_json_friendly():
    sim = ToySim()
    sim.set_goal(1.0, 1.0)
    sim.step(0.05)
    p = sim.pose
    assert set(p) == {"x", "y", "theta"}
    assert all(isinstance(v, float) for v in p.values())
