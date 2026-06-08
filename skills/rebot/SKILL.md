---
name: rebot
description: reBotArm B601-DM 6-DOF arm + parallel gripper via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: rebot
required_safety_tier: safe_motion
hardware_requirements: rebotarm-b601-dm, parallel-gripper, dora-moveit2 (runtime extra), mujoco (headless EGL)
preflight:
  - label: ping arm controller or sim port
    command: bash -c 'test -n "${REBOT_HOST:-}" && curl -fsS -o /dev/null -m 3 http://${REBOT_HOST}:30002 || echo "no arm host set; skipping"'
    timeout_secs: 5
    critical: false
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && MUJOCO_GL=egl dora up && dora start dataflows/rebot-mujoco-bridge.yaml
    timeout_secs: 30
    critical: true
ready_check:
  - label: bridge HTTP responds
    command: curl -fsS -m 2 http://127.0.0.1:8768/healthz
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
    command: curl -fsS -X POST http://127.0.0.1:8768/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}'
    timeout_secs: 5
    critical: true
---

# reBotArm B601-DM (6-DOF Damiao-motor arm + parallel gripper)

You control a reBotArm B601-DM with a parallel gripper through a local HTTP bridge
at `http://127.0.0.1:8768`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

This robot reuses the **same vendor node and verbs** as the UR5e (it's the same
`moveit_arm_node`, selected with a different `ROBOT_CONFIG_MODULE` and MuJoCo
model) — so the verb surface is identical; only the kinematics, gripper stroke,
and named poses differ.

## Motion verbs

- `vendor.moveit.arm.move_to_pose` — Cartesian goal. Args: `{"pose": {"position": [x,y,z], "orientation": [x,y,z,w]}}`. IK + planning happen server-side.
- `vendor.moveit.arm.move_to_joint_state` — joint-space goal. Args: `{"joints": [j1, j2, j3, j4, j5, j6]}` (radians). Joint ranges: j1 ±2.8, j2 −3.14..0, j3 −3.14..0, j4 −1.87..1.57, j5 ±1.57, j6 ±3.14.
- `vendor.moveit.arm.move_to_named` — preset poses. Args: `{"name": "home"}`. For reBot: `home`, `safe`, `zero`, `up`.

## Planning split (advanced)

- `vendor.moveit.arm.plan` — returns a trajectory without executing.
- `vendor.moveit.arm.execute` — executes a precomputed trajectory.

## Gripper

- `vendor.moveit.arm.gripper.set` — Args: `{"width": 0.04}` (meters; reBot parallel stroke is 0..0.05). NOTE: the bridge contract is unchanged — width 0 = closed, larger = open. The sim glue handles reBot's inverted actuator convention internally.
- `vendor.moveit.arm.gripper.open` / `vendor.moveit.arm.gripper.close` — convenience.

## Planning scene

- `vendor.moveit.arm.scene.add_collision` — register a collision object. Args: `{"object": {"id": "...", "shape": "box", "size": [...], "pose": {...}}}`.
- `vendor.moveit.arm.scene.clear` — wipe the scene.

## Common operations

- **Home:** `POST /tools/vendor.moveit.arm.move_to_named` with `{"args":{"name":"home"}}`.
- **Open gripper:** `POST /tools/vendor.moveit.arm.gripper.open` with `{"args":{}}`.
- **Emergency stop:** `POST /tools/robot.estop`. Use immediately for any safety concern.
- **Check state:** `POST /tools/get_state` returns the latest `state` payload (joint positions, gripper width).

## Pick-and-place demo

The imperative pick-and-place demo (on-demand IK + skill sequencing, scripted or
LLM-driven) lives with the vendor node, **not** in the bridge:
`moveit-arm-dora-node/skill_pack/` (driven by `manifests/rebot.json`). The bridge
and octos core are unchanged — adding this robot was a new config/model + this
descriptor + a manifest.

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| `VENDOR_ERROR` | dora-moveit2 reported planning/execution failure (IK no-solution, planning timeout, etc.) | Surface `msg`; try a different pose or smaller step |
| `CONTROLLER_BUSY` | Another caller holds the motion slot | Call `robot.release_control` then retry |
| `INVALID_PARAMS` | Bad args (wrong joint count, missing pose field, unknown named pose) | Fix args and retry |
| `BRIDGE_TIMEOUT` | No `cmd_response` within 30 s | Likely a long-running plan; consider raising `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | Bridge lost its dora session | Lifecycle issue — operator-side recovery |
