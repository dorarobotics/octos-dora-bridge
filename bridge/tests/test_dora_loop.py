from __future__ import annotations

import json
import time

import pyarrow as pa

from octos_spec_bridge.dora_loop import DoraLoop
from octos_spec_bridge.state_cache import StateCache


def _encode(envelope: dict) -> pa.Array:
    return pa.array([json.dumps(envelope)])


def test_advert_is_captured_from_capabilities_input(fake_node, sample_advert):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        fake_node.push_input("capabilities", _encode(sample_advert))
        # Wait for the loop to consume — bounded poll.
        deadline = time.monotonic() + 2.0
        while loop.advert() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert loop.advert() == sample_advert
    finally:
        loop.stop()


def test_state_envelope_routed_to_state_cache(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        state = {"seq": 7, "payload": {"a2_action": "DEFAULT"}}
        fake_node.push_input("state", _encode(state))
        deadline = time.monotonic() + 2.0
        while cache.snapshot()["stream"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cache.snapshot()["stream"] == state
    finally:
        loop.stop()


def test_safety_event_appended_to_ring(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        evt = {"seq": 1, "payload": {"event": "vendor_unreachable"}}
        fake_node.push_input("safety_event", _encode(evt))
        deadline = time.monotonic() + 2.0
        while not cache.events_since(0) and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cache.events_since(0) == [evt]
    finally:
        loop.stop()


def test_cmd_response_resolves_pending_future(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        fut = loop.register_pending("req-42")
        response = {
            "request_id": "req-42",
            "ok": True,
            "code": "0",
            "msg": "",
            "data": {"applied": True},
        }
        fake_node.push_input("cmd_response", _encode(response))
        # Future resolves within timeout.
        result = fut.result(timeout=2.0)
        assert result == response
    finally:
        loop.stop()


def test_publish_cmd_request_sends_via_node(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        env = {"verb": "robot.heartbeat", "request_id": "abc"}
        loop.publish_cmd_request(env)
        # Sent immediately (no thread hop needed for publishing).
        assert len(fake_node.sent) == 1
        sent = fake_node.sent[0]
        assert sent.output_id == "cmd_request"
        assert json.loads(sent.value.to_pylist()[0]) == env
    finally:
        loop.stop()


def test_unknown_request_id_in_response_is_ignored(fake_node):
    """Late/orphan cmd_response (e.g. after timeout) must not crash the loop."""
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        response = {
            "request_id": "never-registered",
            "ok": True,
            "code": "0",
            "msg": "",
            "data": {},
        }
        fake_node.push_input("cmd_response", _encode(response))
        # Give the loop time to process; nothing should crash.
        time.sleep(0.1)
        # Subsequent traffic still works.
        fake_node.push_input("state", _encode({"seq": 1, "payload": {}}))
        deadline = time.monotonic() + 2.0
        while cache.snapshot()["stream"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert cache.snapshot()["stream"]["seq"] == 1
    finally:
        loop.stop()


def test_register_pending_duplicate_warns_and_overwrites(fake_node, caplog):
    """Duplicate request_id logs a warning (prior caller will time out)."""
    import logging

    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        fut1 = loop.register_pending("dup-id")
        with caplog.at_level(logging.WARNING):
            fut2 = loop.register_pending("dup-id")
        assert any("duplicate request_id" in r.message for r in caplog.records)
        # The second future receives any cmd_response for dup-id.
        response = {"request_id": "dup-id", "ok": True, "code": "0", "msg": "", "data": {}}
        fake_node.push_input("cmd_response", _encode(response))
        assert fut2.result(timeout=2.0) == response
        # The first future is left dangling — caller will time out.
        assert not fut1.done()
    finally:
        loop.stop()


def test_cmd_response_missing_request_id_is_dropped(fake_node, caplog):
    """A cmd_response without request_id is logged and ignored."""
    import logging

    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        with caplog.at_level(logging.WARNING):
            fake_node.push_input("cmd_response", _encode({"ok": True, "code": "0"}))
            # Use a follow-up state event as a flush marker.
            fake_node.push_input("state", _encode({"seq": 1, "payload": {}}))
            deadline = time.monotonic() + 2.0
            while cache.snapshot()["stream"] is None and time.monotonic() < deadline:
                time.sleep(0.01)
        assert any("missing request_id" in r.message for r in caplog.records)
    finally:
        loop.stop()


def test_stop_is_idempotent(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    loop.stop()
    loop.stop()  # must not raise
    loop.stop()


def test_start_called_twice_is_noop(fake_node):
    cache = StateCache()
    loop = DoraLoop(node=fake_node, state_cache=cache)
    loop.start()
    try:
        t1 = loop._thread
        loop.start()  # second call is a no-op
        assert loop._thread is t1
    finally:
        loop.stop()
