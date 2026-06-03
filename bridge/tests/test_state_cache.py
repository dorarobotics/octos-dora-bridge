from __future__ import annotations

from octos_spec_bridge.state_cache import StateCache


def test_state_initially_none():
    cache = StateCache()
    snap = cache.snapshot()
    assert snap == {"stream": None, "stale": True, "last_age_s": None}


def test_state_set_and_get():
    cache = StateCache()
    cache.set_state(
        {
            "envelope_version": "1.0",
            "spec_version": "1.0.0",
            "source": "agibot-a2-001",
            "stream": "robot.state",
            "schema": "vendor.agibot.a2.state.v1",
            "seq": 1,
            "ts": "2026-05-23T10:00:00.000Z",
            "payload": {"a2_action": "DEFAULT"},
        }
    )
    snap = cache.snapshot()
    assert snap["stream"]["seq"] == 1
    assert snap["stream"]["payload"]["a2_action"] == "DEFAULT"
    assert snap["stale"] is False
    assert snap["last_age_s"] is not None and snap["last_age_s"] < 1.0


def test_state_becomes_stale_after_threshold(monkeypatch):
    """Patch time.monotonic so the test is deterministic (no real sleep)."""
    fake_now = [100.0]
    monkeypatch.setattr(
        "octos_spec_bridge.state_cache.time.monotonic",
        lambda: fake_now[0],
    )
    cache = StateCache(stale_after_s=0.05)
    cache.set_state({"seq": 1, "payload": {}})
    # Fast-forward past the staleness threshold.
    fake_now[0] = 100.10
    snap = cache.snapshot()
    assert snap["stale"] is True
    assert snap["last_age_s"] >= 0.05


def test_state_overwrite_keeps_latest():
    cache = StateCache()
    cache.set_state({"seq": 1, "payload": {"v": "a"}})
    cache.set_state({"seq": 2, "payload": {"v": "b"}})
    snap = cache.snapshot()
    assert snap["stream"]["seq"] == 2
    assert snap["stream"]["payload"]["v"] == "b"


def test_safety_event_ring_initially_empty():
    cache = StateCache()
    assert cache.events_since(0) == []


def test_safety_event_appended_and_filtered_by_seq():
    cache = StateCache()
    for i in range(1, 4):
        cache.append_safety_event({"seq": i, "payload": {"event": f"e{i}"}})
    assert [e["seq"] for e in cache.events_since(0)] == [1, 2, 3]
    assert [e["seq"] for e in cache.events_since(1)] == [2, 3]
    assert cache.events_since(99) == []


def test_safety_event_ring_drops_oldest_past_capacity():
    cache = StateCache(safety_ring_size=3)
    for i in range(1, 6):
        cache.append_safety_event({"seq": i, "payload": {}})
    assert [e["seq"] for e in cache.events_since(0)] == [3, 4, 5]


def test_state_cache_is_thread_safe():
    """Smoke-test: many threads writing concurrently, no data corruption."""
    import threading

    cache = StateCache()

    def writer(start: int) -> None:
        for i in range(start, start + 100):
            cache.append_safety_event({"seq": i, "payload": {}})

    threads = [threading.Thread(target=writer, args=(s,)) for s in (0, 100, 200, 300)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    events = cache.events_since(0)
    assert len(events) == 128
    assert len({e["seq"] for e in events}) == 128


def test_snapshot_stream_is_isolated_from_internal_state():
    """Callers must not be able to corrupt the cache by mutating snapshot()."""
    cache = StateCache()
    cache.set_state({"seq": 1, "payload": {"a2_action": "DEFAULT"}})
    snap = cache.snapshot()
    # Mutate the returned stream — should NOT affect the cache.
    snap["stream"]["seq"] = 999
    snap2 = cache.snapshot()
    assert snap2["stream"]["seq"] == 1
