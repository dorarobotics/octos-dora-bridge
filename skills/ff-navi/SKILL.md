---
name: ff-navi
description: FF Navi mobile navigation base via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: ff-navi
required_safety_tier: safe_motion
hardware_requirements: ff-navi-bridge, ff-navi-robot-or-stub
preflight:
  - label: probe ff-navi SDK reachable (or NAVI_FAKE_SDK=1)
    command: test "${NAVI_FAKE_SDK:-0}" = "1" || python -c "import robot_control_py"
    timeout_secs: 10
    critical: true
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && dora up && dora start dataflows/navi-bridge.yaml
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8767/healthz
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
    command: curl -fsS -X POST http://127.0.0.1:8767/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}'
    timeout_secs: 5
    critical: true
---

# FF Navi (mobile navigation base)

You control an FF Navi mobile robot through a local HTTP bridge at
`http://127.0.0.1:8767`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

## Communication

The Navi vendor node uses the `robot_control_py` SDK to reach the real
robot. For offline development, set `NAVI_FAKE_SDK=1` in
`dataflows/navi-bridge.yaml` to use the in-package stub instead.

## Heartbeat

`HEARTBEAT_TIMEOUT_MS=1000` — the bridge sends `robot.heartbeat` every 500 ms
automatically. If heartbeats lapse, the Navi's deadman triggers `nav.stop`.
Do not call `robot.heartbeat` yourself.

## Common operations

- **Plan to a waypoint:** the exact verb name depends on the vendor advert;
  consult `GET /tools` for `vendor.ff.navi.nav.*`.
- **Stop:** `POST /tools/vendor.ff.navi.nav.stop` with `{"args":{}}`.
- **Emergency stop:** `POST /tools/robot.estop`. Use immediately for any
  safety concern.
- **Check state:** `POST /tools/get_state` with `{"args":{}}`.

## Workspace

The vendor's planner constrains motion to the configured nav-mesh; no
additional bridge-side workspace check is performed. Out-of-mesh requests
return `VENDOR_ERROR` with the planner's reason in `msg`.

## Safety

- `required_safety_tier: safe_motion` — path-planning verbs are gated by
  octos's `RobotPermissionPolicy`.
