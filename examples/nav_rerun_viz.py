#!/usr/bin/env python3
"""Rerun viewer for the nav-base toy-sim — a top-down 2D map.

Spawns a rerun viewer (matching dora-nav's python/rerun_viz_node.py convention,
`rr.init(spawn=True)`) and renders, in a world top-down frame:
  - grey points:  static obstacles
  - green cross:  current goal
  - orange trail: the base's travelled path
  - blue box:     the robot body + a heading arrow
  - text log:     nav_status / estop banner

It subscribes to the same streams nav_base exchanges with the toy sim, so what
you see is exactly what the nav-base verbs drove over octos HTTP.
"""
from __future__ import annotations

import json
import math
import os
from collections import deque
from typing import Any

import numpy as np
import rerun as rr

ROBOT_HALF = 0.25  # m — half-extent of the drawn robot body
TRAIL_MAX = 800


def _decode(value: Any) -> Any:
    items = value.to_pylist() if hasattr(value, "to_pylist") else list(value)
    if not items:
        return None
    return json.loads(items[0]) if isinstance(items[0], str) else items[0]


def _robot_corners(x: float, y: float, theta: float) -> np.ndarray:
    """Four corners of the robot body box, rotated by theta, as a closed loop."""
    h = ROBOT_HALF
    local = np.array([[h, h], [-h, h], [-h, -h], [h, -h], [h, h]], dtype=np.float32)
    c, s = math.cos(theta), math.sin(theta)
    rot = np.array([[c, -s], [s, c]], dtype=np.float32)
    return (local @ rot.T) + np.array([x, y], dtype=np.float32)


def _ensure_viewer_on_path() -> None:
    """dora launches this node via the conda python's absolute path, so the env's
    bin/ (with the `rerun` viewer) isn't on PATH. The wheel bundles the viewer at
    rerun_sdk/rerun_cli/rerun — prepend that dir so rr.spawn() can find it."""
    cli = os.path.join(os.path.dirname(os.path.dirname(rr.__file__)), "rerun_cli")
    if os.path.isdir(cli):
        os.environ["PATH"] = cli + os.pathsep + os.environ.get("PATH", "")


def main() -> None:  # pragma: no cover — needs a running dora daemon + display
    from dora import Node

    _ensure_viewer_on_path()
    rr.init("nav_base_toy_sim", spawn=True)

    node = Node()
    trail: deque[list[float]] = deque(maxlen=TRAIL_MAX)
    pose = {"x": 0.0, "y": 0.0, "theta": 0.0}
    status = "idle"
    estopped = False

    print("[rerun] nav toy-sim viewer ready — waiting for data…", flush=True)

    for event in node:
        if event["type"] == "STOP":
            break
        if event["type"] != "INPUT":
            continue
        eid = event["id"]
        data = _decode(event["value"])

        if eid == "pose" and isinstance(data, dict):
            pose = data
            x, y = float(pose["x"]), float(pose["y"])
            theta = float(pose.get("theta", 0.0))
            trail.append([x, y])
            rr.log("world/robot/body", rr.LineStrips2D(
                [_robot_corners(x, y, theta)], colors=[[40, 120, 255]], radii=[0.03]))
            rr.log("world/robot/heading", rr.Arrows2D(
                origins=[[x, y]],
                vectors=[[0.5 * math.cos(theta), 0.5 * math.sin(theta)]],
                colors=[[0, 200, 255]]))
            if len(trail) > 1:
                rr.log("world/trail", rr.LineStrips2D(
                    [list(trail)], colors=[[255, 150, 0]], radii=[0.02]))
        elif eid == "goal":
            tgt = None
            if isinstance(data, dict):
                pos = data.get("position")
                if isinstance(pos, list) and len(pos) >= 2:
                    tgt = [float(pos[0]), float(pos[1])]
                elif "x" in data:
                    tgt = [float(data["x"]), float(data["y"])]
            if tgt is not None:
                rr.log("world/goal", rr.Points2D(
                    [tgt], colors=[[0, 220, 0]], radii=[0.15]))
        elif eid == "obstacles" and isinstance(data, list):
            pts = [[float(o["x"]), float(o["y"])] for o in data if "x" in o]
            radii = [float(o.get("radius", 0.2)) for o in data if "x" in o]
            if pts:
                rr.log("world/obstacles", rr.Points2D(
                    pts, colors=[[150, 150, 150]], radii=radii))
        elif eid == "status" and isinstance(data, str):
            status = data
        elif eid == "safety_event" and isinstance(data, dict):
            estopped = data.get("kind") in ("estop", "heartbeat_timeout")

        banner = f"ESTOP ({status})" if estopped else f"nav_status: {status}"
        rr.log("world/banner", rr.TextLog(
            banner, level="ERROR" if estopped else "INFO"))


if __name__ == "__main__":
    main()
