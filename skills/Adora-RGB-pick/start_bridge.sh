#!/usr/bin/env bash
set -euo pipefail

export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_bridge_repo() {
  local candidates=(
    "${OCTOS_DORA_BRIDGE:-}"
    "$SKILL_DIR/../.."
    "$SKILL_DIR/../skills/octos-dora-bridge"
    "$HOME/.octos/skills/skills/octos-dora-bridge"
    "$HOME/octos-dora-bridge"
  )
  local d
  for d in "${candidates[@]}"; do
    [ -n "$d" ] || continue
    if [ -d "$d/dataflows" ] && [ -d "$d/bridge" ]; then
      cd "$d" && pwd
      return 0
    fi
  done
  return 1
}

BRIDGE_REPO="$(find_bridge_repo)" || {
  echo "could not find octos-dora-bridge; set OCTOS_DORA_BRIDGE=/path/to/octos-dora-bridge" >&2
  exit 1
}

RUN_DIR="${ADORA_RUN_DIR:-${SO101_BRIDGE_RUN_DIR:-$BRIDGE_REPO/.adora-hw-run}}"
mkdir -p "$RUN_DIR"

find_dora_moveit2() {
  local candidates=(
    "${DORA_MOVEIT2:-}"
    "$BRIDGE_REPO/../dora-moveit2"
    "$HOME/so101-sim/dora-moveit2"
    "$HOME/dora-moveit2"
  )
  local d
  for d in "${candidates[@]}"; do
    [ -n "$d" ] || continue
    if [ -f "$d/examples/move_group_demo/move_group_demo/nodes/trajectory_executor.py" ]; then
      cd "$d" && pwd
      return 0
    fi
  done
  return 1
}

write_default_adora_manifest() {
  local manifest="$1"
  [ -f "$manifest" ] && return 0
  mkdir -p "$(dirname "$manifest")"
  cat > "$manifest" <<EOF
{
  "lerobot_class": "lerobot.robots.so_follower.SO101Follower",
  "robot_id": "adora",
  "port": "${ADORA_PORT:-${SO101_PORT:-/dev/ttyACM0}}",
  "use_degrees": true,
  "num_joints": 5,
  "arm_qpos_start": 7,
  "gripper_slots": 1,
  "motor_names": ["shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll"],
  "gripper_name": "gripper",
  "arm_home": [-0.108172, -0.959931, 0.529353, 1.386290, -0.822414],
  "signs": [1, 1, 1, 1, 1],
  "offsets": [0, 0, 0, 0, 0],
  "grip_open_w": 0.06,
  "grip_open_pct": 100.0,
  "grip_closed_pct": 0.0,
  "max_relative_target": 10.0,
  "hold_full_orientation": false
}
EOF
}

resolve_adora_dataflow() {
  local template="$BRIDGE_REPO/dataflows/adora-hw-bridge.yaml"
  [ -f "$template" ] || {
    echo "missing ADORA dataflow template: $template" >&2
    exit 1
  }

  local dora_moveit2
  dora_moveit2="$(find_dora_moveit2)" || {
    echo "DORA_MOVEIT2 is required; set DORA_MOVEIT2=/path/to/dora-moveit2" >&2
    exit 1
  }

  local venv_py="${ADORA_VENV_PYTHON:-${SO101_VENV_PYTHON:-}}"
  if [ -z "$venv_py" ]; then
    if [ -x "$RUN_DIR/venv-python" ]; then
      venv_py="$RUN_DIR/venv-python"
    elif [ -x "$BRIDGE_REPO/venv-python" ]; then
      venv_py="$BRIDGE_REPO/venv-python"
    else
      local py="${PYTHON:-python3}"
      cat > "$RUN_DIR/venv-python" <<EOF
#!/usr/bin/env bash
exec "$("$py" -c 'import sys; print(sys.executable)')" "\$@"
EOF
      chmod +x "$RUN_DIR/venv-python"
      venv_py="$RUN_DIR/venv-python"
    fi
  fi

  local manifest="${ADORA_ROBOT_MANIFEST:-$RUN_DIR/adora-hw-dora-manifest.json}"
  write_default_adora_manifest "$manifest"

  local resolved="$RUN_DIR/adora-hw-bridge.yml"
  sed -e "s|__VENV_PY__|$venv_py|g" \
      -e "s|__DORA_MOVEIT2__|$dora_moveit2|g" \
      -e "s|__ADORA_ROBOT_MANIFEST__|$manifest|g" \
      -e "s|__ADORA_ROBOT_ID__|${ADORA_ROBOT_ID:-adora-hw-001}|g" \
      -e "s|__ADORA_HW_TICK_MS__|${ADORA_HW_TICK_MS:-50}|g" \
      -e "s|__ADORA_EXEC_TICK_MS__|${ADORA_EXEC_TICK_MS:-80}|g" \
      -e "s|__ADORA_EXEC_INTERP_SPEED__|${ADORA_EXEC_INTERP_SPEED:-0.25}|g" \
      -e "s|__ADORA_PLANNER_TYPE__|${ADORA_PLANNER_TYPE:-simple}|g" \
      -e "s|__ADORA_IK_SOLVER_TYPE__|${ADORA_IK_SOLVER_TYPE:-de}|g" \
      -e "s|__ADORA_HEARTBEAT_TIMEOUT_MS__|${ADORA_HEARTBEAT_TIMEOUT_MS:-0}|g" \
      -e "s|__ADORA_HTTP_HOST__|${ADORA_HTTP_HOST:-127.0.0.1}|g" \
      -e "s|__ADORA_HTTP_PORT__|${ADORA_HTTP_PORT:-8768}|g" \
      -e "s|__ADORA_CMD_TIMEOUT_S__|${ADORA_CMD_TIMEOUT_S:-90}|g" \
      "$template" > "$resolved"
  DATAFLOW="$resolved"
}

MODE="${ADORA_BRIDGE_MODE:-${SO101_BRIDGE_MODE:-hw}}"
DATAFLOW="${ADORA_DORA_DATAFLOW:-${SO101_DORA_DATAFLOW:-}}"
DEFAULT_ADORA_DATAFLOW="$RUN_DIR/adora-hw-bridge.yml"
if [ -n "$DATAFLOW" ] && [ ! -f "$DATAFLOW" ]; then
  case "$DATAFLOW" in
    "$DEFAULT_ADORA_DATAFLOW")
      DATAFLOW=""
      ;;
    *)
      echo "configured dataflow does not exist: $DATAFLOW" >&2
      echo "unset ADORA_DORA_DATAFLOW/SO101_DORA_DATAFLOW, or point it at an existing resolved YAML" >&2
      exit 1
      ;;
  esac
fi

if [ -z "$DATAFLOW" ]; then
  case "$MODE" in
    hw|hardware|adora|adora-hw)
      resolve_adora_dataflow
      ;;
    sim|mujoco)
      if [ -f "$BRIDGE_REPO/so101-mujoco-bridge-ballstate.yaml" ]; then
        DATAFLOW="$BRIDGE_REPO/so101-mujoco-bridge-ballstate.yaml"
      elif [ -f "$BRIDGE_REPO/so101-mujoco-bridge-resolved.yaml" ]; then
        DATAFLOW="$BRIDGE_REPO/so101-mujoco-bridge-resolved.yaml"
      else
        DATAFLOW="$BRIDGE_REPO/dataflows/so101-mujoco-bridge.yaml"
      fi
      ;;
    *)
      echo "unknown ADORA_BRIDGE_MODE=$MODE; expected hw or sim" >&2
      exit 1
      ;;
  esac
fi

VENV_PY="${ADORA_VENV_PYTHON:-${SO101_VENV_PYTHON:-}}"
if [ -z "$VENV_PY" ]; then
  if [ -x "$BRIDGE_REPO/venv-python" ]; then
    VENV_PY="$BRIDGE_REPO/venv-python"
  else
    PY="${PYTHON:-python3}"
    cat > "$RUN_DIR/venv-python" <<EOF
#!/usr/bin/env bash
exec "$("$PY" -c 'import sys; print(sys.executable)')" "\$@"
EOF
    chmod +x "$RUN_DIR/venv-python"
    VENV_PY="$RUN_DIR/venv-python"
  fi
fi

if grep -q 'path: ./venv-python' "$DATAFLOW"; then
  RESOLVED="$RUN_DIR/$(basename "$DATAFLOW")"
  sed "s|path: ./venv-python|path: $VENV_PY|g" "$DATAFLOW" > "$RESOLVED"
  DATAFLOW="$RESOLVED"
fi

COORD_PORT="${ADORA_DORA_DAEMON_PORT:-${SO101_DORA_DAEMON_PORT:-6113}}"
CONTROL_PORT="${ADORA_DORA_CONTROL_PORT:-${SO101_DORA_CONTROL_PORT:-6112}}"
DAEMON_LISTEN_PORT="${ADORA_DORA_LISTEN_PORT:-${SO101_DORA_LISTEN_PORT:-6114}}"
NAME="${ADORA_DORA_NAME:-${SO101_DORA_NAME:-Adora-RGB-pick}}"
BRIDGE_HTTP_HOST="${ADORA_HTTP_HOST:-127.0.0.1}"
BRIDGE_HTTP_PORT="${ADORA_HTTP_PORT:-8768}"

if ! dora list --coordinator-port "$CONTROL_PORT" >/dev/null 2>&1; then
  setsid bash -c 'exec "$@"' _ dora coordinator --port "$COORD_PORT" --control-port "$CONTROL_PORT" \
    </dev/null > "$RUN_DIR/coordinator.log" 2>&1 &
  echo "$!" > "$RUN_DIR/coordinator.pid"
  sleep 2
  setsid bash -c 'exec "$@"' _ dora daemon --coordinator-addr 127.0.0.1 --coordinator-port "$COORD_PORT" \
    --local-listen-port "$DAEMON_LISTEN_PORT" </dev/null > "$RUN_DIR/daemon.log" 2>&1 &
  echo "$!" > "$RUN_DIR/daemon.pid"
  sleep 3
fi

pid_file_alive() {
  local f="$1"
  [ -f "$f" ] || return 0
  local pid
  pid="$(cat "$f" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" >/dev/null 2>&1
}

control_plane_alive() {
  pid_file_alive "$RUN_DIR/coordinator.pid" && pid_file_alive "$RUN_DIR/daemon.pid"
}

bridge_state_fresh() {
  ADORA_HTTP_HOST="$BRIDGE_HTTP_HOST" ADORA_HTTP_PORT="$BRIDGE_HTTP_PORT" python3 - "$RUN_DIR" <<'PY'
import json
import os
import sys
import urllib.request

try:
    host = os.environ.get("ADORA_HTTP_HOST", "127.0.0.1")
    port = os.environ.get("ADORA_HTTP_PORT", "8768")
    req = urllib.request.Request(
        f"http://{host}:{port}/tools/get_state",
        data=b'{"args":{}}',
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=2) as resp:
        payload = json.loads(resp.read().decode())
    data = payload.get("data", {})
    if data.get("stale"):
        raise SystemExit(1)
    if not data.get("stream"):
        raise SystemExit(1)
except Exception:
    raise SystemExit(1)
PY
}

START_OUT="$RUN_DIR/start.out"
dora start "$DATAFLOW" --name "$NAME" --detach --coordinator-port "$CONTROL_PORT" > "$START_OUT" 2>&1
UUID="$(awk '/dataflow started:/ {print $3}' "$START_OUT" | tail -1)"
if [ -n "$UUID" ]; then
  echo "$UUID" > "$RUN_DIR/dataflow.uuid"
fi
ps -eo pid=,args= | awk '
  /octos_spec_bridge|moveit_arm_node|rebot_hw_node\.node|planning_scene\.py|planner\.py|ik_solver\.py|trajectory_executor\.py/ &&
  !/awk/ {print $1}
' > "$RUN_DIR/node.pids"

for _ in $(seq 1 60); do
  if control_plane_alive &&
     curl -fsS -m 2 "http://$BRIDGE_HTTP_HOST:$BRIDGE_HTTP_PORT/healthz" >/dev/null 2>&1 &&
     bridge_state_fresh; then
    ps -eo pid=,args= | awk '
      /octos_spec_bridge|moveit_arm_node|rebot_hw_node\.node|planning_scene\.py|planner\.py|ik_solver\.py|trajectory_executor\.py/ &&
      !/awk/ {print $1}
    ' > "$RUN_DIR/node.pids"
    echo "ADORA bridge ready at http://$BRIDGE_HTTP_HOST:$BRIDGE_HTTP_PORT"
    exit 0
  fi
  sleep 1
done

echo "bridge did not become ready; dora start output:" >&2
cat "$START_OUT" >&2
"$SKILL_DIR/stop_bridge.sh" >/dev/null 2>&1 || true
exit 1
