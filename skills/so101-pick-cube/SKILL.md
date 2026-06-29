---
name: so101-pick-cube
description: SO-101 and Adora pick-and-place with camera-based block detection and hand-eye calibration via SPEC-VENDOR-NODE-V1 bridge
version: 0.5.0
author: dorarobotics
robot_type: so101, adora
required_safety_tier: safe_motion
hardware_requirements: so-arm101, feetech-sts3215, orbbec-gemini-335, dora-moveit2 (runtime), mujoco (headless EGL)
preflight:
  - label: check arm serial bus
    command: bash -c 'test -e "${SO101_PORT:-/dev/ttyACM0}" || echo "no arm bus at ${SO101_PORT:-/dev/ttyACM0}; sim/loopback only"'
    timeout_secs: 5
    critical: false
init:
  - label: start dora bridge dataflow
    command: cd /opt/octos-dora-bridge && MUJOCO_GL=egl dora up && dora start dataflows/so101-mujoco-bridge.yaml
    timeout_secs: 30
    critical: true
  - label: move arm to home
    command: |
      curl -fsS -X POST http://127.0.0.1:8768/tools/vendor.moveit.arm.move_to_named \
        -H "Content-Type: application/json" \
        -d '{"args":{"name":"home"}}' -m 30
    timeout_secs: 45
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
    command: curl -fsS -X POST http://127.0.0.1:8768/tools/robot.estop -H "Content-Type: application/json" -d '{"args":{"reason":"emergency"}}' -m 5
    timeout_secs: 5
    critical: true
---

# SO-101 / Adora Pick-and-Place with Vision + Calibration

You control an SO-101 (or Adora, 1.15x scaled) arm with a gripper and RGB camera
through a local HTTP bridge at `http://127.0.0.1:8768`. Motion verbs are
auto-discovered from the robot's capabilities advert; high-level tools (pick,
place, detect blocks, calibrate, grasp) are provided by the imperative skill pack
at `/home/dora/.octos/skills/so101-pick-cube`.

## Robot selection

Use `--robot` to switch between supported arms:

| Flag | Description |
|------|-------------|
| `--robot so101` (default) | SO-101 5-DOF arm |
| `--robot adora` | Adora 1.15x scaled SO-101 |

## Tools

| Tool | Input | Output |
|------|-------|--------|
| `get_dropoff_position` | *(none)* | `x=0.250, y=0.000` (plate position from manifest) |
| `pick_cube_at` | `{"x": 0.15, "y": 0.05, "z": 0.02}` | picks cube at given base-frame coordinates |
| `place_cube_at` | `{"x": 0.25, "y": 0.0}` | places held cube at target |
| `move_to` | `{"x": 0.20, "y": 0.10, "z": 0.05}` | pure Cartesian movement (no gripper) |
| `set_gripper` | `{"action": "open"\|"close"}` | open or close gripper independently |
| `detect_blocks` | `{"colors": ["yellow"]}` (optional) | detect colored blocks via camera |
| `capture_chessboard` | `{"square_size_mm": 25}` | capture chessboard image for calibration |
| `calibrate_camera` | `{"square_size_mm": 25}` | run camera intrinsics calibration |
| `hand_eye_collect` | `{"square_size_mm": 25}` | record one hand-eye calibration pose |
| `hand_eye_solve` | `{"method": "park"}` | solve AX=XB hand-eye calibration |
| `grasp_block` | `{"color": "yellow"}` | full autonomous pick-and-place via vision |

## Motion verbs (from bridge auto-discovery)

- `vendor.moveit.arm.move_to_joint_state` — `{"joints": [j1..j5]}` (radians)
- `vendor.moveit.arm.move_to_named` — `{"name": "home"\|"safe"\|"zero"\|"up"}`
- `vendor.moveit.arm.gripper.set` — `{"width": 0.03}` (meters)
- `vendor.moveit.arm.gripper.open` / `vendor.moveit.arm.gripper.close`

## Calibration workflow

1. Print `calibration/chessboard_9x6.png`, measure square size in mm
2. Run `capture_chessboard` 5+ times with chessboard at different positions/angles
3. Run `calibrate_camera` to compute camera intrinsics
4. Fix chessboard on table. Run `move_to` to position arm, then `hand_eye_collect`. Repeat 6+ times at different poses.
5. Run `hand_eye_solve` to compute T_cam_in_wrist and Z_table
6. Now `grasp_block` works — detects colored blocks and autonomously picks them up

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `SKILL_PACK` | `/home/dora/.octos/skills/so101-pick-cube` | imperative code location |
| `MODEL_NAME` | `${SKILL_PACK}/mjcf/so101/so101_new_calib.xml` | MuJoCo XML for IK |
| `ROBOT_MANIFEST` | `${SKILL_PACK}/manifests/so101-hw.json` | arm_skills per-robot tuning |
| `ARM_BRIDGE_URL` | `http://127.0.0.1:8768` | SPEC bridge |

## Sim vs hardware

- **Sim:** `so101-mujoco-bridge.yaml` dataflow (MuJoCo simulation)
- **Hardware:** `so101-hw-bridge.yaml` dataflow (LeRobot → Feetech serial bus)

## Error codes

| Code | Meaning | What to do |
|------|---------|------------|
| `VENDOR_ERROR` | planning/execution failure | surface `msg`; try another pose |
| `CONTROLLER_BUSY` | another caller holds the motion slot | `robot.release_control` then retry |
| `BRIDGE_TIMEOUT` | no `cmd_response` within timeout | raise `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | bridge lost its dora session | operator-side recovery |
