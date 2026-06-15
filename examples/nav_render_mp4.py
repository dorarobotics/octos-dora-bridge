#!/usr/bin/env python3
"""Offline MP4 renderer for the nav-base toy-sim demo — no display, no dora, no rerun.

The live viewer (examples/nav_rerun_viz.py) needs an X display and the running
dora-0.2.1 dataflow. This script reproduces the SAME top-down scene headlessly:
it drives the pure `ToySim` kinematics through the same scripted sequence as
examples/nav_demo_driver.py (go to A/B/C, spin in place, stop, head to origin,
then ESTOP) and renders each frame with Pillow, piping raw RGB to ffmpeg → MP4.

Visual vocabulary matches nav_rerun_viz.py:
  - grey circles : static obstacles
  - green cross  : current goal
  - orange trail : path travelled
  - blue box     : robot body + heading arrow
  - text banner  : phase / nav_status (red on ESTOP)

Usage:
    python3 examples/nav_render_mp4.py [out.mp4]      # default: ./nav_base_demo.mp4
Deps: Pillow, ffmpeg on PATH. (numpy not required.)
"""
from __future__ import annotations

import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw

# Reuse the real, unit-tested kinematic core + obstacle set.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from nav_toy_sim import DEFAULT_OBSTACLES, ToySim  # noqa: E402

# ---- render config ----
SIZE = 720                     # px (square)
FPS = 20
DT = 0.05                      # s per sim step (matches TOY_SIM_DT default)
ROBOT_HALF = 0.25              # m (matches nav_rerun_viz ROBOT_HALF)
# World view window (metres) — covers the goals, obstacles and the start pose.
XMIN, XMAX = -2.0, 3.0
YMIN, YMAX = -2.0, 3.0
SCALE = SIZE / (XMAX - XMIN)

BG = (18, 18, 22)
GRID = (38, 38, 46)
BLUE = (70, 140, 255)
ORANGE = (255, 150, 40)
GREEN = (60, 220, 90)
GREY = (150, 150, 158)
WHITE = (235, 235, 240)
RED = (240, 70, 70)


def w2p(wx: float, wy: float) -> tuple[float, float]:
    """World (m) -> pixel (px), with +y up."""
    px = (wx - XMIN) * SCALE
    py = SIZE - (wy - YMIN) * SCALE
    return px, py


def _grid(d: ImageDraw.ImageDraw) -> None:
    x = math.ceil(XMIN)
    while x <= XMAX:
        px, _ = w2p(x, 0)
        d.line([(px, 0), (px, SIZE)], fill=GRID, width=1)
        x += 1
    y = math.ceil(YMIN)
    while y <= YMAX:
        _, py = w2p(0, y)
        d.line([(0, py), (SIZE, py)], fill=GRID, width=1)
        y += 1


def _robot_corners(x: float, y: float, theta: float):
    c, s = math.cos(theta), math.sin(theta)
    pts = []
    for dx, dy in ((ROBOT_HALF, ROBOT_HALF), (ROBOT_HALF, -ROBOT_HALF),
                   (-ROBOT_HALF, -ROBOT_HALF), (-ROBOT_HALF, ROBOT_HALF)):
        wx = x + dx * c - dy * s
        wy = y + dx * s + dy * c
        pts.append(w2p(wx, wy))
    return pts


def render_frame(sim: ToySim, trail, goal, banner, banner_color) -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)
    _grid(d)

    # obstacles (grey filled circles, true radius)
    for o in DEFAULT_OBSTACLES:
        cx, cy = w2p(o["x"], o["y"])
        r = o["radius"] * SCALE
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GREY)

    # goal (green cross)
    if goal is not None:
        gx, gy = w2p(*goal)
        d.line([(gx - 11, gy), (gx + 11, gy)], fill=GREEN, width=3)
        d.line([(gx, gy - 11), (gx, gy + 11)], fill=GREEN, width=3)

    # trail (orange polyline)
    if len(trail) > 1:
        d.line([w2p(tx, ty) for tx, ty in trail], fill=ORANGE, width=2)

    # robot body (blue box) + heading arrow
    d.polygon(_robot_corners(sim.x, sim.y, sim.theta), outline=BLUE, fill=(40, 70, 130))
    hx, hy = w2p(sim.x + 0.45 * math.cos(sim.theta), sim.y + 0.45 * math.sin(sim.theta))
    bx, by = w2p(sim.x, sim.y)
    d.line([(bx, by), (hx, hy)], fill=ORANGE, width=3)

    # banner
    d.text((12, 10), banner, fill=banner_color)
    d.text((12, 26), f"nav_status: {sim.status}", fill=WHITE)
    return img


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "nav_base_demo.mp4"
    out = os.path.abspath(out)

    sim = ToySim()
    trail: list[tuple[float, float]] = []

    # (banner, action, seconds) — mirrors examples/nav_demo_driver.py
    GOAL, VEL, STOP, ESTOP, IDLE = "goal", "vel", "stop", "estop", "idle"
    phases = [
        ("idle — static map + obstacles", (IDLE, None), 1.0),
        ("go_to_pose -> A (2.0, 0.0)", (GOAL, (2.0, 0.0)), 7.0),
        ("go_to_pose -> B (2.0, 2.0)", (GOAL, (2.0, 2.0)), 7.0),
        ("go_to_pose -> C (-1.0, 2.0)", (GOAL, (-1.0, 2.0)), 9.0),
        ("set_velocity -> spin 1.0 rad/s", (VEL, (0.0, 1.0)), 3.0),
        ("stop", (STOP, None), 1.5),
        ("go_to_pose -> origin (0.0, 0.0)", (GOAL, (0.0, 0.0)), 2.5),
        ("robot.estop -- base halted", (ESTOP, None), 2.5),
    ]

    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-f", "rawvideo", "-pixel_format", "rgb24",
         "-video_size", f"{SIZE}x{SIZE}", "-framerate", str(FPS), "-i", "-",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-loglevel", "error", out],
        stdin=subprocess.PIPE,
    )
    assert ff.stdin is not None

    goal = None
    n_frames = 0
    estopped = False
    for banner, (kind, arg), secs in phases:
        if kind == GOAL:
            sim.set_goal(*arg)
            goal = arg
        elif kind == VEL:
            sim.set_velocity(*arg)
            goal = None
        elif kind == STOP:
            sim.set_velocity(0.0, 0.0)
            goal = None
        elif kind == ESTOP:
            sim.cancel()
            goal = None
            estopped = True
        # else IDLE: leave the sim as-is

        color = RED if estopped else WHITE
        for _ in range(int(secs / DT)):
            if not estopped:
                sim.step(DT)
                trail.append((sim.x, sim.y))
            img = render_frame(sim, trail, goal, banner, color)
            ff.stdin.write(img.tobytes())
            n_frames += 1

    ff.stdin.close()
    ff.wait()
    print(f"wrote {out}  ({n_frames} frames, {n_frames / FPS:.1f}s @ {FPS}fps)")
    return ff.returncode


if __name__ == "__main__":
    raise SystemExit(main())
