"""Periodic robot.heartbeat publisher.

When the vendor capabilities advert declares
``safety.heartbeat_timeout_ms > 0``, the bridge publishes
``robot.heartbeat`` cmd_requests at half that period to keep the vendor's
deadman from firing. When the timeout is 0 or the safety section is
missing, this runner is a no-op — useful for sim deployments
(e.g. A2 MuJoCo).

Threading model matches DoraLoop: one daemon thread, controlled via a
threading.Event. Stop is idempotent and joins the thread.
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Optional, Protocol

from octos_spec_bridge.translator import tool_call_to_cmd_request

logger = logging.getLogger(__name__)


class _DoraLoopHandle(Protocol):
    """Subset of DoraLoop that heartbeat needs."""

    def advert(self) -> Optional[dict[str, Any]]: ...
    def publish_cmd_request(self, envelope: dict[str, Any]) -> None: ...


def _read_timeout_ms(advert: Optional[dict[str, Any]]) -> int:
    if not advert:
        return 0
    safety = advert.get("safety") or {}
    try:
        return int(safety.get("heartbeat_timeout_ms", 0))
    except (TypeError, ValueError):
        logger.warning(
            "heartbeat: non-integer safety.heartbeat_timeout_ms in advert; treating as 0"
        )
        return 0


class HeartbeatRunner:
    """Background thread that publishes robot.heartbeat at advert cadence."""

    def __init__(
        self,
        *,
        dora_loop: _DoraLoopHandle,
        robot_id: str,
        advert_poll_interval_s: float = 0.1,
    ) -> None:
        self._loop = dora_loop
        self._robot_id = robot_id
        self._advert_poll_interval_s = advert_poll_interval_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="heartbeat", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning("heartbeat thread did not exit within 2s")
            self._thread = None

    def _run(self) -> None:
        # Phase 1: wait for the advert.
        timeout_ms = 0
        while not self._stop.is_set():
            timeout_ms = _read_timeout_ms(self._loop.advert())
            if timeout_ms > 0:
                break
            if self._stop.wait(self._advert_poll_interval_s):
                return
        if self._stop.is_set():
            return

        period_s = (timeout_ms / 1000.0) / 2.0
        logger.info(
            "heartbeat: timeout=%dms → publishing robot.heartbeat every %.3fs",
            timeout_ms,
            period_s,
        )

        # Phase 2: publish loop.
        while not self._stop.is_set():
            envelope = tool_call_to_cmd_request(
                tool="robot.heartbeat",
                args={},
                target=self._robot_id,
            )
            try:
                self._loop.publish_cmd_request(envelope)
            except Exception:  # noqa: BLE001 — keep the thread alive
                logger.exception("heartbeat publish failed")
            if self._stop.wait(period_s):
                return
