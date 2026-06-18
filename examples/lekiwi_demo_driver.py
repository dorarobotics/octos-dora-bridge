"""Scripted LeKiwi teleop demo over octos HTTP — forward, turn, stop.

Each action is a real octos tool call (POST /tools/<verb>) against the LeKiwi
bridge on :8770. Watch the MuJoCo window: the base drives forward, turns, stops.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _demo_common import call, check, detail, require_healthz, say  # noqa: E402

BASE = os.environ.get("LEKIWI_BRIDGE_URL", "http://127.0.0.1:8770")


def main() -> int:
    require_healthz(BASE)

    say("get_capabilities")
    caps = check(call(BASE, "robot.get_capabilities"), "get_capabilities")
    detail(f"{len(caps.get('data', {}).get('commands', []))} verbs advertised")

    say("move forward (linear 0.3 m/s) for 3 s")
    check(call(BASE, "vendor.dora_nav.base.set_velocity", linear=0.3, angular=0.0,
               control_source="demo"), "set_velocity")
    time.sleep(3)
    pose = call(BASE, "vendor.dora_nav.localization.get_pose")
    detail(f"pose: {pose.get('data', {}).get('pose')}")

    say("turn left (angular 0.8 rad/s) for 2 s")
    check(call(BASE, "vendor.dora_nav.base.set_velocity", linear=0.0, angular=0.8,
               control_source="demo"), "set_velocity")
    time.sleep(2)

    say("stop")
    check(call(BASE, "vendor.dora_nav.base.stop"), "stop")
    pose = call(BASE, "vendor.dora_nav.localization.get_pose")
    detail(f"final pose: {pose.get('data', {}).get('pose')}")

    say("Demo complete. Leave running to inspect, or Ctrl-C the launcher.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
