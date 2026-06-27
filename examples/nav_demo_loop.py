#!/usr/bin/env python3
"""Looping nav-base visual demo — drives the toy sim continuously (NO estop, so
the robot never latches). Watch the rerun window: the blue robot box drives a
patrol loop through waypoints, spins, and stops, over and over."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from _demo_common import call, require_healthz  # noqa: E402

BASE = os.environ.get("NAV_BRIDGE_URL", "http://127.0.0.1:8769")


def _pose(x: float, y: float) -> dict:
    return {"position": [x, y, 0.0], "orientation": [0.0, 0.0, 0.0, 1.0]}


def _goto(x: float, y: float, settle: float) -> None:
    call(BASE, "vendor.dora_nav.base.go_to_pose", pose=_pose(x, y), control_source="demo")
    time.sleep(settle)


def main() -> int:
    require_healthz(BASE)
    waypoints = [(2.0, 0.0, 7), (2.0, 2.0, 7), (-1.0, 2.0, 8), (0.0, 2.0, 6), (0.0, 0.0, 7)]
    lap = 0
    while True:
        lap += 1
        print(f"[loop] lap {lap} — patrolling", flush=True)
        for x, y, settle in waypoints:
            _goto(x, y, settle)
        # spin in place, then stop
        call(BASE, "vendor.dora_nav.base.set_velocity", linear=0.0, angular=1.0,
             control_source="demo")
        time.sleep(3)
        call(BASE, "vendor.dora_nav.base.stop")
        time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
