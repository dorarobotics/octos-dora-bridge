#!/usr/bin/env python3
"""Scripted UR5e arm skill demo — drives the MuJoCo arm through octos HTTP.

Watch the MuJoCo viewer: the arm moves to named/joint/pose targets and the
gripper opens & closes, then an estop halts it. Motion verbs are DEFERRED, so
each HTTP call blocks until the motion actually finishes — when the call returns
ok, the arm has arrived. Every action is a real octos tool call against :8768.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _demo_common import call, check, detail, require_healthz, say  # noqa: E402

BASE = os.environ.get("ARM_BRIDGE_URL", "http://127.0.0.1:8768")


def main() -> int:
    require_healthz(BASE)

    say("get_capabilities")
    caps = check(call(BASE, "robot.get_capabilities"), "get_capabilities")
    verbs = [c["verb"] for c in caps.get("data", {}).get("commands", [])]
    detail(f"{len(verbs)} verbs advertised")

    say("move_to_named → home  (blocks until arrived)")
    check(call(BASE, "vendor.moveit.arm.move_to_named", name="home", control_source="demo"),
          "move_to_named(home)")

    say("gripper → open")
    check(call(BASE, "vendor.moveit.arm.gripper.set", width=0.08), "gripper open")
    time.sleep(0.5)
    say("gripper → close")
    check(call(BASE, "vendor.moveit.arm.gripper.set", width=0.0), "gripper close")

    say("move_to_joint_state → a reachable config")
    check(call(BASE, "vendor.moveit.arm.move_to_joint_state",
               joints=[-0.5, -1.2, 1.0, -1.4, -1.57, 0.3], control_source="demo"),
          "move_to_joint_state")

    say("move_to_pose → a Cartesian target (async IK + plan + execute)")
    check(call(BASE, "vendor.moveit.arm.move_to_pose",
               pose={"position": [0.4, 0.1, 0.4],
                     "orientation": [1.0, 0.0, 0.0, 0.0]},
               control_source="demo"),
          "move_to_pose")

    say("move_to_named → up")
    check(call(BASE, "vendor.moveit.arm.move_to_named", name="up", control_source="demo"),
          "move_to_named(up)")

    say("move_to_named → home (return), then ESTOP finale")
    check(call(BASE, "vendor.moveit.arm.move_to_named", name="home", control_source="demo"),
          "move_to_named(home)")
    say("robot.estop")
    check(call(BASE, "robot.estop", reason="demo_finale"), "estop")
    time.sleep(0.5)

    say("get_recent_safety_events(since=0) — validates the seq fix")
    ev = call(BASE, "get_recent_safety_events", since=0)
    events = ev.get("data", {}).get("events", [])
    detail(f"events: {events}")
    if any(e.get("kind") == "estop" for e in events):
        detail("✓ estop event visible at since=0 (seq fix works)")
    else:
        detail("✗ no estop event at since=0 — seq regression!")

    say("Demo complete. Inspect the MuJoCo viewer, or Ctrl-C the launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
