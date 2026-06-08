#!/usr/bin/env python3
"""Side-channel ball-pose server for the pick-and-place demo.

The octos bridge only forwards SPEC robot verbs; the ball is sim scenery, not
robot state, so it isn't on the SPEC state stream. This tiny node subscribes to
mujoco_sim/joint_positions (the full qpos vector — ball freejoint is qpos[0:3]),
keeps the latest ball xyz, and serves it on a small stdlib HTTP server so the
pick-and-place driver can aim the grasp at wherever the ball actually settled.

GET /ball -> {"x":.., "y":.., "z":.., "ts": <count>}

Non-invasive: nothing about the bridge/moveit_arm/octos contract changes.
"""
from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

_state = {"x": None, "y": None, "z": None, "ts": 0}
_lock = threading.Lock()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence access logs
        pass

    def do_GET(self):
        if self.path.rstrip("/") not in ("/ball", "/healthz"):
            self.send_response(404)
            self.end_headers()
            return
        with _lock:
            body = json.dumps(dict(_state)).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _serve(host: str, port: int) -> None:
    HTTPServer((host, port), _Handler).serve_forever()


def main() -> None:  # pragma: no cover — needs a running dora daemon
    from dora import Node

    host = os.environ.get("BALL_HTTP_HOST", "127.0.0.1")
    port = int(os.environ.get("BALL_HTTP_PORT", "8779"))
    threading.Thread(target=_serve, args=(host, port), daemon=True).start()
    print(f"[ball_state] serving ball pose on http://{host}:{port}/ball", flush=True)

    node = Node()
    for event in node:
        if event["type"] != "INPUT":
            continue
        q = event["value"].to_numpy()
        if len(q) >= 3:
            with _lock:
                _state["x"] = round(float(q[0]), 5)
                _state["y"] = round(float(q[1]), 5)
                _state["z"] = round(float(q[2]), 5)
                _state["ts"] += 1


if __name__ == "__main__":
    main()
