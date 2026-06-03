"""Smoke tests for __main__.main wiring (no real dora.Node)."""

from __future__ import annotations

from unittest import mock

import pytest


def test_main_constructs_heartbeat_runner(monkeypatch: pytest.MonkeyPatch) -> None:
    """When main() runs, it must instantiate a HeartbeatRunner and start it.

    Heavy collaborators (dora.Node, uvicorn.Server, signal.signal) are
    monkeypatched so the test never actually opens sockets or talks to dora.
    """
    monkeypatch.setenv("ROBOT_ID", "test-robot-001")
    monkeypatch.setenv("HTTP_PORT", "0")

    fake_node = mock.MagicMock()
    fake_server = mock.MagicMock()
    fake_server.run.return_value = None

    started: list[dict] = []

    class FakeHeartbeatRunner:
        def __init__(self, **kwargs):  # noqa: ANN003
            self.kwargs = kwargs

        def start(self) -> None:
            started.append(self.kwargs)

        def stop(self) -> None:
            pass

    fake_uvicorn = mock.MagicMock()
    fake_uvicorn.Server = mock.MagicMock(return_value=fake_server)
    fake_uvicorn.Config = mock.MagicMock(return_value=mock.MagicMock())

    with (
        mock.patch.dict(
            "sys.modules",
            {
                "dora": mock.MagicMock(Node=lambda: fake_node),
                "uvicorn": fake_uvicorn,
            },
        ),
        mock.patch("octos_spec_bridge.__main__.signal.signal"),
        mock.patch("octos_spec_bridge.heartbeat.HeartbeatRunner", FakeHeartbeatRunner),
    ):
        from octos_spec_bridge.__main__ import main

        main()

    assert len(started) == 1
    assert started[0]["robot_id"] == "test-robot-001"
