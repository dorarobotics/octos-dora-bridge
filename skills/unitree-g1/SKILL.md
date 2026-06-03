---
name: unitree-g1
description: Unitree G1 humanoid biped via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: unitree-g1
required_safety_tier: safe_motion
hardware_requirements: unitree-g1-bridge, unitree-g1-robot-or-sim
preflight:
  - label: confirm DDS network interface is up
    command: ip link show "${DDS_NETWORK_INTERFACE:-lo}"
    timeout_secs: 5
    critical: false
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && dora up && dora start dataflows/g1-bridge.yaml
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8766/healthz
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
    command: curl -fsS -X POST http://127.0.0.1:8766/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}'
    timeout_secs: 5
    critical: true
---

# Unitree G1 (humanoid biped)

You control a Unitree G1 humanoid bipedal robot through a local HTTP bridge at
`http://127.0.0.1:8766`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

## Communication

The G1 vendor node speaks DDS (CycloneDDS) on the network interface named by
`DDS_NETWORK_INTERFACE` (default empty = system default). If running on a
multi-interface host, set the env var in `dataflows/g1-bridge.yaml`.

## Heartbeat

`HEARTBEAT_TIMEOUT_MS=500` — the bridge sends `robot.heartbeat` every 250 ms
automatically. If heartbeats lapse, the G1 deadman fires `DEFAULT` mode.
Do not call `robot.heartbeat` yourself.

## Common operations

- **Switch FSM mode:** `POST /tools/vendor.unitree.g1.fsm.switch_mode` with
  `{"args":{"mode":"<mode_name>"}}`.
- **Walk:** standard locomotion verb; consult `GET /tools` for the exact name
  the vendor reports (the advert is authoritative).
- **Emergency stop:** `POST /tools/robot.estop`. Use immediately for any
  safety concern.
- **Check state:** `POST /tools/get_state` with `{"args":{}}` — returns the
  most-recent `robot.state` payload (may be stale up to 5 s).

## Safety

- `required_safety_tier: safe_motion` — locomotion verbs are gated by octos's
  `RobotPermissionPolicy`. The bridge does not double-enforce.
- An operator should be holding the G1 kill-switch dongle when commanding
  any motion verb against real hardware. The bridge does not enforce this;
  the operator does.

## When something fails

Error codes are identical to A2's table — see `skills/agibot-a2/SKILL.md`
"When something fails." The G1's most common code under real-hardware use is
`VENDOR_ERROR` from DDS transport failures; check `DDS_NETWORK_INTERFACE`.
