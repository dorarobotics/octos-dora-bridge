"""Entry point: wires DoraLoop + FastAPI server + uvicorn.

Reads env vars:
  ROBOT_ID         — required (raises KeyError)
  HTTP_PORT        — default 8765
  HTTP_HOST        — default 127.0.0.1 (localhost only)
  CMD_TIMEOUT_S    — default 30
  LOG_LEVEL        — default INFO

dora is imported lazily inside main() so that test-only imports of this
module (or running --help in environments without a dora coordinator) work.
"""

from __future__ import annotations

import logging
import os
import signal
from typing import Any

logger = logging.getLogger(__name__)


def main() -> None:
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    logging.basicConfig(level=log_level)

    robot_id = os.environ["ROBOT_ID"]
    http_host = os.environ.get("HTTP_HOST", "127.0.0.1")
    http_port = int(os.environ.get("HTTP_PORT", "8765"))
    cmd_timeout_s = float(os.environ.get("CMD_TIMEOUT_S", "30"))

    # Lazy imports — dora may not be installed in test envs.
    import uvicorn
    from dora import Node  # noqa: PLC0415, type: ignore[import-untyped]

    from octos_spec_bridge.dora_loop import DoraLoop
    from octos_spec_bridge.heartbeat import HeartbeatRunner
    from octos_spec_bridge.http_api import create_app
    from octos_spec_bridge.state_cache import StateCache

    state_cache = StateCache()
    node: Any = Node()
    loop = DoraLoop(node=node, state_cache=state_cache)
    loop.start()

    heartbeat = HeartbeatRunner(dora_loop=loop, robot_id=robot_id)
    heartbeat.start()

    app = create_app(
        dora_loop=loop,
        state_cache=state_cache,
        robot_id=robot_id,
        cmd_timeout_s=cmd_timeout_s,
    )

    config = uvicorn.Config(
        app=app,
        host=http_host,
        port=http_port,
        log_level=log_level.lower(),
        access_log=False,
    )
    server = uvicorn.Server(config)

    def _shutdown(*_: Any) -> None:
        logger.info("shutdown signal — stopping heartbeat + dora loop")
        heartbeat.stop()
        loop.stop()
        server.should_exit = True

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("bridge starting on %s:%d for robot_id=%s", http_host, http_port, robot_id)
    try:
        server.run()
    finally:
        heartbeat.stop()
        loop.stop()


if __name__ == "__main__":
    main()
