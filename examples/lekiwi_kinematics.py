"""Pure kinematic core for the LeKiwi mobile base — no dora/mujoco imports.

Milestone-1 motion is unicycle: the commanded twist is (linear, angular) with no
lateral component, so base-pose integration is the standard unicycle model (same
as nav_toy_sim's ToySim velocity branch). `wheel_velocities` converts a full
holonomic body twist (vx, vy, omega) into 3 omniwheel angular speeds for VISUAL
wheel spin only; constants are the LeKiwi layout borrowed from lerobot and are not
load-bearing in milestone 1.
"""
from __future__ import annotations

import math

MAX_LIN = 0.6   # m/s clamp
MAX_ANG = 1.5   # rad/s clamp

# LeKiwi base geometry (borrowed from lerobot's LeKiwi; visual-only here).
WHEEL_RADIUS = 0.05     # m
BASE_RADIUS = 0.125     # m  (wheel contact circle radius)
# Three omniwheels spaced 120 deg apart.
WHEEL_ANGLES = (math.radians(90.0), math.radians(210.0), math.radians(330.0))


def _wrap(a: float) -> float:
    """Wrap an angle to [-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


class LeKiwiBase:
    """Unicycle kinematic base with omniwheel-spin output. Drive via `step(dt)`."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.status = "idle"
        self._v = 0.0
        self._w = 0.0
        self.wheel_angle = [0.0, 0.0, 0.0]   # accumulated, for visual spin

    def set_velocity(self, linear: float, angular: float) -> None:
        self._v = _clamp(float(linear), -MAX_LIN, MAX_LIN)
        self._w = _clamp(float(angular), -MAX_ANG, MAX_ANG)
        self.status = "idle" if (self._v == 0.0 and self._w == 0.0) else "following"

    def cancel(self) -> None:
        self._v = self._w = 0.0
        self.status = "idle"

    def step(self, dt: float) -> None:
        if self.status != "following":
            return
        self.x += self._v * math.cos(self.theta) * dt
        self.y += self._v * math.sin(self.theta) * dt
        self.theta = _wrap(self.theta + self._w * dt)
        w1, w2, w3 = self.wheel_velocities(self._v, 0.0, self._w)
        self.wheel_angle[0] = _wrap(self.wheel_angle[0] + w1 * dt)
        self.wheel_angle[1] = _wrap(self.wheel_angle[1] + w2 * dt)
        self.wheel_angle[2] = _wrap(self.wheel_angle[2] + w3 * dt)

    def wheel_velocities(self, vx: float, vy: float, omega: float) -> tuple[float, float, float]:
        """Body twist (m/s, m/s, rad/s) -> 3 wheel angular speeds (rad/s)."""
        out = []
        for beta in WHEEL_ANGLES:
            v_tangential = -math.sin(beta) * vx + math.cos(beta) * vy + BASE_RADIUS * omega
            out.append(v_tangential / WHEEL_RADIUS)
        return (out[0], out[1], out[2])

    @property
    def pose(self) -> dict[str, float]:
        return {
            "x": round(self.x, 4),
            "y": round(self.y, 4),
            "theta": round(self.theta, 4),
        }
