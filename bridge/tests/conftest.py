"""Shared test fixtures.

FakeDoraNode mimics the surface area of dora.Node that the bridge uses:
  - send_output(output_id: str, value: pyarrow.Array) -> None
  - iteration: __iter__ yielding events {"type": "INPUT"|"STOP", "id": str, "value": pyarrow.Array}

Tests push events into the fake's input queue; the fake yields them on the
next iteration. Tests capture outputs from `sent` for assertions.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Iterator

import pyarrow as pa
import pytest


@dataclass
class SentOutput:
    output_id: str
    value: pa.Array


class FakeDoraNode:
    def __init__(self) -> None:
        self._inputs: Queue[dict] = Queue()
        self.sent: list[SentOutput] = []
        self._closed = threading.Event()

    def push_input(self, input_id: str, value: pa.Array) -> None:
        """Test helper: enqueue an input event."""
        self._inputs.put({"type": "INPUT", "id": input_id, "value": value})

    def send_output(self, output_id: str, value: pa.Array) -> None:
        self.sent.append(SentOutput(output_id, value))

    def close(self) -> None:
        self._closed.set()
        self._inputs.put({"type": "STOP", "id": "", "value": pa.array([])})

    def __iter__(self) -> Iterator[dict]:
        while not self._closed.is_set():
            try:
                event = self._inputs.get(timeout=0.1)
            except Empty:
                continue
            yield event
            if event["type"] == "STOP":
                return


@pytest.fixture
def fake_node() -> FakeDoraNode:
    return FakeDoraNode()


@pytest.fixture
def sample_advert() -> dict:
    """Minimal capabilities advert matching SPEC-VENDOR-NODE-V1."""
    return {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "robot_id": "agibot-a2-001",
        "vendor": "agibot",
        "model": "a2",
        "sdk_version": "1.3",
        "node_version": "0.1.0",
        "ts": "2026-05-23T10:00:00.000Z",
        "commands": [
            {"verb": "robot.heartbeat"},
            {"verb": "robot.estop"},
            {"verb": "vendor.agibot.a2.motion.set_action"},
            {"verb": "vendor.agibot.a2.audio.tts"},
        ],
        "streams": [
            {"name": "robot.state", "schema": "vendor.agibot.a2.state.v1", "rate_hz": 1.0},
            {
                "name": "robot.safety_event",
                "schema": "robot.safety_event.v1",
                "rate_hz": "on-event",
            },
        ],
        "safety": {"heartbeat_timeout_ms": 0},
    }
