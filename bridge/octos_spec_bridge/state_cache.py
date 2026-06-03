"""Thread-safe state + safety-event cache.

The bridge's dora-loop thread writes; the http_api request handlers read.
A single Lock guards both fields — contention is low (1 Hz writes,
occasional polled reads).
"""

from __future__ import annotations

import collections
import threading
import time
from typing import Any, Optional

DEFAULT_STALE_AFTER_S = 5.0
DEFAULT_SAFETY_RING_SIZE = 128


class StateCache:
    def __init__(
        self,
        *,
        stale_after_s: float = DEFAULT_STALE_AFTER_S,
        safety_ring_size: int = DEFAULT_SAFETY_RING_SIZE,
    ) -> None:
        self._stale_after_s = stale_after_s
        self._lock = threading.Lock()
        self._state: Optional[dict[str, Any]] = None
        self._state_ts: float = 0.0
        self._events: collections.deque[dict[str, Any]] = collections.deque(maxlen=safety_ring_size)

    def set_state(self, envelope: dict[str, Any]) -> None:
        with self._lock:
            self._state = envelope
            self._state_ts = time.monotonic()

    def snapshot(self) -> dict[str, Any]:
        """Return a snapshot of the cached state.

        The returned ``stream`` field is a shallow copy of the stored
        envelope so callers can JSON-serialize or read freely without
        risking corruption of the live cache.
        """
        with self._lock:
            if self._state is None:
                return {"stream": None, "stale": True, "last_age_s": None}
            age = time.monotonic() - self._state_ts
            return {
                "stream": dict(self._state),
                "stale": age > self._stale_after_s,
                "last_age_s": age,
            }

    def append_safety_event(self, envelope: dict[str, Any]) -> None:
        with self._lock:
            self._events.append(envelope)

    def events_since(self, since_seq: int) -> list[dict[str, Any]]:
        """Return ring contents with seq > since_seq, in ring order."""
        with self._lock:
            return [e for e in self._events if e.get("seq", 0) > since_seq]
