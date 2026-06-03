"""Unit tests for heartbeat — periodic robot.heartbeat publisher.

Heartbeat reads advert.safety.heartbeat_timeout_ms; if > 0, it publishes
robot.heartbeat cmd_requests at half that period via DoraLoop.publish_cmd_request. The
heartbeat thread waits for the advert before starting and is cancellable.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Optional

from octos_spec_bridge.heartbeat import HeartbeatRunner


class FakeDoraLoop:
    def __init__(self, advert: Optional[dict[str, Any]]) -> None:
        self._advert = advert
        self.published: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def advert(self) -> Optional[dict[str, Any]]:
        return self._advert

    def set_advert(self, advert: dict[str, Any]) -> None:
        self._advert = advert

    def publish_cmd_request(self, envelope: dict[str, Any]) -> None:
        with self._lock:
            self.published.append(envelope)


def test_heartbeat_does_not_start_when_timeout_is_zero() -> None:
    advert = {"robot_id": "r1", "safety": {"heartbeat_timeout_ms": 0}}
    loop = FakeDoraLoop(advert)
    runner = HeartbeatRunner(dora_loop=loop, robot_id="r1")
    runner.start()
    time.sleep(0.15)
    runner.stop()
    assert loop.published == []


def test_heartbeat_does_not_start_when_safety_section_missing() -> None:
    advert = {"robot_id": "r1"}  # no safety section at all
    loop = FakeDoraLoop(advert)
    runner = HeartbeatRunner(dora_loop=loop, robot_id="r1")
    runner.start()
    time.sleep(0.15)
    runner.stop()
    assert loop.published == []


def test_heartbeat_publishes_at_half_period_when_timeout_nonzero() -> None:
    advert = {"robot_id": "r1", "safety": {"heartbeat_timeout_ms": 200}}
    loop = FakeDoraLoop(advert)
    runner = HeartbeatRunner(dora_loop=loop, robot_id="r1")
    runner.start()
    # 200ms timeout → tick every 100ms. After 350ms expect at least 2 publishes.
    time.sleep(0.35)
    runner.stop()
    assert len(loop.published) >= 2, f"expected >=2 publishes, got {len(loop.published)}"
    for env in loop.published:
        assert env["verb"] == "robot.heartbeat"
        assert env["target"] == "r1"
        assert env["params"] == {}


def test_heartbeat_waits_for_advert_before_publishing() -> None:
    loop = FakeDoraLoop(advert=None)
    runner = HeartbeatRunner(dora_loop=loop, robot_id="r1", advert_poll_interval_s=0.02)
    runner.start()
    # Without an advert, nothing should publish.
    time.sleep(0.1)
    assert loop.published == []
    # Now publish an advert with a tight heartbeat.
    loop.set_advert({"robot_id": "r1", "safety": {"heartbeat_timeout_ms": 100}})
    # Half period is 50ms; after 0.30s expect at least one publish.
    time.sleep(0.30)
    runner.stop()
    assert len(loop.published) >= 1


def test_stop_is_idempotent_and_joins_thread() -> None:
    advert = {"robot_id": "r1", "safety": {"heartbeat_timeout_ms": 100}}
    loop = FakeDoraLoop(advert)
    runner = HeartbeatRunner(dora_loop=loop, robot_id="r1")
    runner.start()
    runner.stop()
    runner.stop()  # second call must not raise
    # No further publishes after stop.
    snapshot = len(loop.published)
    time.sleep(0.15)
    assert len(loop.published) == snapshot
