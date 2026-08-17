"""Behavioral test for the octos lekiwi tool binary (skills/lekiwi/main).

Spins up a stdlib HTTP stub standing in for the nav-base bridge, then runs the
`main` binary as a subprocess (exactly how octos invokes it) and asserts the
emitted {"output","success"} JSON and that the expected bridge verbs were hit.
No mujoco/dora needed.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

HERE = os.path.dirname(__file__)
MAIN = os.path.join(HERE, "..", "skills", "lekiwi", "main")

_hits: list[str] = []


class _Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass

    def do_POST(self):
        _hits.append(self.path)
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        body = {"ok": True, "code": "0", "data": {"pose": {"x": 0.6, "y": 0.0, "theta": 0.0}}}
        self.wfile.write(json.dumps(body).encode())


@pytest.fixture()
def stub():
    _hits.clear()
    srv = HTTPServer(("127.0.0.1", 0), _Stub)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _run(tool: str, args: dict, base: str) -> dict:
    env = dict(os.environ, LEKIWI_BRIDGE_URL=base)
    p = subprocess.run(
        [sys.executable, MAIN, tool],
        input=json.dumps(args).encode(),
        capture_output=True,
        env=env,
        timeout=20,
    )
    assert p.returncode == 0, p.stderr.decode()
    return json.loads(p.stdout.decode())


def test_get_base_pose(stub):
    out = _run("get_base_pose", {}, stub)
    assert out["success"] is True
    assert "0.6" in out["output"]
    assert any("localization.get_pose" in h for h in _hits)


def test_move_base_sets_velocity_then_stops(stub):
    out = _run("move_base", {"linear": 0.3, "angular": 0.0, "seconds": 0}, stub)
    assert out["success"] is True
    assert any("base.set_velocity" in h for h in _hits)
    assert any("base.stop" in h for h in _hits)


def test_stop_base(stub):
    out = _run("stop_base", {}, stub)
    assert out["success"] is True
    assert any("base.stop" in h for h in _hits)


def test_unknown_tool_fails_gracefully(stub):
    out = _run("bogus", {}, stub)
    assert out["success"] is False
