#!/usr/bin/env python3
"""Kinematic toy-sim backend for nav-base — a visual stand-in for dora-nav.

Replaces fake_localization + fake_planner with a single node that actually moves:
it integrates a unicycle model so a goal makes the base drive there and a
set_velocity makes it cruise. It publishes the same topics nav_base subscribes to
(dora_nav_pose / dora_nav_status / dora_nav_obstacles) and consumes nav_base's
outbound intents (dora_nav_goal / dora_nav_cancel / dora_nav_cmd_vel).

This is a TOY (no real localization, planning, or collision) — its only job is to
give nav-base verbs something visible to drive in the rerun viewer. The kinematic
core (`ToySim`) is pure and unit-tested; `main()` is the thin dora wrapper.
"""
from __future__ import annotations

import json
import math
import os
from typing import Any

MAX_LIN = 0.6          # m/s
MAX_ANG = 1.5          # rad/s
GOAL_TOL = 0.12        # m — "arrived" radius
HEADING_GATE = 0.35    # rad — only drive forward once roughly facing the goal

# A couple of static obstacles so the map view isn't empty. (x, y, radius)
DEFAULT_OBSTACLES = [
    {"x": 1.2, "y": 0.8, "radius": 0.25},
    {"x": 2.0, "y": -0.9, "radius": 0.3},
    {"x": -0.8, "y": 1.5, "radius": 0.2},
]


def _wrap(a: float) -> float:
    """Wrap an angle to [-pi, pi]."""
    return (a + math.pi) % (2 * math.pi) - math.pi


def target_from_goal(payload: dict[str, Any]) -> tuple[float, float] | None:
    """Extract an (x, y) target from a goal payload.

    Accepts both the SPEC pose shape ``{"position": [x, y, z], ...}`` (what
    go_to_pose forwards) and a flat ``{"x":.., "y":..}`` (named-waypoint style).
    """
    if not isinstance(payload, dict):
        return None
    pos = payload.get("position")
    if isinstance(pos, list) and len(pos) >= 2:
        return float(pos[0]), float(pos[1])
    if "x" in payload and "y" in payload:
        return float(payload["x"]), float(payload["y"])
    return None


class ToySim:
    """Unicycle-model kinematic toy. All motion goes through `step(dt)`."""

    def __init__(self) -> None:
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.status = "idle"
        self._mode = "idle"            # idle | goal | velocity
        self._target: tuple[float, float] | None = None
        self._v = 0.0
        self._w = 0.0

    # ---- intents ----
    def set_goal(self, x: float, y: float) -> None:
        self._target = (x, y)
        self._mode = "goal"
        self.status = "following"

    def set_velocity(self, linear: float, angular: float) -> None:
        self._v = linear
        self._w = angular
        if linear == 0.0 and angular == 0.0:
            self._mode = "idle"
            self.status = "idle"
        else:
            self._mode = "velocity"
            self.status = "following"

    def cancel(self) -> None:
        self._mode = "idle"
        self._target = None
        self._v = self._w = 0.0
        self.status = "idle"

    # ---- integration ----
    def step(self, dt: float) -> None:
        if self._mode == "goal" and self._target is not None:
            tx, ty = self._target
            dx, dy = tx - self.x, ty - self.y
            dist = math.hypot(dx, dy)
            if dist < GOAL_TOL:
                self._mode = "idle"
                self._target = None
                self.status = "arrived"
                return
            heading = math.atan2(dy, dx)
            ang_err = _wrap(heading - self.theta)
            self.theta = _wrap(
                self.theta + max(-MAX_ANG * dt, min(MAX_ANG * dt, ang_err))
            )
            if abs(ang_err) < HEADING_GATE:
                step = min(MAX_LIN * dt, dist)
                self.x += step * math.cos(self.theta)
                self.y += step * math.sin(self.theta)
        elif self._mode == "velocity":
            self.x += self._v * math.cos(self.theta) * dt
            self.y += self._v * math.sin(self.theta) * dt
            self.theta = _wrap(self.theta + self._w * dt)

    @property
    def pose(self) -> dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4), "theta": round(self.theta, 4)}


def main() -> None:  # pragma: no cover — needs a running dora daemon
    import pyarrow as pa
    from dora import Node

    sim = ToySim()
    obstacles = DEFAULT_OBSTACLES
    dt = float(os.environ.get("TOY_SIM_DT", "0.05"))
    node = Node()

    def emit(out_id: str, payload: Any) -> None:
        node.send_output(out_id, pa.array([json.dumps(payload)]))

    def decode(value: Any) -> Any:
        items = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
        if not items:
            return None
        return json.loads(items[0]) if isinstance(items[0], str) else items[0]

    for event in node:
        if event["type"] == "STOP":
            break
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        if eid == "tick":
            sim.step(dt)
            emit("pose", sim.pose)
            emit("status", sim.status)
            emit("obstacles", obstacles)
        elif eid == "goal":
            tgt = target_from_goal(decode(event["value"]))
            if tgt is not None:
                sim.set_goal(*tgt)
        elif eid == "cancel":
            sim.cancel()
        elif eid == "cmd_vel":
            cmd = decode(event["value"]) or {}
            sim.set_velocity(float(cmd.get("linear", 0.0)), float(cmd.get("angular", 0.0)))


if __name__ == "__main__":
    main()
