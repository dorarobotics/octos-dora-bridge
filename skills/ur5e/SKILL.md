---
name: ur5e
description: UR5e 6-DOF arm + Robotiq 2F-85 gripper via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: ur5e
required_safety_tier: safe_motion
hardware_requirements: ur5e-arm, robotiq-2f85, dora-moveit2 (runtime extra), mujoco (headless EGL)
preflight:
  - label: ping arm controller or sim port
    command: bash -c 'test -n "${UR5E_HOST:-}" && curl -fsS -o /dev/null -m 3 http://${UR5E_HOST}:30002 || echo "no arm host set; skipping"'
    timeout_secs: 5
    critical: false
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && MUJOCO_GL=egl dora up && dora start dataflows/ur5e-mujoco-bridge.yaml
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

# UR5e + Robotiq 2F-85 (collaborative 6-DOF arm + parallel gripper)

You control a UR5e arm with a Robotiq 2F-85 gripper through a local HTTP bridge
at `http://127.0.0.1:8768`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

## Motion verbs

- `vendor.moveit.arm.move_to_pose` — Cartesian goal. Args: `{"pose": {"position": [x,y,z], "orientation": [x,y,z,w]}}`. IK + planning happen server-side.
- `vendor.moveit.arm.move_to_joint_state` — joint-space goal. Args: `{"joints": [j1, j2, j3, j4, j5, j6]}` (radians).
- `vendor.moveit.arm.move_to_named` — preset poses. Args: `{"name": "home"}`. Available names depend on the loaded robot config; for UR5e, expect at least `home` and `ready`.

## Planning split (advanced)

- `vendor.moveit.arm.plan` — returns a trajectory without executing. Useful when the agent wants to inspect / cache / replay.
- `vendor.moveit.arm.execute` — executes a precomputed trajectory.

## Gripper

- `vendor.moveit.arm.gripper.set` — Args: `{"width": 0.04}` (meters; 2F-85 max stroke is 0.085).
- `vendor.moveit.arm.gripper.open` — convenience for max stroke.
- `vendor.moveit.arm.gripper.close` — convenience for closed (0.0).

## Planning scene

- `vendor.moveit.arm.scene.add_collision` — register a collision object so the planner avoids it. Args: `{"object": {"id": "...", "shape": "box", "size": [...], "pose": {...}}}`.
- `vendor.moveit.arm.scene.clear` — wipe the scene.

## Common operations

- **Home:** `POST /tools/vendor.moveit.arm.move_to_named` with `{"args":{"name":"home"}}`.
- **Open gripper:** `POST /tools/vendor.moveit.arm.gripper.open` with `{"args":{}}`.
- **Emergency stop:** `POST /tools/robot.estop`. Use immediately for any safety concern.
- **Check state:** `POST /tools/get_state` returns the latest `state` payload (joint positions, gripper width).

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| `VENDOR_ERROR` | dora-moveit2 reported planning/execution failure (IK no-solution, planning timeout, etc.) | Surface `msg`; try a different pose or smaller step |
| `CONTROLLER_BUSY` | Another caller holds the motion slot | Call `robot.release_control` then retry |
| `INVALID_PARAMS` | Bad args (wrong joint count, missing pose field, unknown named pose) | Fix args and retry |
| `BRIDGE_TIMEOUT` | No `cmd_response` within 30 s | Likely a long-running plan; consider raising `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | Bridge lost its dora session | Lifecycle issue — operator-side recovery |
