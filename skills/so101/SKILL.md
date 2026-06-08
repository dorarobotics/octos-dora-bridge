---
name: so101
description: SO-101 (LeRobot) 5-DOF arm + gripper via SPEC-VENDOR-NODE-V1 over local bridge
version: 0.1.0
author: dorarobotics
robot_type: so101
required_safety_tier: safe_motion
hardware_requirements: so-arm101, feetech-sts3215, lerobot, dora-moveit2 (runtime extra), mujoco (headless EGL)
preflight:
  - label: check serial port for the SO-101 bus
    command: bash -c 'test -e "${SO101_PORT:-/dev/ttyACM0}" || echo "no SO-101 bus at ${SO101_PORT:-/dev/ttyACM0}; sim/loopback only"'
    timeout_secs: 5
    critical: false
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && MUJOCO_GL=egl dora up && dora start dataflows/so101-mujoco-bridge.yaml
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

# SO-101 (LeRobot 5-DOF arm + gripper)

You control an SO-101 arm with a gripper through a local HTTP bridge at
`http://127.0.0.1:8768`. All tools are auto-discovered from the robot's
capabilities advert; the bridge speaks SPEC-VENDOR-NODE-V1.

Same vendor node (`moveit_arm_node`) and verb surface as UR5e/reBot — only the
kinematics differ. **The SO-101 is 5-DOF**: it controls position and the approach
(down) axis, but not full end-effector orientation (yaw about the approach axis is
free). The pick-and-place skill handles this automatically (down-only grasp IK).

## Motion verbs

- `vendor.moveit.arm.move_to_joint_state` — Args: `{"joints": [j1..j5]}` (radians). Joints: shoulder_pan, shoulder_lift, elbow_flex, wrist_flex, wrist_roll.
- `vendor.moveit.arm.move_to_named` — `{"name": "home"}`. Names: `home`, `safe`, `zero`, `up`.
- `vendor.moveit.arm.move_to_pose` — Cartesian goal. NOTE: as a 5-DOF arm, full orientation is not independently reachable; prefer joint-space / the pick-and-place skill.

## Gripper

- `vendor.moveit.arm.gripper.set` — Args: `{"width": 0.03}` (meters; SPEC contract, 0 = closed). The hardware backend maps width to the SO-101 gripper's 0–100 % command internally.
- `vendor.moveit.arm.gripper.open` / `vendor.moveit.arm.gripper.close`.

## Common operations

- **Home:** `POST /tools/vendor.moveit.arm.move_to_named` `{"args":{"name":"home"}}`.
- **Emergency stop:** `POST /tools/robot.estop` — disables servo torque on the bus.
- **Check state:** `POST /tools/get_state` — joint positions (5) + gripper.

## Sim vs hardware

- **Sim:** MuJoCo (`mujoco_sim`), TheRobotStudio SO101 model adapted object-first.
- **Hardware:** the `rebot-hw-dora-node` `LeRobotBackend` (`ROBOT_BACKEND=lerobot`,
  `lerobot_class=...SO101Follower`) — LeRobot's unified Robot API drives the Feetech
  bus. Config + manifest only; no new SPEC node and no bridge/octos change.

## Error codes

| Code | Meaning | What to do |
|---|---|---|
| `VENDOR_ERROR` | planning/execution failure (IK no-solution, etc.) | Surface `msg`; try another pose |
| `CONTROLLER_BUSY` | another caller holds the motion slot | `robot.release_control` then retry |
| `INVALID_PARAMS` | bad args (wrong joint count — SO-101 wants 5, not 6) | Fix args and retry |
| `BRIDGE_TIMEOUT` | no `cmd_response` within timeout | raise `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | bridge lost its dora session | operator-side recovery |
