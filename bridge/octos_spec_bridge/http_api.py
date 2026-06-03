"""FastAPI app — HTTP surface octos talks to.

Endpoints:
  GET  /healthz                    — liveness
  GET  /tools                      — tool catalog (vendor verbs + synthetics)
  POST /tools/<name>               — invoke a vendor verb
"""

from __future__ import annotations

import concurrent.futures
import logging
from concurrent.futures import Future
from typing import Any, Protocol

from fastapi import Body, FastAPI
from fastapi.responses import JSONResponse

from octos_spec_bridge.state_cache import StateCache
from octos_spec_bridge.translator import (
    cmd_response_to_tool_result,
    synthesize_tool_description,
    tool_call_to_cmd_request,
)

logger = logging.getLogger(__name__)

SYNTHETIC_TOOL_NAMES = ("get_state", "get_recent_safety_events")
SYNTHETIC_DESCRIPTIONS = {
    "get_state": (
        "Return the most-recent robot.state payload from the vendor stream "
        "(cached; may be stale by up to 5 s)."
    ),
    "get_recent_safety_events": (
        "Return safety-event payloads with seq greater than 'since' "
        "(ring-buffered, last 128 events)."
    ),
}


class DoraLoopLike(Protocol):
    def advert(self) -> dict[str, Any] | None: ...
    def register_pending(self, request_id: str) -> Future[dict[str, Any]]: ...
    def cancel_pending(self, request_id: str) -> None: ...
    def publish_cmd_request(self, envelope: dict[str, Any]) -> None: ...


def _known_verbs(advert: dict[str, Any]) -> set[str]:
    return {cmd.get("verb", "") for cmd in advert.get("commands", []) if cmd.get("verb")}


def create_app(
    *,
    dora_loop: DoraLoopLike,
    state_cache: StateCache,
    robot_id: str,
    cmd_timeout_s: float,
) -> FastAPI:
    app = FastAPI(title="octos-spec-bridge")

    @app.get("/healthz")
    def healthz() -> JSONResponse:
        if dora_loop.advert() is None:
            return JSONResponse({"status": "advert_pending"}, status_code=503)
        return JSONResponse({"status": "ok"}, status_code=200)

    @app.get("/tools")
    def list_tools() -> JSONResponse:
        advert = dora_loop.advert()
        if advert is None:
            return JSONResponse({"status": "advert_pending"}, status_code=503)
        tools = []
        for cmd in advert.get("commands", []):
            verb = cmd.get("verb", "")
            if not verb:
                continue
            entry = {
                "name": verb,
                "description": synthesize_tool_description(verb),
                "input_schema": {"type": "object", "additionalProperties": True},
            }
            if "safety_tier" in cmd:  # SPEC-V1 1.1
                entry["safety_tier"] = cmd["safety_tier"]
            tools.append(entry)
        for synth in SYNTHETIC_TOOL_NAMES:
            tools.append(
                {
                    "name": synth,
                    "description": SYNTHETIC_DESCRIPTIONS[synth],
                    "input_schema": {"type": "object", "additionalProperties": True},
                }
            )
        return JSONResponse({"tools": tools}, status_code=200)

    @app.post("/tools/{name:path}")
    def invoke_tool(name: str, payload: dict[str, Any] = Body(default={})) -> JSONResponse:
        args = payload.get("args", {}) or {}

        if name == "get_state":
            return JSONResponse(
                {
                    "ok": True,
                    "code": "0",
                    "msg": "",
                    "data": state_cache.snapshot(),
                    "trace_id": None,
                    "request_id": "",
                },
                status_code=200,
            )

        if name == "get_recent_safety_events":
            since = int(args.get("since", 0))
            return JSONResponse(
                {
                    "ok": True,
                    "code": "0",
                    "msg": "",
                    "data": {"events": state_cache.events_since(since)},
                    "trace_id": None,
                    "request_id": "",
                },
                status_code=200,
            )

        advert = dora_loop.advert()
        if advert is None:
            return JSONResponse(
                {
                    "ok": False,
                    "code": "ADVERT_PENDING",
                    "msg": "capabilities advert not yet received",
                },
                status_code=503,
            )

        if name not in _known_verbs(advert):
            return JSONResponse(
                {
                    "ok": False,
                    "code": "VERB_UNKNOWN",
                    "msg": f"verb {name!r} not in capabilities advert",
                },
                status_code=404,
            )

        envelope = tool_call_to_cmd_request(tool=name, args=args, target=robot_id)
        request_id = envelope["request_id"]
        fut = dora_loop.register_pending(request_id)
        try:
            dora_loop.publish_cmd_request(envelope)
            try:
                response = fut.result(timeout=cmd_timeout_s)
            except concurrent.futures.TimeoutError:
                dora_loop.cancel_pending(request_id)
                return JSONResponse(
                    {
                        "ok": False,
                        "code": "BRIDGE_TIMEOUT",
                        "msg": f"no cmd_response within {cmd_timeout_s}s",
                        "request_id": request_id,
                    },
                    status_code=504,
                )
            return JSONResponse(cmd_response_to_tool_result(response), status_code=200)
        except Exception:  # noqa: BLE001
            dora_loop.cancel_pending(request_id)
            raise

    return app
