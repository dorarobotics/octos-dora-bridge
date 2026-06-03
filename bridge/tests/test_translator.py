from __future__ import annotations

import json
import re

from octos_spec_bridge.translator import (
    cmd_response_to_tool_result,
    synthesize_tool_description,
    tool_call_to_cmd_request,
)


ISO_8601_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def test_tool_call_to_cmd_request_motion_setaction():
    env = tool_call_to_cmd_request(
        tool="vendor.agibot.a2.motion.set_action",
        args={"action": "RL_LOCOMOTION_DEFAULT"},
        target="agibot-a2-001",
    )

    # Spec fields present and correct
    assert env["envelope_version"] == "1.0"
    assert env["spec_version"] == "1.0.0"
    assert env["verb"] == "vendor.agibot.a2.motion.set_action"
    assert env["target"] == "agibot-a2-001"
    assert env["params"] == {"action": "RL_LOCOMOTION_DEFAULT"}
    assert env["auth"] == {"cmd_token": "octos-bridge"}

    # Generated fields look right
    assert UUID_RE.match(env["request_id"]), f"bad request_id: {env['request_id']!r}"
    assert ISO_8601_Z.match(env["ts"]), f"bad ts: {env['ts']!r}"


def test_tool_call_to_cmd_request_no_args():
    env = tool_call_to_cmd_request(
        tool="robot.heartbeat",
        args={},
        target="agibot-a2-001",
    )
    assert env["envelope_version"] == "1.0"
    assert env["spec_version"] == "1.0.0"
    assert env["verb"] == "robot.heartbeat"
    assert env["target"] == "agibot-a2-001"
    assert env["params"] == {}
    assert env["auth"] == {"cmd_token": "octos-bridge"}
    assert UUID_RE.match(env["request_id"])
    assert ISO_8601_Z.match(env["ts"])


def test_tool_call_to_cmd_request_explicit_request_id_used():
    """When caller passes request_id, use it verbatim (for retries / dedup)."""
    env = tool_call_to_cmd_request(
        tool="robot.heartbeat",
        args={},
        target="x",
        request_id="fixed-id-1234",
    )
    assert env["request_id"] == "fixed-id-1234"


def test_envelope_serializable_as_json():
    env = tool_call_to_cmd_request("robot.heartbeat", {}, "x")
    # Must round-trip through json — vendor reads it via json.loads.
    assert json.loads(json.dumps(env)) == env


def test_tool_call_to_cmd_request_empty_string_request_id_is_used_verbatim():
    """Empty string is a legal request_id per spec; must NOT be replaced with UUID."""
    env = tool_call_to_cmd_request(
        tool="robot.heartbeat",
        args={},
        target="x",
        request_id="",
    )
    assert env["request_id"] == ""


def test_cmd_response_to_tool_result_success():
    response = {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "request_id": "abc-123",
        "ok": True,
        "code": "0",
        "msg": "",
        "ts": "2026-05-23T10:00:00.000Z",
        "data": {"applied": True},
        "trace_id": "trace-xyz",
    }
    result = cmd_response_to_tool_result(response)
    assert result == {
        "ok": True,
        "code": "0",
        "msg": "",
        "data": {"applied": True},
        "trace_id": "trace-xyz",
        "request_id": "abc-123",
    }


def test_cmd_response_to_tool_result_vendor_error():
    response = {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "request_id": "abc-123",
        "ok": False,
        "code": "VENDOR_ERROR",
        "msg": "HTTP error: connection refused",
        "ts": "2026-05-23T10:00:00.000Z",
        "data": {"vendor_code": -1},
    }
    result = cmd_response_to_tool_result(response)
    assert result["ok"] is False
    assert result["code"] == "VENDOR_ERROR"
    assert result["msg"] == "HTTP error: connection refused"
    assert result["data"] == {"vendor_code": -1}
    assert result["trace_id"] is None


def test_cmd_response_missing_trace_id():
    response = {
        "envelope_version": "1.0",
        "spec_version": "1.0.0",
        "request_id": "x",
        "ok": True,
        "code": "0",
        "msg": "",
        "ts": "2026-05-23T10:00:00.000Z",
        "data": {},
    }
    result = cmd_response_to_tool_result(response)
    assert result["trace_id"] is None


def test_cmd_response_to_tool_result_all_defaults():
    """Empty dict — every field falls back to its default."""
    result = cmd_response_to_tool_result({})
    assert result == {
        "ok": False,
        "code": "",
        "msg": "",
        "data": {},
        "trace_id": None,
        "request_id": "",
    }


def test_synthesize_common_verb():
    desc = synthesize_tool_description("robot.heartbeat")
    assert desc == "Common verb robot.heartbeat per SPEC-VENDOR-NODE-V1 §8.1"


def test_synthesize_vendor_verb():
    desc = synthesize_tool_description("vendor.agibot.a2.motion.set_action")
    assert desc == (
        "Vendor verb: motion.set_action on agibot a2 (see capabilities advert for params)"
    )


def test_synthesize_multilevel_vendor_verb():
    """Vendor verbs can have more than one group-level segment."""
    desc = synthesize_tool_description("vendor.unitree.g1.motion_switcher.select")
    assert desc == (
        "Vendor verb: motion_switcher.select on unitree g1 (see capabilities advert for params)"
    )


def test_synthesize_unrecognized_verb_falls_back_to_raw_name():
    desc = synthesize_tool_description("custom.weird.verb")
    assert desc == "Verb custom.weird.verb (no synthesized description available)"


def test_synthesize_empty_verb_does_not_produce_blank_in_output():
    """Defensive: empty input must not yield 'Verb  (no synthesized ...)' with a blank."""
    desc = synthesize_tool_description("")
    assert desc == "Verb (unnamed) (no synthesized description available)"


def test_synthesize_vendor_with_only_4_parts_falls_back():
    """4-part vendor.x.y.z is not a complete spec verb (§8.2) — intentional fallback."""
    desc = synthesize_tool_description("vendor.agibot.a2.motion")
    assert desc == "Verb vendor.agibot.a2.motion (no synthesized description available)"
