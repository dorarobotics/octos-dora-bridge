---
name: nav-base
description: Mobile-base navigation via dora-nav, SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: nav-base
required_safety_tier: safe_motion
hardware_requirements: dora-nav-stack, mobile-base, lidar, nav-base-bridge
preflight:
  - label: check waypoints file exists
    command: bash -c 'test -f /opt/octos-dora-bridge/load_path.yml || test "${NAV_FAKE_MAP:-0}" = "1"'
    timeout_secs: 3
    critical: true
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && dora up && dora start dataflows/nav-base-bridge.yaml
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8769/healthz
    timeout_secs: 3
    retries: 10
    critical: true
shutdown:
  - label: stop dora dataflow
    command: dora stop --grace 5
    timeout_secs: 10
    critical: false
emergency_shutdown:
  - label: estop via bridge
    command: curl -fsS -X POST http://127.0.0.1:8769/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}'
    timeout_secs: 5
    critical: true
---

# nav-base (mobile navigation base)

You control a mobile base through a local HTTP bridge at `http://127.0.0.1:8769`.
The base uses dora-nav under the hood for SLAM-based localization and planning;
the bridge speaks SPEC-VENDOR-NODE-V1.

## Motion verbs

- `vendor.dora_nav.base.go_to_pose` — Args: `{"pose": {"position": [x,y,z], "orientation": [x,y,z,w]}}`. Goal is dispatched to the planner; success returned when the planner reports `arrived`.
- `vendor.dora_nav.base.go_to_named` — Args: `{"name": "kitchen"}`. Resolved via the configured `WAYPOINTS_PATH` YAML file.
- `vendor.dora_nav.base.set_velocity` — Args: `{"linear": 0.3, "angular": 0.0}`. Manual driving (cancels any active goal).
- `vendor.dora_nav.base.stop` — Cancels goal + commands zero velocity. Privileged (works during estop).

## Localization & map verbs

- `vendor.dora_nav.localization.get_pose` — Latest robot pose (`{"x": ..., "y": ..., "theta": ...}`).
- `vendor.dora_nav.map.get_obstacles` — Currently detected obstacle list.

## Common operations

- **Go somewhere:** `POST /tools/vendor.dora_nav.base.go_to_named` with `{"args":{"name":"kitchen"}}`.
- **Where am I:** `POST /tools/vendor.dora_nav.localization.get_pose` with `{"args":{}}`.
- **Stop immediately:** `POST /tools/vendor.dora_nav.base.stop` (or `robot.estop` for full shutdown).

## Quirks

- **Map required for real hardware.** Set `MAP_PATH` env var. For sim / unit tests set `NAV_FAKE_MAP=1` and the node emits a synthetic empty map.
- **Status updates are asynchronous.** A `go_to_pose` returns OK once the goal is queued, not once the base has arrived. Watch the `state` stream for `nav_status` transitions.

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| `VENDOR_ERROR` | dora-nav stack reported a problem (no path found, blocked, localization lost) | Surface `msg`; consider clearing obstacles, replanning |
| `CONTROLLER_BUSY` | Another caller holds the motion slot | `robot.release_control` then retry |
| `INVALID_PARAMS` | Bad args (unknown waypoint, malformed pose) | Fix args |
| `BRIDGE_TIMEOUT` | No `cmd_response` within 30 s | Long-running planning; consider raising `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | Bridge lost its dora session | Operator recovery |
