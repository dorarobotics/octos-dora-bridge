"""End-to-end smoke: real dora dataflow + agibot-a2-dora-node with FakeHttpClient.

Requires `dora-cli` on PATH and `agibot-a2-dora-node` installed in the venv.
Run with `pytest tests/test_e2e_fake_http.py -v -s` from the repo root.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

import httpx
import pytest

BRIDGE_URL = "http://127.0.0.1:18765"
DATAFLOW = "dataflows/a2-bridge-fake.yaml"


def _have_dora() -> bool:
    return shutil.which("dora") is not None


pytestmark = pytest.mark.skipif(not _have_dora(), reason="dora CLI not installed")


@pytest.fixture(scope="module")
def dora_dataflow():
    # Fresh daemon so it starts in this process's env.
    subprocess.run(["dora", "destroy"], capture_output=True)
    subprocess.run(["dora", "up"], check=True, capture_output=True)
    proc = subprocess.Popen(
        ["dora", "start", DATAFLOW, "--attach"],
        cwd=os.path.dirname(os.path.dirname(__file__)) or ".",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for /healthz to come up (up to 30 s).
    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{BRIDGE_URL}/healthz", timeout=2.0)
            if r.status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    else:
        proc.terminate()
        raise RuntimeError("bridge /healthz never came up within 30s")
    yield
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
    subprocess.run(["dora", "destroy"], capture_output=True)


def test_healthz(dora_dataflow):
    r = httpx.get(f"{BRIDGE_URL}/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_tools_catalog_includes_expected_verbs(dora_dataflow):
    r = httpx.get(f"{BRIDGE_URL}/tools")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["tools"]}
    # agibot-a2-dora-node advertises 22 verbs + 2 synthetic = 24
    assert "robot.heartbeat" in names
    assert "robot.estop" in names
    assert "vendor.agibot.a2.motion.set_action" in names
    assert "get_state" in names
    assert "get_recent_safety_events" in names
    assert len(names) >= 22


def test_heartbeat_round_trip(dora_dataflow):
    r = httpx.post(f"{BRIDGE_URL}/tools/robot.heartbeat", json={"args": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["code"] == "0"
    assert body["data"]["ok"] is True


def test_set_action_fakehttp(dora_dataflow):
    r = httpx.post(
        f"{BRIDGE_URL}/tools/vendor.agibot.a2.motion.set_action",
        json={"args": {"action": "RL_LOCOMOTION_DEFAULT"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["applied"] is True


def test_get_state_works_after_a_second(dora_dataflow):
    # Vendor polls state at 1 Hz; wait for at least one cycle.
    time.sleep(1.5)
    r = httpx.post(f"{BRIDGE_URL}/tools/get_state", json={"args": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["stream"] is not None
    assert body["data"]["stale"] is False
