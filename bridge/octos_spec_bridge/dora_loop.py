"""Background-thread dora Node lifecycle.

Subscribes to: capabilities, cmd_response, state, safety_event.
Publishes:     cmd_request.

The dora Node's iteration is blocking, so the loop runs on its own thread.
Concurrent http_api request handlers interact via:
  - register_pending(request_id) -> concurrent.futures.Future
  - publish_cmd_request(envelope)
  - advert() (read-only snapshot of the cached capabilities advert)

state_cache is shared mutable state; DoraLoop only writes to it. Reads
happen from http_api in another thread; the cache itself is thread-safe.
"""

from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import Future
from typing import Any, Optional

import pyarrow as pa

from octos_spec_bridge.state_cache import StateCache

logger = logging.getLogger(__name__)

DORA_INPUT_IDS = ("capabilities", "cmd_response", "state", "safety_event")
DORA_OUTPUT_ID = "cmd_request"


def _as_event_dict(event: Any) -> dict[str, Any]:
    """Normalize a dora event to a dict.

    The custom dora fork yields dict events; stock ``dora-rs`` yields a
    subscript-only ``PyEvent`` (no ``.get``). Coerce the latter so the loop
    works on both. Dicts pass through unchanged.
    """
    if isinstance(event, dict):
        return event
    out: dict[str, Any] = {}
    for key in ("type", "id", "value", "metadata", "error"):
        try:
            out[key] = event[key]
        except Exception:  # noqa: BLE001
            out[key] = None
    return out


class DoraLoop:
    def __init__(self, *, node: Any, state_cache: StateCache) -> None:
        self._node = node
        self._cache = state_cache
        self._advert: Optional[dict[str, Any]] = None
        self._advert_lock = threading.Lock()
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._stopped = False
        self._start_lock = threading.Lock()
        self._publish_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._thread is not None:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="dora-loop", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._stop.set()
        if hasattr(self._node, "close"):
            self._node.close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            if self._thread.is_alive():
                logger.warning(
                    "dora-loop thread did not exit within 2s; leaving as zombie. "
                    "Real dora.Node has no close() — stop() cannot interrupt an idle iterator."
                )
            self._thread = None

    def advert(self) -> Optional[dict[str, Any]]:
        with self._advert_lock:
            return self._advert

    def register_pending(self, request_id: str) -> Future[dict[str, Any]]:
        """Reserve a future that will resolve when the matching cmd_response arrives.

        Duplicate request_id is a programming error or a UUID collision; the
        prior future is dropped (its caller will time out) and a warning is
        logged. The new future replaces it so the latest caller gets the next
        matching cmd_response.
        """
        fut: Future[dict[str, Any]] = Future()
        with self._pending_lock:
            if request_id in self._pending:
                logger.warning(
                    "register_pending: duplicate request_id=%r — previous caller will time out",
                    request_id,
                )
            self._pending[request_id] = fut
        return fut

    def cancel_pending(self, request_id: str) -> None:
        """Drop a pending future (e.g. on http_api-side timeout)."""
        with self._pending_lock:
            self._pending.pop(request_id, None)

    def publish_cmd_request(self, envelope: dict[str, Any]) -> None:
        """Send a SPEC §7.1 envelope on the cmd_request output.

        The publish call holds a lock because dora.Node.send_output thread
        safety is not documented in this codebase. Cheap insurance — emits
        are infrequent (one per HTTP tool call).
        """
        payload = json.dumps(envelope)
        with self._publish_lock:
            self._node.send_output(DORA_OUTPUT_ID, pa.array([payload]))

    def _run(self) -> None:
        try:
            for event in self._node:
                if self._stop.is_set():
                    return
                event = _as_event_dict(event)
                etype = event.get("type")
                if etype != "INPUT":
                    if etype == "STOP":
                        return
                    continue
                self._dispatch(event)
        except Exception:
            logger.exception("dora loop crashed")
            raise

    def _dispatch(self, event: dict[str, Any]) -> None:
        input_id = event.get("id")
        if input_id not in DORA_INPUT_IDS:
            return
        try:
            value = event["value"]
            raw = value.to_pylist()[0] if hasattr(value, "to_pylist") else None
            if not isinstance(raw, str):
                logger.warning("dora input %s had non-string value, dropping", input_id)
                return
            envelope = json.loads(raw)
        except (KeyError, IndexError, json.JSONDecodeError):
            logger.exception("failed to decode dora input %s", input_id)
            return
        except Exception:  # noqa: BLE001 — defensive: don't crash the loop on bad data
            logger.exception(
                "unexpected error decoding dora input %s, dropping message",
                input_id,
            )
            return

        if input_id == "capabilities":
            with self._advert_lock:
                self._advert = envelope
            logger.info("captured capabilities advert")
            return
        if input_id == "state":
            self._cache.set_state(envelope)
            return
        if input_id == "safety_event":
            self._cache.append_safety_event(envelope)
            return
        if input_id == "cmd_response":
            req_id = envelope.get("request_id")
            if not req_id:
                logger.warning(
                    "cmd_response with empty/missing request_id, dropping: %r",
                    envelope,
                )
                return
            with self._pending_lock:
                fut = self._pending.pop(req_id, None)
            if fut is not None:
                if not fut.done():
                    fut.set_result(envelope)
            else:
                logger.debug("cmd_response for unknown request_id=%r (late/orphan)", req_id)
            return
