---
name: lekiwi
description: LeKiwi holonomic mobile base in MuJoCo sim, SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: nav-base
required_safety_tier: safe_motion
hardware_requirements: lekiwi-mujoco-sim, nav-base-bridge
preflight:
  - label: sim model present
    command: bash -c 'test -f "${LEKIWI_SIM_DIR:-/opt/LeKiwi-sim}/mjcf_lcmm_robot.xml"'
    timeout_secs: 3
    critical: true
init:
  - label: start dora bridge dataflow
    command: bash -c 'cd /opt/octos-dora-bridge && dora up && dora start dataflows/lekiwi-mujoco-bridge.yaml'
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8770/healthz
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
    command: "curl -fsS -X POST http://127.0.0.1:8770/tools/robot.estop -H \"Content-Type: application/json\" -d '{\"args\":{\"reason\":\"emergency\"}}'"
    timeout_secs: 5
    critical: true
---

# lekiwi (holonomic mobile base, MuJoCo sim)

You control a LeKiwi mobile base through a local HTTP bridge at `http://127.0.0.1:8770`.
Milestone-1 motion is unicycle teleop.

## Motion verbs

- `vendor.dora_nav.base.set_velocity` — Args: `{"linear": 0.3, "angular": 0.0}`. Forward/back via `linear`, turn via `angular`.
- `vendor.dora_nav.base.stop` — Stops the base (privileged; works during estop).
- `vendor.dora_nav.localization.get_pose` — Latest pose `{"x","y","theta"}`.

## Common operations

- **Move forward:** `set_velocity {"linear": 0.3, "angular": 0.0}`, then `stop`.
- **Turn left:** `set_velocity {"linear": 0.0, "angular": 0.8}`, then `stop`.
- **Where am I:** `localization.get_pose`.

## Quirks

- Sim base is kinematic; `set_velocity` cruises until the next `stop` or zero-velocity command.
- `go_to_pose` / named waypoints are NOT supported in this milestone (teleop only).
