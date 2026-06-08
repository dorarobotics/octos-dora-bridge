#!/usr/bin/env python3
"""UR5e pick-and-place of the red ball via JOINT-SPACE waypoints, over octos HTTP.

dora-moveit2's Cartesian move_to_pose IK is unreliable (the gripper misses
commanded targets), so the grasp waypoints are precomputed offline against the
MuJoCo model by ik_solve_grasp.py (written to grasp_configs.json) and driven here
with the verified move_to_joint_state verb. Verifies relocation by reading the
ball's live pose from the ball_state side-server.

Env:
  ARM_BRIDGE_URL (http://127.0.0.1:8768), BALL_URL (http://127.0.0.1:8779/ball)
  GRASP_CONFIGS  (/home/demo/dorarobotics-test/grasp_configs.json)
  CLOSE_WIDTH    (0.0)   gripper width when gripping the ball
  PLACE_X,PLACE_Y(0.30,0.25)  expected place location (for the verify report)
  SETTLE_S       (1.5)
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

BASE = os.environ.get("ARM_BRIDGE_URL", "http://127.0.0.1:8768")
BALL_URL = os.environ.get("BALL_URL", "http://127.0.0.1:8779/ball")
CONFIGS = os.environ.get("GRASP_CONFIGS", "/home/demo/dorarobotics-test/grasp_configs.json")
CLOSE_WIDTH = float(os.environ.get("CLOSE_WIDTH", "0.0"))
PLACE_X = float(os.environ.get("PLACE_X", "0.25"))
PLACE_Y = float(os.environ.get("PLACE_Y", "0.0"))
SETTLE_S = float(os.environ.get("SETTLE_S", "1.5"))

MOVE = "vendor.moveit.arm.move_to_joint_state"
NAMED = "vendor.moveit.arm.move_to_named"
GRIP = "vendor.moveit.arm.gripper.set"


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


def wait_settled(timeout_s: float = 15.0) -> dict | None:
    """Poll until the ball stops moving (it spawns mid-air and rolls before
    resting near the table). Returns the settled pose."""
    prev = None
    stable = 0
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        b = ball_pose(tries=2)
        if b and prev is not None:
            d = math.hypot(b["x"] - prev["x"], b["y"] - prev["y"]) + abs(b["z"] - prev["z"])
            if d < 0.003 and b["z"] < 0.05:
                stable += 1
                if stable >= 3:
                    return b
            else:
                stable = 0
        prev = b
        time.sleep(0.4)
    return prev


def _ballz(tag: str) -> None:
    b = ball_pose(tries=3)
    if b:
        detail(f"  ball@{tag}: ({b['x']:.3f}, {b['y']:.3f}, {b['z']:.3f})")


def joints(label: str, q: list[float], track: bool = False) -> None:
    say(f"{label}  {[round(v, 2) for v in q]}")
    check(call(BASE, MOVE, joints=q, control_source="pickplace"), label)
    time.sleep(0.3)
    if track:
        _ballz(label)


def grip(label: str, width: float, dwell: float = 0.6) -> None:
    say(f"{label} (width={width})")
    check(call(BASE, GRIP, width=width), label)
    # The gripper is non-deferred: the verb returns immediately but the pads take
    # ~1.5-2s of sim time to physically clamp. Dwell here so we don't start lifting
    # while it's still closing (that catches the ball high with a weak grip that
    # then rolls off mid-carry).
    time.sleep(dwell)


def main() -> int:
    require_healthz(BASE)
    with open(CONFIGS) as f:
        cfg = json.load(f)

    say("wait for the ball to settle, then read its position")
    b0 = wait_settled()
    detail(f"ball settled at ({b0['x']}, {b0['y']}, {b0['z']})" if b0 else "no ball pose")

    say("move_to_named → home")
    check(call(BASE, NAMED, name="home", control_source="pickplace"), "home")
    grip("open gripper", 0.085)
    joints("above ball", cfg["above_ball"], track=True)
    joints("descend to ball", cfg["at_ball"], track=True)
    grip("close on ball", CLOSE_WIDTH, dwell=float(os.environ.get("GRIP_DWELL", "3.0")))
    _ballz("after close (pre-lift)")
    joints("lift a", cfg["lift_a"], track=True)
    joints("lift b", cfg["lift_b"], track=True)
    joints("lift", cfg["lift"])
    bl = ball_pose(tries=4)
    if bl:
        detail(f"ball after lift: z={bl['z']:.3f}  ->  {'GRASPED (lifted)' if bl['z'] > 0.10 else 'NOT lifted (grasp missed)'}")
    carry_keys = sorted((k for k in cfg if k.startswith("carry")),
                        key=lambda k: int(k[5:]))
    for k in carry_keys:
        joints(f"carry {k[5:]}", cfg[k], track=True)
    joints("carry above place", cfg["above_place"], track=True)
    joints("descend to place", cfg["at_place"], track=True)
    grip("release", 0.085)
    joints("retract", cfg["above_place"])
    say("move_to_named → home")
    check(call(BASE, NAMED, name="home", control_source="pickplace"), "home")

    time.sleep(SETTLE_S)
    say("verify: re-read ball position")
    b1 = ball_pose()
    if b0 and b1:
        detail(f"ball now ({b1['x']}, {b1['y']}, {b1['z']})")
        moved = math.hypot(b1["x"] - b0["x"], b1["y"] - b0["y"])
        to_target = math.hypot(b1["x"] - PLACE_X, b1["y"] - PLACE_Y)
        detail(f"ball moved {moved*100:.1f} cm; {to_target*100:.1f} cm from place target ({PLACE_X},{PLACE_Y})")
        if to_target < 0.10:
            detail("✓ ball placed at target")
        elif moved > 0.05:
            detail("~ ball moved but not to target (tune grasp/place height)")
        else:
            detail("✗ ball did not move (grasp missed — tune at_ball height / CLOSE_WIDTH)")
    say("Pick-and-place complete. Inspect the MuJoCo viewer.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
