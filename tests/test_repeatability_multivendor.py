"""Repeatability litmus: adding a new robot must not change bridge code.

The bridge is a single source of truth; per-robot deltas live entirely in
dataflow YAML + SKILL.md frontmatter. This test parses the three dataflows
and three SKILL.mds shipped today and verifies the canonical two-node
topology + required frontmatter keys on each.

NOTE: SKILL.md frontmatters contain `command:` lines with unquoted curl
arguments (e.g. `-H "Content-Type: application/json"`) that trip yaml.safe_load.
We extract frontmatter keys via regex rather than full YAML parsing — we only
need top-level keys and a few scalar values for this test.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_DIR = REPO_ROOT / "bridge" / "octos_spec_bridge"
DATAFLOWS = REPO_ROOT / "dataflows"
SKILLS = REPO_ROOT / "skills"

ROBOTS = ("agibot-a2", "unitree-g1", "ff-navi", "ur5e", "nav-base")
DATAFLOW_FILES = {
    "agibot-a2": "a2-bridge.yaml",
    "unitree-g1": "g1-bridge.yaml",
    "ff-navi": "navi-bridge.yaml",
    "ur5e": "ur5e-bridge.yaml",
    "nav-base": "nav-base-bridge.yaml",
}
EXPECTED_BRIDGE_FILES = {
    "__init__.py",
    "__main__.py",
    "translator.py",
    "state_cache.py",
    "dora_loop.py",
    "http_api.py",
    "heartbeat.py",
}
REQUIRED_FRONTMATTER_KEYS = {
    "name",
    "description",
    "version",
    "robot_type",
    "required_safety_tier",
    "hardware_requirements",
    "preflight",
    "init",
    "ready_check",
    "shutdown",
    "emergency_shutdown",
}
EXPECTED_PORTS = {"agibot-a2": 8765, "unitree-g1": 8766, "ff-navi": 8767, "ur5e": 8768, "nav-base": 8769}


def _extract_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """Return the raw frontmatter block + a dict of top-level scalar keys.

    Top-level scalar = a line matching `^key: value` at column 0 inside the
    `---` fence. Nested keys (under preflight/init/...) and list items are
    skipped. This is enough for the assertions we need.
    """
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return "", {}
    block = m.group(1)
    scalars: dict[str, str] = {}
    for line in block.splitlines():
        # Top-level scalar: starts at column 0, not "- ", contains ": "
        # The frontmatter block ranges include lifecycle sections like
        # `preflight:` (key with no value, list follows) — capture those keys
        # too as present-but-empty.
        sm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):(\s*(.*))?$", line)
        if sm:
            key = sm.group(1)
            value = (sm.group(3) or "").strip()
            scalars[key] = value
    return block, scalars


def _top_level_keys_in_frontmatter(text: str) -> set[str]:
    """Return the set of top-level frontmatter keys (excludes nested ones)."""
    return set(_extract_frontmatter(text)[1].keys())


def test_three_robots_share_one_bridge_codebase() -> None:
    """The bridge module set must be exactly what's listed.

    If a future task adds a module, update EXPECTED_BRIDGE_FILES *deliberately*
    and add a PR-description note explaining why all three vendors benefit
    from the change.
    """
    actual = {p.name for p in BRIDGE_DIR.glob("*.py")}
    assert actual == EXPECTED_BRIDGE_FILES, (
        f"unexpected bridge module set; "
        f"missing={EXPECTED_BRIDGE_FILES - actual}, extra={actual - EXPECTED_BRIDGE_FILES}"
    )


def test_each_dataflow_yaml_has_canonical_two_node_shape() -> None:
    for robot in ROBOTS:
        path = DATAFLOWS / DATAFLOW_FILES[robot]
        df = yaml.safe_load(path.read_text())
        nodes = df["nodes"]
        # nav-base uses 4 nodes (nav_base, fake_localization, fake_planner, bridge);
        # others use canonical 2-node shape (vendor + bridge).
        expected_node_count = 4 if robot == "nav-base" else 2
        assert len(nodes) == expected_node_count, f"{robot} dataflow has != {expected_node_count} nodes"
        node_ids = {n["id"] for n in nodes}
        assert "bridge" in node_ids, f"{robot} dataflow missing 'bridge' node"
        # Find the vendor node (not bridge, and for nav-base not fake_localization/fake_planner)
        vendor_node = next(
            n for n in nodes
            if n["id"] not in ("bridge", "fake_localization", "fake_planner")
        )

        # Vendor outputs the four SPEC-V1 standard topics.
        assert set(vendor_node["outputs"]) >= {
            "cmd_response",
            "capabilities",
            "state",
            "safety_event",
        }, f"{robot} vendor outputs missing SPEC-V1 standard topics"

        # Vendor consumes cmd_request from bridge.
        assert vendor_node["inputs"]["cmd_request"] == "bridge/cmd_request", (
            f"{robot} vendor inputs differ from SPEC-V1 standard"
        )

        # Both bridge and vendor nodes use the venv-python wrapper convention.
        for n in nodes:
            if n["id"] in ("bridge", vendor_node["id"]):
                assert n["path"] == "./venv-python", (
                    f"{robot} node {n['id']!r} must use ./venv-python wrapper "
                    f"(got {n['path']!r}); this is the dora-venv workaround convention"
                )


def test_each_skill_md_has_required_frontmatter_keys() -> None:
    for robot in ROBOTS:
        skill_md = (SKILLS / robot / "SKILL.md").read_text()
        _block, scalars = _extract_frontmatter(skill_md)
        keys = set(scalars.keys())
        missing = REQUIRED_FRONTMATTER_KEYS - keys
        assert not missing, f"{robot} SKILL.md frontmatter missing: {sorted(missing)}"
        # robot_type is a top-level scalar, should equal the directory name.
        assert scalars["robot_type"] == robot, (
            f"{robot} SKILL.md robot_type={scalars['robot_type']!r} "
            f"(expected {robot!r})"
        )


def test_each_bridge_uses_distinct_http_port() -> None:
    """Distinct ports so multiple robots can run on one host without collision."""
    seen: dict[int, str] = {}
    for robot in ROBOTS:
        df = yaml.safe_load((DATAFLOWS / DATAFLOW_FILES[robot]).read_text())
        bridge_node = next(n for n in df["nodes"] if n["id"] == "bridge")
        port = int(bridge_node["env"]["HTTP_PORT"])
        assert port not in seen, (
            f"{robot} and {seen[port]} both use HTTP_PORT={port}; ports must be distinct"
        )
        seen[port] = robot
        assert port == EXPECTED_PORTS[robot], (
            f"{robot} uses HTTP_PORT={port} (expected {EXPECTED_PORTS[robot]})"
        )
    assert seen == {8765: "agibot-a2", 8766: "unitree-g1", 8767: "ff-navi", 8768: "ur5e", 8769: "nav-base"}
