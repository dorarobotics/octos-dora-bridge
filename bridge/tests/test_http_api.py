from __future__ import annotations

import threading
import time
from concurrent.futures import Future
from typing import Optional

import pytest
from fastapi.testclient import TestClient

from octos_spec_bridge.http_api import create_app
from octos_spec_bridge.state_cache import StateCache


class FakeDoraLoop:
    """Test double for DoraLoop — captures publishes, returns canned advert."""

    def __init__(self, advert: Optional[dict] = None) -> None:
        self._advert = advert
        self.published: list[dict] = []
        self._pending: dict[str, Future] = {}
        self._cache = StateCache()

    def advert(self) -> Optional[dict]:
        return self._advert

    def set_advert(self, advert: dict) -> None:
        self._advert = advert

    def register_pending(self, request_id: str) -> Future:
        fut: Future = Future()
        self._pending[request_id] = fut
        return fut

    def cancel_pending(self, request_id: str) -> None:
        self._pending.pop(request_id, None)

    def publish_cmd_request(self, envelope: dict) -> None:
        self.published.append(envelope)

    def resolve(self, request_id: str, response: dict) -> None:
        """Test helper — simulate a vendor cmd_response."""
        fut = self._pending.pop(request_id, None)
        if fut is not None and not fut.done():
            fut.set_result(response)


@pytest.fixture
def fake_loop(sample_advert) -> FakeDoraLoop:
    return FakeDoraLoop(advert=sample_advert)


@pytest.fixture
def client(fake_loop) -> TestClient:
    app = create_app(
        dora_loop=fake_loop,
        state_cache=fake_loop._cache,
        robot_id="agibot-a2-001",
        cmd_timeout_s=2.0,
    )
    return TestClient(app)


def test_healthz_returns_200(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_healthz_503_when_advert_not_ready(fake_loop):
    fake_loop.set_advert(None)
    app = create_app(
        dora_loop=fake_loop,
        state_cache=fake_loop._cache,
        robot_id="agibot-a2-001",
        cmd_timeout_s=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/healthz")
        assert r.status_code == 503
        assert r.json()["status"] == "advert_pending"


def test_tools_returns_one_entry_per_verb_plus_synthetics(client):
    r = client.get("/tools")
    assert r.status_code == 200
    body = r.json()
    names = [t["name"] for t in body["tools"]]
    # sample_advert has 4 verbs + 2 synthetic = 6
    assert "robot.heartbeat" in names
    assert "robot.estop" in names
    assert "vendor.agibot.a2.motion.set_action" in names
    assert "vendor.agibot.a2.audio.tts" in names
    assert "get_state" in names
    assert "get_recent_safety_events" in names
    assert len(names) == 6


def test_tools_synthesizes_descriptions(client):
    r = client.get("/tools")
    body = r.json()
    by_name = {t["name"]: t for t in body["tools"]}
    assert by_name["robot.heartbeat"]["description"] == (
        "Common verb robot.heartbeat per SPEC-VENDOR-NODE-V1 §8.1"
    )
    assert by_name["vendor.agibot.a2.motion.set_action"]["description"] == (
        "Vendor verb: motion.set_action on agibot a2 (see capabilities advert for params)"
    )


def test_tools_returns_503_when_advert_pending(fake_loop):
    fake_loop.set_advert(None)
    app = create_app(
        dora_loop=fake_loop,
        state_cache=fake_loop._cache,
        robot_id="agibot-a2-001",
        cmd_timeout_s=2.0,
    )
    with TestClient(app) as client:
        r = client.get("/tools")
        assert r.status_code == 503


def test_post_tool_happy_path(client, fake_loop):
    """POST /tools/<name> publishes envelope and resolves on cmd_response."""

    # Arrange: spawn a thread that responds to whatever request_id appears.
    def responder() -> None:
        deadline = time.monotonic() + 2.0
        while not fake_loop.published and time.monotonic() < deadline:
            time.sleep(0.01)
        req_id = fake_loop.published[0]["request_id"]
        fake_loop.resolve(
            req_id,
            {
                "envelope_version": "1.0",
                "spec_version": "1.0.0",
                "request_id": req_id,
                "ok": True,
                "code": "0",
                "msg": "",
                "ts": "2026-05-23T10:00:00.000Z",
                "data": {"applied": True},
            },
        )

    t = threading.Thread(target=responder, daemon=True)
    t.start()

    r = client.post(
        "/tools/vendor.agibot.a2.motion.set_action",
        json={"args": {"action": "RL_LOCOMOTION_DEFAULT"}},
    )
    t.join(timeout=3.0)

    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["code"] == "0"
    assert body["data"] == {"applied": True}

    # And the cmd_request had the right shape.
    assert len(fake_loop.published) == 1
    env = fake_loop.published[0]
    assert env["verb"] == "vendor.agibot.a2.motion.set_action"
    assert env["target"] == "agibot-a2-001"
    assert env["params"] == {"action": "RL_LOCOMOTION_DEFAULT"}
    assert env["auth"] == {"cmd_token": "octos-bridge"}


def test_post_tool_unknown_verb_returns_404(client):
    r = client.post("/tools/not.a.real.verb", json={"args": {}})
    assert r.status_code == 404
    assert r.json()["code"] == "VERB_UNKNOWN"


def test_post_tool_timeout_returns_504(client, fake_loop):
    """If no cmd_response arrives within cmd_timeout_s, return 504."""
    # No responder thread — request will time out.
    r = client.post(
        "/tools/robot.heartbeat",
        json={"args": {}},
    )
    assert r.status_code == 504
    body = r.json()
    assert body["ok"] is False
    assert body["code"] == "BRIDGE_TIMEOUT"
    assert "request_id" in body
    # And the pending future was cleaned up.
    assert fake_loop._pending == {}


def test_post_tool_vendor_error_passes_through(client, fake_loop):
    """A non-ok cmd_response must be returned with status 200 (HTTP-level OK,
    application-level !ok). Octos's tool runner reads body.ok/code, not HTTP status."""

    def responder() -> None:
        deadline = time.monotonic() + 2.0
        while not fake_loop.published and time.monotonic() < deadline:
            time.sleep(0.01)
        req_id = fake_loop.published[0]["request_id"]
        fake_loop.resolve(
            req_id,
            {
                "envelope_version": "1.0",
                "spec_version": "1.0.0",
                "request_id": req_id,
                "ok": False,
                "code": "CONTROLLER_BUSY",
                "msg": "controller slot held by another caller",
                "ts": "2026-05-23T10:00:00.000Z",
                "data": {},
            },
        )

    t = threading.Thread(target=responder, daemon=True)
    t.start()
    r = client.post("/tools/robot.heartbeat", json={"args": {}})
    t.join(timeout=3.0)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["code"] == "CONTROLLER_BUSY"
    assert body["msg"] == "controller slot held by another caller"


def test_post_tool_missing_args_body_treated_as_empty(client, fake_loop):
    """POST with no args still goes through; args defaults to {}."""

    def responder() -> None:
        deadline = time.monotonic() + 2.0
        while not fake_loop.published and time.monotonic() < deadline:
            time.sleep(0.01)
        req_id = fake_loop.published[0]["request_id"]
        fake_loop.resolve(
            req_id,
            {
                "request_id": req_id,
                "ok": True,
                "code": "0",
                "msg": "",
                "data": {},
            },
        )

    t = threading.Thread(target=responder, daemon=True)
    t.start()
    r = client.post("/tools/robot.heartbeat", json={})
    t.join(timeout=3.0)
    assert r.status_code == 200
    assert fake_loop.published[0]["params"] == {}


def test_post_get_state_returns_cache_snapshot(client, fake_loop):
    fake_loop._cache.set_state(
        {
            "seq": 5,
            "payload": {"a2_action": "DEFAULT"},
        }
    )
    r = client.post("/tools/get_state", json={"args": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["stream"]["seq"] == 5
    assert body["data"]["stale"] is False


def test_post_get_state_empty_cache(client):
    r = client.post("/tools/get_state", json={"args": {}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["data"]["stream"] is None
    assert body["data"]["stale"] is True


def test_post_get_recent_safety_events_filters_by_since(client, fake_loop):
    for i in range(1, 4):
        fake_loop._cache.append_safety_event({"seq": i, "payload": {"event": f"e{i}"}})
    r = client.post("/tools/get_recent_safety_events", json={"args": {"since": 1}})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert [e["seq"] for e in body["data"]["events"]] == [2, 3]


def test_post_get_recent_safety_events_default_since(client, fake_loop):
    """Missing 'since' defaults to 0 — return everything."""
    fake_loop._cache.append_safety_event({"seq": 1, "payload": {}})
    r = client.post("/tools/get_recent_safety_events", json={"args": {}})
    assert r.status_code == 200
    assert len(r.json()["data"]["events"]) == 1


def test_main_module_imports_without_dora_at_import_time():
    """__main__ must not import dora at module top — it does so lazily in main().
    This lets test environments without a dora coordinator still collect the file."""
    import octos_spec_bridge.__main__ as m  # noqa: F401

    assert hasattr(m, "main")


def test_get_tools_includes_safety_tier_from_advert(fake_loop):
    """GET /tools propagates safety_tier from the cached advert (SPEC-V1 1.1)."""
    advert = {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "robot_id": "agibot-a2-001",
        "vendor": "agibot",
        "model": "a2",
        "commands": [
            {"verb": "robot.heartbeat", "safety_tier": "observe"},
            {"verb": "robot.estop", "safety_tier": "emergency_override"},
            {"verb": "vendor.agibot.a2.motion.set_action", "safety_tier": "safe_motion"},
        ],
    }
    fake_loop.set_advert(advert)
    app = create_app(
        dora_loop=fake_loop,
        state_cache=fake_loop._cache,
        robot_id="agibot-a2-001",
        cmd_timeout_s=2.0,
    )
    client = TestClient(app)

    resp = client.get("/tools")
    assert resp.status_code == 200
    tools = {t["name"]: t for t in resp.json()["tools"]}

    assert tools["robot.heartbeat"]["safety_tier"] == "observe"
    assert tools["robot.estop"]["safety_tier"] == "emergency_override"
    assert tools["vendor.agibot.a2.motion.set_action"]["safety_tier"] == "safe_motion"


def test_get_tools_omits_safety_tier_for_verbs_lacking_it(fake_loop):
    """Pre-SPEC-V1 1.1 adverts (no safety_tier) → catalog entries also omit the field.

    Consumers fall back to their own skill-level default. This preserves
    backward-compat during the 1.0 → 1.1 migration window.
    """
    advert = {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "robot_id": "agibot-a2-001",
        "vendor": "agibot",
        "model": "a2",
        "commands": [
            {"verb": "robot.heartbeat"}  # no safety_tier
        ],
    }
    fake_loop.set_advert(advert)
    app = create_app(
        dora_loop=fake_loop,
        state_cache=fake_loop._cache,
        robot_id="agibot-a2-001",
        cmd_timeout_s=2.0,
    )
    client = TestClient(app)

    resp = client.get("/tools")
    tools = {t["name"]: t for t in resp.json()["tools"]}
    assert "safety_tier" not in tools["robot.heartbeat"], (
        f"bridge should not invent a default; entry={tools['robot.heartbeat']}"
    )
