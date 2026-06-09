"""Unit tests for the pure LeKiwi kinematic core (examples/lekiwi_kinematics.py)."""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "examples"))

from lekiwi_kinematics import LeKiwiBase  # noqa: E402


def test_forward_velocity_increases_x():
    base = LeKiwiBase()
    base.set_velocity(0.3, 0.0)
    assert base.status == "following"
    for _ in range(20):           # 1.0 s at dt=0.05
        base.step(0.05)
    assert base.x > 0.25 and abs(base.y) < 1e-6
    assert abs(base.theta) < 1e-9


def test_zero_velocity_is_idle_and_static():
    base = LeKiwiBase()
    base.set_velocity(0.0, 0.0)
    assert base.status == "idle"
    base.step(0.05)
    assert (base.x, base.y, base.theta) == (0.0, 0.0, 0.0)


def test_angular_velocity_turns_in_place():
    base = LeKiwiBase()
    base.set_velocity(0.0, 1.0)
    for _ in range(10):           # 0.5 s
        base.step(0.05)
    assert abs(base.theta - 0.5) < 1e-6
    assert abs(base.x) < 1e-6 and abs(base.y) < 1e-6


def test_cancel_stops_motion():
    base = LeKiwiBase()
    base.set_velocity(0.3, 0.0)
    base.step(0.05)
    base.cancel()
    assert base.status == "idle"
    x0 = base.x
    base.step(0.05)
    assert base.x == x0


def test_wheel_velocities_zero_when_stopped():
    base = LeKiwiBase()
    assert base.wheel_velocities(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)


def test_wheel_velocities_forward_are_nonzero_and_finite():
    base = LeKiwiBase()
    w = base.wheel_velocities(0.3, 0.0, 0.0)
    assert len(w) == 3
    assert all(math.isfinite(v) for v in w)
    assert any(abs(v) > 1e-6 for v in w)
    # standard omniwheel geometry: forward motion spins wheel 0 negative, 1 & 2 positive
    assert w[0] < 0 and w[1] > 0 and w[2] > 0


def test_pose_dict_shape_and_rounding():
    base = LeKiwiBase()
    base.set_velocity(0.3, 0.0)
    base.step(0.05)
    p = base.pose
    assert set(p) == {"x", "y", "theta"}
    assert p["x"] == round(p["x"], 4)


def test_sim_module_imports_and_has_main():
    import importlib
    mod = importlib.import_module("lekiwi_mujoco_sim")
    assert callable(mod.main)
