#!/usr/bin/env python3
"""Scripted UR5e pick-and-place of the red ball, driven over octos HTTP.

Reads the ball's live settled position from the ball_state side-server, then
drives the SPEC arm verbs (move_to_named / move_to_pose / gripper.set) through the
octos bridge (:8768) to pick it up and place it beside its start. Verifies success
by re-reading the ball pose and reporting how far it moved.

Tunable via env (so grasp depth can be iterated without code edits):
  ARM_BRIDGE_URL   (default http://127.0.0.1:8768)
  BALL_URL         (default http://127.0.0.1:8779/ball)
  APPROACH_Z       (default 0.25)  TCP height above the table for approach/lift
  GRASP_Z          (default 0.10)  TCP height when closing on the ball
  PLACE_X, PLACE_Y (default 0.30, 0.25)  where to set it down
  SETTLE_S         (default 1.0)   pause after release for the ball to settle
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from _demo_common import call, check, detail, require_healthz, say  # noqa: E402
from pick_place_poses import build_pick_place  # noqa: E402

BASE = os.environ.get("ARM_BRIDGE_URL", "http://127.0.0.1:8768")
BALL_URL = os.environ.get("BALL_URL", "http://127.0.0.1:8779/ball")
APPROACH_Z = float(os.environ.get("APPROACH_Z", "0.25"))
GRASP_Z = float(os.environ.get("GRASP_Z", "0.10"))
PLACE_X = float(os.environ.get("PLACE_X", "0.30"))
PLACE_Y = float(os.environ.get("PLACE_Y", "0.25"))
SETTLE_S = float(os.environ.get("SETTLE_S", "1.0"))


def ball_pose(tries: int = 30) -> dict | None:
    for _ in range(tries):
        try:
            with urllib.request.urlopen(BALL_URL, timeout=2) as r:
                d = json.loads(r.read().decode())
            if d.get("x") is not None:
                return d
        except OSError:
            pass
        time.sleep(0.5)
    return None


def main() -> int:
    require_healthz(BASE)

    say("read live ball position (ball_state side-server)")
    b0 = ball_pose()
    if b0 is None:
        detail("✗ no ball pose available — is the ball_state node running?")
        return 1
    detail(f"ball at ({b0['x']}, {b0['y']}, {b0['z']})")

    steps = build_pick_place(
        ball_xy=(b0["x"], b0["y"]), place_xy=(PLACE_X, PLACE_Y),
        approach_z=APPROACH_Z, grasp_z=GRASP_Z,
    )

    for s in steps:
        pos = s["args"].get("pose", {}).get("position")
        suffix = f" {pos}" if pos else ""
        say(f"{s['label']}{suffix}")
        resp = check(call(BASE, s["verb"], **s["args"]), s["label"])
        if not resp.get("ok"):
            detail(f"… step failed; continuing to observe. ({resp.get('msg')})")
        time.sleep(0.3)

    time.sleep(SETTLE_S)
    say("verify: re-read ball position")
    b1 = ball_pose()
    if b1 is None:
        detail("✗ lost ball pose")
        return 1
    detail(f"ball now ({b1['x']}, {b1['y']}, {b1['z']})")
    moved = math.hypot(b1["x"] - b0["x"], b1["y"] - b0["y"])
    to_target = math.hypot(b1["x"] - PLACE_X, b1["y"] - PLACE_Y)
    detail(f"ball moved {moved*100:.1f} cm from start; {to_target*100:.1f} cm from place target")
    if moved > 0.05:
        detail("✓ ball was relocated")
    else:
        detail("✗ ball did not move appreciably (grasp likely missed — tune GRASP_Z)")

    say("Pick-and-place complete. Inspect the MuJoCo viewer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
