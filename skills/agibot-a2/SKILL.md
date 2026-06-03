---
name: agibot-a2
description: AgiBot A2 humanoid via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: agibot-a2
required_safety_tier: safe_motion
hardware_requirements: agibot-a2-bridge, a2-mujoco-sim
preflight:
  - label: ping A2 motion RPC
    command: curl -fsS -o /dev/null -m 3 -X POST http://192.168.100.100:56322/rpc/aimdk.protocol.McBaseService/GetState -H "Content-Type: application/json" -d '{}'
    timeout_secs: 5
    critical: true
init:
  - label: start dora bridge dataflow
    # Assumes the bridge venv lives at /opt/octos-dora-bridge/bridge/.venv
    # (the convention referenced in dataflows/a2-bridge.yaml). If your venv
    # lives elsewhere, copy the dataflow YAML and update the two path: lines.
    command: cd /opt/octos-dora-bridge && dora up && dora start dataflows/a2-bridge.yaml
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8765/healthz
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
    command: curl -fsS -X POST http://127.0.0.1:8765/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}'
    timeout_secs: 5
    critical: true
---

# AgiBot A2 (humanoid biped)

You control an AgiBot A2 humanoid bipedal robot through a local HTTP bridge at
`http://127.0.0.1:8765`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

## Locomotion modes (set via `vendor.agibot.a2.motion.set_action`)

- `RL_LOCOMOTION_DEFAULT` — balanced walking. Default "move" mode.
- `RL_JOINT_DEFAULT` — joint-position controller; usually a stepping-stone toward locomotion.
- `PASSIVE_UPPER_BODY_JOINT_SERVO` — upper body free, lower body still.
- `DEFAULT` — passive, controller off (safe).

## Common operations

- **Walk:** `POST /tools/vendor.agibot.a2.motion.set_action` with `{"args":{"action":"RL_LOCOMOTION_DEFAULT"}}`.
- **Stop:** Same verb with `{"args":{"action":"DEFAULT"}}`.
- **Emergency stop:** `POST /tools/robot.estop`. Use immediately for any safety concern.
- **Speak:** `POST /tools/vendor.agibot.a2.audio.tts` with `{"args":{"text":"Hello"}}`.
- **Check state:** `POST /tools/get_state` with `{"args":{}}` — returns the most-recent `robot.state` payload (may be stale up to 5 s).

## MuJoCo simulator quirks (must read before commanding motion in sim)

1. **`current_action` in state stream does not echo commanded actions** on the
   MuJoCo sim build. After `set_action(RL_LOCOMOTION_DEFAULT)`, `get_state` may
   still report `a2_action: "DEFAULT"`. The authoritative success signal is the
   tool result: `ok: true, data.applied: true`.
2. **Stand-up requires manual MuJoCo Load-Key click.** The full sim startup is:
   - Send `set_action(RL_JOINT_DEFAULT)` and wait for `applied: true`.
   - **Ask the human operator to click "Load-Key" in MuJoCo.**
   - Send `set_action(RL_LOCOMOTION_DEFAULT)`.
   This sequence cannot be automated against this sim build; the Load-Key click
   is mandatory between the two `set_action` calls.
3. **Watchdog is disabled in sim** (`HEARTBEAT_TIMEOUT_MS=0`); you do not need to
   send `robot.heartbeat` periodically against the sim. On real hardware,
   heartbeats are required while motion verbs are in flight.

## When something fails

The bridge returns `ok: false` with one of these codes:

| Code | Meaning | What to do |
|---|---|---|
| `VENDOR_ERROR` | A2 returned a non-zero header code or the HTTP layer failed | Surface the `msg`; consider retrying after a beat |
| `CONTROLLER_BUSY` | Another caller holds the motion slot | Call `robot.release_control` then retry |
| `INVALID_PARAMS` | Bad args (missing field, wrong enum) | Fix args and retry |
| `BRIDGE_TIMEOUT` | No `cmd_response` within 30 s | Check `get_recent_safety_events`; may be vendor_unreachable |
| `BRIDGE_DOWN` | Bridge lost its dora session | Lifecycle issue — operator-side recovery |
