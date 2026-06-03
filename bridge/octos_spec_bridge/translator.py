"""Pure translation between octos's {tool, args} and SPEC-VENDOR-NODE-V1 envelopes.

The bridge sends `cmd_request` envelopes per SPEC §7.1 and receives `cmd_response`
envelopes per SPEC §7.2. These functions are the single source of truth for the
wire shape — keep them pure and well-tested.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

CMD_TOKEN = "octos-bridge"
SPEC_ENVELOPE_VERSION = "1.0"
SPEC_VERSION = "1.0.0"


def _now_iso() -> str:
    """ISO-8601 UTC timestamp with millisecond precision and trailing Z."""
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def tool_call_to_cmd_request(
    tool: str,
    args: dict[str, Any],
    target: str,
    *,
    request_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a SPEC §7.1 cmd_request envelope from a tool call.

    request_id defaults to a freshly-generated UUIDv4; callers can pass an
    explicit value for retries or upstream dedup.

    trace_id is intentionally omitted for MVP — no upstream correlation
    identifier flows from octos's HTTP layer today. Add when the spec
    surfaces one.
    """
    return {
        "envelope_version": SPEC_ENVELOPE_VERSION,
        "spec_version": SPEC_VERSION,
        "verb": tool,
        "target": target,
        "request_id": request_id if request_id is not None else str(uuid.uuid4()),
        "ts": _now_iso(),
        "auth": {"cmd_token": CMD_TOKEN},
        "params": args,
    }


def cmd_response_to_tool_result(response: dict[str, Any]) -> dict[str, Any]:
    """Project a SPEC §7.2 cmd_response into octos's tool-result dict.

    Pass through ok/code/msg/data/trace_id/request_id unchanged. The bridge
    is a wire translator — it does NOT invent semantics or rewrite codes.

    Notes:
      - ``ok`` is coerced via ``bool(...)`` so vendors emitting 1/0 instead
        of true/false still produce a Python bool.
      - ``data`` defaults to ``{}`` (not None) so the LLM-facing contract
        always has a dict-shaped payload, even when the vendor omits it.
    """
    return {
        "ok": bool(response.get("ok", False)),
        "code": response.get("code", ""),
        "msg": response.get("msg", ""),
        "data": response.get("data", {}),
        "trace_id": response.get("trace_id"),
        "request_id": response.get("request_id", ""),
    }


def synthesize_tool_description(verb: str) -> str:
    """Generate a description for an LLM from the verb name alone.

    Used when the capabilities advert doesn't carry per-verb metadata
    (the MVP case). The spec follow-up is to require advert-side
    description+params_schema; this function is the fallback.

    A 4-part vendor.* verb (e.g. ``vendor.agibot.a2.motion``) is not a
    complete spec verb per SPEC §8.2 and intentionally falls through to
    the generic fallback — capability adverts MUST NOT advertise such
    verbs. See ``test_synthesize_vendor_with_only_4_parts_falls_back``.
    """
    if not verb:
        return "Verb (unnamed) (no synthesized description available)"
    if verb.startswith("robot."):
        return f"Common verb {verb} per SPEC-VENDOR-NODE-V1 §8.1"
    parts = verb.split(".")
    # vendor.<vendor>.<model>.<group>.<name>  → 5+ parts; group may itself be dotted
    if parts[0] == "vendor" and len(parts) >= 5:
        vendor = parts[1]
        model = parts[2]
        # group can be multi-segment, e.g. motion_switcher; name is last segment
        group_and_name = ".".join(parts[3:])
        return (
            f"Vendor verb: {group_and_name} on {vendor} {model} "
            "(see capabilities advert for params)"
        )
    return f"Verb {verb} (no synthesized description available)"
