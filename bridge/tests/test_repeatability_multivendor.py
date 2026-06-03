"""Multi-vendor repeatability test (post-SPEC-V1 1.1).

Verifies that for each supported vendor (agibot-a2, unitree-g1, ff-navi),
the bridge's GET /tools endpoint propagates safety_tier on every vendor-verb
entry when the vendor advert declares it. This is a smoke test that exercises
all three vendor families through the same bridge code path.

Note on shape: SPEC-VENDOR-NODE-V1 1.1 adverts carry the per-verb safety_tier
inside ``commands[*]``, where each command has a ``verb`` field (see
``test_get_tools_includes_safety_tier_from_advert`` in test_http_api.py).
The bridge appends two synthetic tools (``get_state``,
``get_recent_safety_events``) that are not safety-tiered — those are excluded
from the per-vendor-verb assertion.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from octos_spec_bridge.http_api import create_app
from octos_spec_bridge.state_cache import StateCache

from .test_http_api import FakeDoraLoop

# Synthetic tools the bridge always appends, which intentionally lack safety_tier.
SYNTHETIC_NAMES = {"get_state", "get_recent_safety_events"}


# One representative verb per vendor, each with a known, distinct safety_tier
# drawn from the SPEC-V1 1.1 tier vocabulary used by the three vendor nodes.
AGIBOT_A2_ADVERT = {
    "envelope_version": "1.0",
    "spec_version": "1.0.0",
    "robot_id": "agibot-a2-001",
    "vendor": "agibot",
    "model": "a2",
    "commands": [
        {"verb": "robot.heartbeat", "safety_tier": "observe"},
    ],
}

UNITREE_G1_ADVERT = {
    "envelope_version": "1.0",
    "spec_version": "1.0.0",
    "robot_id": "unitree-g1-001",
    "vendor": "unitree",
    "model": "g1",
    "commands": [
        {"verb": "vendor.unitree.g1.lowcmd.disable", "safety_tier": "full_actuation"},
    ],
}

FF_NAVI_ADVERT = {
    "envelope_version": "1.0",
    "spec_version": "1.0.0",
    "robot_id": "ff-navi-001",
    "vendor": "ff",
    "model": "navi",
    "commands": [
        {"verb": "robot.estop", "safety_tier": "emergency_override"},
    ],
}

UR5E_ADVERT = {
    "spec_version": "1.0.0",
    "vendor": "moveit",
    "model": "arm",
    "robot_id": "ur5e-001",
    "commands": [
        {"verb": "robot.heartbeat", "safety_tier": "emergency_override"},
        {"verb": "robot.estop", "safety_tier": "emergency_override"},
        {"verb": "robot.release_control", "safety_tier": "emergency_override"},
        {"verb": "robot.get_capabilities", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.move_to_pose", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.move_to_joint_state", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.move_to_named", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.plan", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.execute", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.gripper.set", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.gripper.open", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.gripper.close", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.scene.add_collision", "safety_tier": "emergency_override"},
        {"verb": "vendor.moveit.arm.scene.clear", "safety_tier": "emergency_override"},
    ],
}

NAV_BASE_ADVERT = {
    "spec_version": "1.0.0",
    "vendor": "dora_nav",
    "model": "base",
    "robot_id": "nav-base-001",
    "commands": [
        {"verb": "robot.heartbeat", "safety_tier": "emergency_override"},
        {"verb": "robot.estop", "safety_tier": "emergency_override"},
        {"verb": "robot.release_control", "safety_tier": "emergency_override"},
        {"verb": "robot.get_capabilities", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.base.go_to_pose", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.base.go_to_named", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.base.set_velocity", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.base.stop", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.localization.get_pose", "safety_tier": "emergency_override"},
        {"verb": "vendor.dora_nav.map.get_obstacles", "safety_tier": "emergency_override"},
    ],
}


@pytest.mark.parametrize(
    "label,advert,expected_tier",
    [
        ("agibot-a2", AGIBOT_A2_ADVERT, "observe"),
        ("unitree-g1", UNITREE_G1_ADVERT, "full_actuation"),
        ("ff-navi", FF_NAVI_ADVERT, "emergency_override"),
        ("ur5e", UR5E_ADVERT, "emergency_override"),
        ("nav-base", NAV_BASE_ADVERT, "emergency_override"),
    ],
)
def test_each_vendor_catalog_includes_safety_tier(
    label: str, advert: dict, expected_tier: str
) -> None:
    """Post-SPEC-V1 1.1, every vendor-verb entry in GET /tools must carry
    safety_tier when the vendor advert declares it. Asserted independently
    for agibot-a2, unitree-g1, and ff-navi to confirm the propagation path
    is vendor-agnostic.
    """
    fake_loop = FakeDoraLoop(advert=advert)
    app = create_app(
        dora_loop=fake_loop,
        state_cache=StateCache(),
        robot_id=advert["robot_id"],
        cmd_timeout_s=2.0,
    )
    client = TestClient(app)

    resp = client.get("/tools")
    assert resp.status_code == 200, (
        f"{label} GET /tools failed: {resp.status_code} {resp.text}"
    )
    body = resp.json()
    tools = body["tools"]
    assert tools, f"{label} catalog is empty"

    vendor_entries = [t for t in tools if t["name"] not in SYNTHETIC_NAMES]
    assert vendor_entries, f"{label} catalog has no vendor-verb entries"

    for entry in vendor_entries:
        assert "safety_tier" in entry, (
            f"{label} vendor entry missing safety_tier: {entry}"
        )
        assert entry["safety_tier"] == expected_tier, (
            f"{label} unexpected safety_tier for {entry['name']}: {entry['safety_tier']}"
        )
