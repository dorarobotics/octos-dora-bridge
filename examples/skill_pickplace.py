#!/usr/bin/env python3
"""Deterministic skill-level pick-and-place — the octos skill layer WITHOUT the LLM.

Calls arm_skills.{get_ball_position,get_plate_position,pick_at,place_at} in a fixed
sequence (the same functions the octos agent sequences). Use this to validate /
tune the robot geometry (pinch site, HOME, grasp heights) without LLM variance,
then switch to arm_agent.py for the full agentic demo.

Env: same as arm_skills (MODEL_NAME, ARM_BRIDGE_URL, BALL_URL, PLATE_X/Y, ARM_HOME,
GRASP_Z, PLACE_Z, APPROACH_Z, LIFT_ZS, GRIP_OPEN_W, GRIP_CLOSE_W).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(__file__))

import arm_skills  # noqa: E402


def _xy(s: str):
    m = dict(re.findall(r"([xy])=([-\d.]+)", s))
    return float(m["x"]), float(m["y"])


def main() -> int:
    print("[skill] reading object position…", flush=True)
    obj = arm_skills.get_ball_position()
    print(f"[skill]   object: {obj}", flush=True)
    if obj.startswith("ERROR"):
        return 1
    ox, oy = _xy(obj)

    plate = arm_skills.get_plate_position()
    print(f"[skill]   plate:  {plate}", flush=True)
    px, py = _xy(plate)

    print(f"[skill] pick_at({ox:.3f}, {oy:.3f})…", flush=True)
    print(f"[skill]   {arm_skills.pick_at(ox, oy)}", flush=True)

    print(f"[skill] place_at({px:.3f}, {py:.3f})…", flush=True)
    print(f"[skill]   {arm_skills.place_at(px, py)}", flush=True)

    print("[skill] done.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
