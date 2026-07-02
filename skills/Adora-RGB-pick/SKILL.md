---
name: Adora-RGB-pick
description: ADORA RGB camera pick-and-place with hand-eye calibration, black-box drop-off detection, and SPEC-VENDOR-NODE-V1 bridge control
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
    command: |
      bash -lc 'for d in "${OCTOS_SKILL_DIR:-}" "$PWD" "$HOME/.octos/skills/Adora-RGB-pick"; do [ -n "$d" ] && [ -x "$d/start_bridge.sh" ] && exec "$d/start_bridge.sh"; done; echo "start_bridge.sh not found" >&2; exit 1'
    timeout_secs: 90
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
    command: |
      bash -lc 'NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost curl -fsS -m 2 http://127.0.0.1:8768/healthz'
    timeout_secs: 3
    retries: 10
    critical: true
shutdown:
  - label: stop dora dataflow
    command: |
      bash -lc 'for d in "${OCTOS_SKILL_DIR:-}" "$PWD" "$HOME/.octos/skills/Adora-RGB-pick"; do [ -n "$d" ] && [ -x "$d/stop_bridge.sh" ] && exec "$d/stop_bridge.sh"; done; echo "stop_bridge.sh not found" >&2; exit 0'
    timeout_secs: 10
    critical: false
emergency_shutdown:
  - label: estop via bridge
    command: |
      NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost \
        curl -fsS -X POST http://127.0.0.1:8768/tools/robot.estop \
          -H "Content-Type: application/json" \
          -d '{"args":{"reason":"emergency"}}' -m 5
    timeout_secs: 5
    critical: true
---

# SO-101 / Adora Pick-and-Place with Vision + Calibration

You control an SO-101 (or Adora, 1.15x scaled) arm with a gripper and RGB camera
through a local HTTP bridge at `http://127.0.0.1:8768`. Motion verbs are
auto-discovered from the robot's capabilities advert; high-level tools (pick,
place, detect blocks, calibrate, grasp) are provided by the imperative skill pack
at `/home/dora/.octos/skills/Adora-RGB-pick`.

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
| `set_gripper` | `{"action": "open"\|"close"}` or `{"width": 0.03}` | open or close gripper independently; optional `width` (meters) overrides default |
| `detect_blocks` | `{"colors": ["yellow"]}` (optional) | detect colored blocks via camera |
| `locate_dropoff` | `{}` | detect the moving black drop-off box and return its visual center in base coordinates |
| `place_held_above` | `{"x": 0.30, "y": 0.0}` | move the held cube above the detected drop-off center; default z uses `approach_z` |
| `place_held_down` | `{"x": 0.30, "y": 0.0, "z": -0.06}` | lower the held cube to release height |
| `release_cube` | `{}` | open gripper and release the currently held cube |
| `retract_after_release` | `{"x": 0.30, "y": 0.0}` | raise the arm after release |
| `capture_chessboard` | `{"square_size_mm": 25}` | capture chessboard image for calibration |
| `calibrate_camera` | `{"square_size_mm": 25}` | run camera intrinsics calibration |
| `hand_eye_collect` | `{"square_size_mm": 25}` | record one hand-eye calibration pose |
| `hand_eye_solve` | `{"method": "park"}` | solve AX=XB hand-eye calibration |
| `grasp_block` | `{"color": "yellow"}` | full autonomous pick-and-place via vision |

## Yellow Block To Black Box Workflow

When the user asks to put the yellow block into the black box, decompose the task
with these tools instead of using a single hidden macro:

1. `grasp_block` with `{"color": "yellow"}`.
2. `locate_dropoff` with `{}`.
3. Read `adjusted_base` from `locate_dropoff`; if missing, use `center_base`. Use
   the first two values as `x` and `y`.
4. `place_held_above` with `{"x": x, "y": y}`.
5. `place_held_down` with `{"x": x, "y": y, "z": -0.06}`.
6. `release_cube` with `{}`.
7. `retract_after_release` with `{"x": x, "y": y}`.

Do not use `move_to` to simulate grasping or releasing. `grasp_block` performs the
real gripper close, and `release_cube` performs the real gripper open.

Hidden backup: `main` still contains a non-manifest `grasp_yellow_to_black_box`
macro. Its purpose is to run the full fixed sequence in code when deterministic
execution is needed. It is intentionally not listed in `manifest.json` right now
so Octos chat will let the LLM plan the sequence from visible tools.

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
| `SKILL_PACK` | `/home/dora/.octos/skills/Adora-RGB-pick` | imperative code location |
| `MODEL_NAME` | `${SKILL_PACK}/mjcf/so101/so101_new_calib.xml` | MuJoCo XML for IK |
| `ROBOT_MANIFEST` | `${SKILL_PACK}/manifests/so101-hw.json` | arm_skills per-robot tuning |
| `ARM_BRIDGE_URL` | `http://127.0.0.1:8768` | SPEC bridge |

## ADORA bridge startup

Normally no environment variables are required:

```bash
bash /home/dora/.octos/skills/Adora-RGB-pick/start_bridge.sh
```

The startup script reads `dataflows/adora-hw-bridge.yaml` as a template and
generates the machine-local runtime file:

```text
.adora-hw-run/adora-hw-bridge.yml
```

Use these variables only when overriding the defaults:

| Variable | Default | Purpose |
|----------|---------|---------|
| `ADORA_RUN_DIR` | `${OCTOS_DORA_BRIDGE}/.adora-hw-run` | runtime output directory for resolved YAML, manifest, logs, and dora session files |
| `ADORA_DORA_DATAFLOW` | *(empty)* | use an explicit resolved dataflow instead of generating from `dataflows/adora-hw-bridge.yaml` |
| `ADORA_ROBOT_ID` | `adora-hw-001` | robot id advertised by `moveit_arm` and the HTTP bridge |
| `ADORA_PORT` | `/dev/ttyACM0` | serial device written into the generated hardware manifest |
| `ADORA_ROBOT_MANIFEST` | `${ADORA_RUN_DIR}/adora-hw-dora-manifest.json` | hardware manifest consumed by `rebot_hw_node` |
| `ADORA_VENV_PYTHON` | auto-detected | Python executable/wrapper used by all dora nodes |
| `DORA_MOVEIT2` | auto-detected | local `dora-moveit2` checkout used for planner, IK, and trajectory executor node paths |
| `ADORA_EXEC_INTERP_SPEED` | `0.25` | trajectory interpolation speed passed to `trajectory_executor.py` |
| `ADORA_HW_TICK_MS` | `50` | hardware node tick period |
| `ADORA_EXEC_TICK_MS` | `80` | trajectory executor tick period |
| `ADORA_HTTP_HOST` | `127.0.0.1` | bridge HTTP bind host |
| `ADORA_HTTP_PORT` | `8768` | bridge HTTP bind port |
| `ADORA_CMD_TIMEOUT_S` | `90` | bridge command timeout |
| `ADORA_HEARTBEAT_TIMEOUT_MS` | `0` | moveit-arm heartbeat timeout; `0` disables it for this hardware flow |
| `ADORA_DORA_CONTROL_PORT` | `6112` | dora control port used by `dora list/start/stop` |
| `ADORA_DORA_DAEMON_PORT` | `6113` | dora coordinator port used by the isolated daemon |
| `ADORA_DORA_LISTEN_PORT` | `6114` | local daemon listen port |

Older `SO101_*` startup variables remain accepted as compatibility aliases where
the script historically used them.

## Reproducible Python environment

Use one robot runtime venv instead of relying on packages from `~/.local`,
Conda, or a generated `.adora-hw-run` directory:

```bash
cd /path/to/octos-dora-bridge
bash scripts/setup_adora_hw.sh
```

The manual equivalent is:

```bash
cd /path/to/octos-dora-bridge
python3 -m venv /path/to/adora-venv
/path/to/adora-venv/bin/python -m pip install --upgrade pip
/path/to/adora-venv/bin/python -m pip install -e '.[adora-hw]'

/path/to/adora-venv/bin/python -m pip install --no-deps -e bridge
/path/to/adora-venv/bin/python -m pip install --no-deps -e /path/to/moveit-arm-dora-node
/path/to/adora-venv/bin/python -m pip install --no-deps -e /path/to/rebot-hw-dora-node
/path/to/adora-venv/bin/python -m pip install --no-deps -e /path/to/dora-moveit2/dora_moveit
/path/to/adora-venv/bin/python -m pip install --no-deps -e /path/to/dora-moveit2/examples/move_group_demo
```

Then run the bridge with that interpreter:

```bash
ADORA_VENV_PYTHON=/path/to/adora-venv/bin/python \
DORA_MOVEIT2=/path/to/dora-moveit2 \
bash /home/dora/.octos/skills/Adora-RGB-pick/start_bridge.sh
```

The Feetech/SCS servo Python module is currently not represented by a standard
PyPI package in this repo. The runtime must be able to `import scservo_sdk`;
install it from the vendor source used by your hardware stack, or copy the
known-good `scservo_sdk/` package into the venv's `site-packages`.

The `adora-hw` extra pins the validated PyPI runtime. Keep sibling repository
installs on `--no-deps` unless their package metadata has been updated to the
same Dora runtime version; otherwise pip can silently replace the working
`dora-rs`/`pyarrow` pair.

Check the environment before starting hardware:

```bash
/path/to/adora-venv/bin/python - <<'PY'
import dora, draccus, lerobot, torch, uvicorn
import octos_spec_bridge, moveit_arm_node, rebot_hw_node, dora_moveit
import scservo_sdk
print("adora hw venv ok")
PY
```

## Sim vs hardware

- **Sim:** `so101-mujoco-bridge.yaml` dataflow (MuJoCo simulation)
- **SO101 hardware:** `so101-hw-bridge.yaml` dataflow (LeRobot → Feetech serial bus)
- **ADORA hardware:** `dataflows/adora-hw-bridge.yaml` template resolved to `.adora-hw-run/adora-hw-bridge.yml`

## Error codes

| Code | Meaning | What to do |
|------|---------|------------|
| `VENDOR_ERROR` | planning/execution failure | surface `msg`; try another pose |
| `CONTROLLER_BUSY` | another caller holds the motion slot | `robot.release_control` then retry |
| `BRIDGE_TIMEOUT` | no `cmd_response` within timeout | raise `CMD_TIMEOUT_S` |
| `BRIDGE_DOWN` | bridge lost its dora session | operator-side recovery |
