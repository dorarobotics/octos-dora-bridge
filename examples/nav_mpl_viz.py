#!/usr/bin/env python3
"""Matplotlib (TkAgg) top-down viewer for the nav-base toy sim.

A plain raster Tk window that remote-desktop tools (RustDesk/VNC) capture
reliably — unlike the GL-based rerun viewer, whose software-Vulkan surface shows
black over RustDesk on a GPU-less box. Subscribes to the same dora streams as
nav_rerun_viz.py: pose / goal / obstacles / status / safety_event.
"""
from __future__ import annotations

import json
import math
from collections import deque

import matplotlib

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Polygon  # noqa: E402

from dora import Node  # noqa: E402

TRAIL_MAX = 300


def _decode(value):
    try:
        lst = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
    except Exception:
        return None
    if not lst:
        return None
    first = lst[0]
    if isinstance(first, str):
        try:
            return json.loads(first)
        except Exception:
            return None
    return first


def _robot_corners(x, y, theta, L=0.5, W=0.35):
    c, s = math.cos(theta), math.sin(theta)
    base = [(-L / 2, -W / 2), (L / 2, -W / 2), (L / 2, W / 2), (-L / 2, W / 2)]
    return [(x + px * c - py * s, y + px * s + py * c) for px, py in base]


def main():
    plt.ion()
    fig, ax = plt.subplots(figsize=(7, 7))
    try:
        fig.canvas.manager.set_window_title("nav-base toy sim")
    except Exception:
        pass
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlim(-4, 4)
    ax.set_ylim(-4, 4)
    title = ax.set_title("waiting for data…")

    robot = Polygon([(0, 0)], closed=True, facecolor="#2878ff", edgecolor="#0a3aa0", zorder=4)
    ax.add_patch(robot)
    (heading,) = ax.plot([], [], "-", color="#00d0ff", lw=2.5, zorder=5)
    (trail_line,) = ax.plot([], [], "-", color="#ff9600", lw=1.5, alpha=0.7, zorder=2)
    (goal_pt,) = ax.plot([], [], "*", color="#00cc00", markersize=20, zorder=6)
    (obst_pts,) = ax.plot([], [], "o", color="#888888", markersize=10, zorder=3)
    fig.tight_layout()
    fig.show()
    fig.canvas.flush_events()

    node = Node()
    trail = deque(maxlen=TRAIL_MAX)
    status = "idle"
    estopped = False
    print("[mpl] viewer ready — waiting for data…", flush=True)

    for event in node:
        if event["type"] == "STOP":
            break
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        data = _decode(event["value"])

        if eid == "pose" and isinstance(data, dict):
            x, y = float(data["x"]), float(data["y"])
            th = float(data.get("theta", 0.0))
            trail.append((x, y))
            robot.set_xy(_robot_corners(x, y, th))
            heading.set_data([x, x + 0.6 * math.cos(th)], [y, y + 0.6 * math.sin(th)])
            if len(trail) > 1:
                trail_line.set_data([p[0] for p in trail], [p[1] for p in trail])
            title.set_text(("ESTOP — " if estopped else "") + f"nav_status: {status}")
            title.set_color("red" if estopped else "black")
            fig.canvas.draw_idle()
            fig.canvas.flush_events()
        elif eid == "goal":
            tgt = None
            if isinstance(data, dict):
                pos = data.get("position")
                if isinstance(pos, list) and len(pos) >= 2:
                    tgt = [float(pos[0]), float(pos[1])]
                elif "x" in data:
                    tgt = [float(data["x"]), float(data["y"])]
            if tgt is not None:
                goal_pt.set_data([tgt[0]], [tgt[1]])
                fig.canvas.draw_idle()
                fig.canvas.flush_events()
        elif eid == "obstacles" and isinstance(data, list):
            pts = [(float(o["x"]), float(o["y"])) for o in data if "x" in o]
            if pts:
                obst_pts.set_data([p[0] for p in pts], [p[1] for p in pts])
        elif eid == "status" and isinstance(data, str):
            status = data
        elif eid == "safety_event" and isinstance(data, dict):
            estopped = data.get("kind") in ("estop", "heartbeat_timeout")


if __name__ == "__main__":
    main()
