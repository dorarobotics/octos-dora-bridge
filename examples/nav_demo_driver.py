#!/usr/bin/env python3
"""Scripted nav-base skill demo — drives the toy sim through octos HTTP.

Watch the rerun window: the blue robot box drives to each goal, spins on a
velocity command, stops, and finally halts on an estop. Every action here is a
real octos tool call (POST /tools/<verb>) against the nav-base bridge on :8769.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _demo_common import call, check, detail, require_healthz, say  # noqa: E402

BASE = os.environ.get("NAV_BRIDGE_URL", "http://127.0.0.1:8769")


def _pose(x: float, y: float) -> dict:
    return {"position": [x, y, 0.0], "orientation": [0.0, 0.0, 0.0, 1.0]}


def _goto(x: float, y: float, label: str, settle: float = 6.0) -> None:
    say(f"go_to_pose → {label} ({x}, {y})")
    check(call(BASE, "vendor.dora_nav.base.go_to_pose", pose=_pose(x, y), control_source="demo"),
          "go_to_pose")
    detail("…driving (watch rerun)…")
    time.sleep(settle)
    pose = call(BASE, "vendor.dora_nav.localization.get_pose")
    detail(f"pose now: {pose.get('data', {}).get('pose')}")


def main() -> int:
    require_healthz(BASE)

    say("get_capabilities")
    caps = check(call(BASE, "robot.get_capabilities"), "get_capabilities")
    verbs = [c["verb"] for c in caps.get("data", {}).get("commands", [])]
    detail(f"{len(verbs)} verbs advertised")

    say("get_obstacles (static map)")
    obs = check(call(BASE, "vendor.dora_nav.map.get_obstacles"), "get_obstacles")
    detail(f"obstacles: {obs.get('data', {}).get('obstacles')}")

    _goto(2.0, 0.0, "waypoint A", settle=7)
    _goto(2.0, 2.0, "waypoint B", settle=7)
    _goto(-1.0, 2.0, "waypoint C", settle=9)

    say("set_velocity → spin in place (angular 1.0 rad/s) for 3s")
    check(call(BASE, "vendor.dora_nav.base.set_velocity", linear=0.0, angular=1.0,
               control_source="demo"), "set_velocity")
    time.sleep(3)

    say("stop")
    check(call(BASE, "vendor.dora_nav.base.stop"), "stop")
    time.sleep(1)

    say("go_to_pose → back toward origin, then ESTOP mid-drive")
    check(call(BASE, "vendor.dora_nav.base.go_to_pose", pose=_pose(0.0, 0.0),
               control_source="demo"), "go_to_pose")
    time.sleep(2.5)
    say("robot.estop — base must halt immediately")
    check(call(BASE, "robot.estop", reason="demo_finale"), "estop")
    time.sleep(1)

    say("get_recent_safety_events(since=0) — validates the seq fix")
    ev = call(BASE, "get_recent_safety_events", since=0)
    events = ev.get("data", {}).get("events", [])
    detail(f"events: {events}")
    if any(e.get("kind") == "estop" for e in events):
        detail("✓ estop event visible at since=0 (seq fix works)")
    else:
        detail("✗ no estop event at since=0 — seq regression!")

    say("Demo complete. Leave running to inspect rerun, or Ctrl-C the launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
