#!/usr/bin/env bash
# ============================================================================
#  octos LLM agent drives the reBotArm B601-DM pick-and-place from a sentence.
#
#  Same octos skill architecture as run-arm-agent.sh (the UR5e demo): an LLM
#  (Ollama qwen3:8b) reads your sentence, senses the red cube + green plate, and
#  sequences the skill tools (get_ball_position / get_plate_position / pick_at /
#  place_at). Only the ROBOT changes — the model, config, gripper mapping, and a
#  handful of grasp-geometry env vars. The qpos layout is identical (object
#  freejoint first) so the skill code is shared verbatim.
#
#  RUN IT (from a terminal inside the epyc remote desktop, so the viewer shows):
#      bash ~/dorarobotics-test/run-rebot-agent.sh
#      bash ~/dorarobotics-test/run-rebot-agent.sh "put the red block on the green plate"
#
#  Headless (no viewer, for logs):   HEADLESS=1 bash ~/dorarobotics-test/run-rebot-agent.sh
#  Tear down: Ctrl-C.
# ============================================================================
set -uo pipefail
export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
BR=$ROOT/octos-dora-bridge
# Live dataflow derived from octos-dora-bridge/dataflows/rebot-mujoco-bridge.yaml
# (placed inside the dora-moveit2 example dir so ./venv-python + relative node
#  paths resolve). See the bring-up runbook / manual_skill.md.
SRC=$ROOT/rebot-mujoco-live.yml
YML=$ROOT/rebot-agent.yml
URL=http://127.0.0.1:8768
BALL=http://127.0.0.1:8779/ball
MODEL=/home/demo/Public/github_dora_nav_moveit/dora-moveit2/examples/move_group_demo/models/rebot_pickplace.xml
OLLAMA_BASE="${OLLAMA_BASE:-http://127.0.0.1:11434/v1}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
LOG=/tmp/rebot-agent.log
HEADLESS="${HEADLESS:-0}"
SENTENCE="${*:-Pick up the red block and place it on the green plate}"
# DRIVER=agent (default): octos LLM agent plans from the sentence.
# DRIVER=skill: deterministic skill-level sequence (no LLM) — for geometry tuning.
DRIVER="${DRIVER:-agent}"

# ---- reBot grasp geometry (override per-run; tuned live on epyc) ----
ARM_HOME="${ARM_HOME:-0.0,-1.0,-1.5,0.0,0.0,0.0}"
GRASP_BIAS="${GRASP_BIAS:-0.0}"     # pure sim — no live-arm undershoot to compensate
GRASP_Z="${GRASP_Z:-0.02}"          # red cube center height (half-size 0.02)
PLACE_Z="${PLACE_Z:-0.03}"
APPROACH_Z="${APPROACH_Z:-0.18}"
LIFT_ZS="${LIFT_ZS:-0.06,0.10,0.18}"
GRIP_OPEN_W="${GRIP_OPEN_W:-0.085}"
GRIP_CLOSE_W="${GRIP_CLOSE_W:-0.0}"

die() { echo "[rebot-agent] ERROR: $*" >&2; exit 1; }

# ---- preflight ----
echo "[rebot-agent] preflight checks…"
[ -f "$MODEL" ] || die "MuJoCo model not found: $MODEL"
[ -f "$SRC" ] || die "live dataflow not found: $SRC (derive it from dataflows/rebot-mujoco-bridge.yaml — see runbook)"
command -v dora >/dev/null || die "dora CLI not on PATH ($HOME/.cargo/bin)"
if [ "$DRIVER" = "agent" ]; then
  curl -fsS -m4 "${OLLAMA_BASE%/v1}/api/tags" >/dev/null 2>&1 \
    || die "Ollama not reachable at $OLLAMA_BASE (start it: 'ollama serve')"
  curl -fsS -m4 "${OLLAMA_BASE%/v1}/api/tags" 2>/dev/null | grep -q "$OLLAMA_MODEL" \
    || die "Ollama model '$OLLAMA_MODEL' not pulled (run: 'ollama pull $OLLAMA_MODEL')"
  OCTOS_PY_DIR="${OCTOS_PY_DIR:-$ROOT}" "$PY" - <<'PYCHK' || die "python deps missing (need openai + octos_py)"
import os, sys
sys.path.insert(0, os.environ.get("OCTOS_PY_DIR"))
import openai            # noqa
import octos_py.agent    # noqa
PYCHK
  echo "[rebot-agent] preflight OK (model, dora, Ollama+$OLLAMA_MODEL, octos_py, openai)"
else
  echo "[rebot-agent] preflight OK (model, dora; DRIVER=skill — no LLM needed)"
fi

# ---- build the dataflow: viewer/headless flag, executor speed, ball_state node ----
if [ "$HEADLESS" = "1" ]; then
  cp "$SRC" "$YML"
else
  sed -e 's|MUJOCO_HEADLESS: "1"|MUJOCO_HEADLESS: "0"\n      DISPLAY: ":0"|' "$SRC" > "$YML"
fi
sed -i "/env: {.*ROBOT_CONFIG_MODULE/ s| }|, EXEC_INTERP_SPEED: \"${EXEC_INTERP_SPEED:-0.3}\" }|" "$YML"
cat >> "$YML" <<YAML

  - id: ball_state
    path: $PY
    args: $BR/examples/ball_state.py
    env: { BALL_HTTP_HOST: "127.0.0.1", BALL_HTTP_PORT: "8779" }
    inputs:
      joint_positions: mujoco_sim/joint_positions
YAML

cleanup() {
  echo "[rebot-agent] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  pkill -f octos_spec_bridge 2>/dev/null || true
  pkill -f ball_state.py 2>/dev/null || true
  pkill -f dora_mujoco 2>/dev/null || true
}
trap cleanup EXIT

# ---- robust dora bring-up: kill ALL node orphans + free ports (see run-arm-agent.sh) ----
echo "[rebot-agent] resetting dora daemon + killing node orphans + freeing ports…"
pkill -9 -f "dora_mujoco|move_group_demo|moveit_arm_node|octos_spec_bridge|ball_state|trajectory_execution|planning_scene" 2>/dev/null || true
fuser -k 8768/tcp 8779/tcp 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true
sleep 3
fuser 8768/tcp >/dev/null 2>&1 && die "port 8768 still held after cleanup (kill it: fuser -k 8768/tcp)"
dora up >/dev/null 2>&1 || true
ready=0
for _ in $(seq 1 15); do
  if dora list >/dev/null 2>&1; then ready=1; break; fi
  dora up >/dev/null 2>&1 || true
  sleep 1
done
[ "$ready" = 1 ] || die "dora coordinator never came up (try: dora destroy && dora up)"

echo "[rebot-agent] starting dataflow (log: $LOG)…"
dora start "$YML" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[rebot-agent] waiting for bridge + object server (up to 5 min)…"
bridge_ok=0
for _ in $(seq 1 300); do
  curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && { bridge_ok=1; break; }
  kill -0 "$DORA_PID" 2>/dev/null || { echo "[rebot-agent] dataflow exited early:"; tail -30 "$LOG"; exit 1; }
  sleep 1
done
[ "$bridge_ok" = 1 ] || die "bridge /healthz never came up — see $LOG (tail: $(tail -3 "$LOG"))"
ball_ok=0
for _ in $(seq 1 30); do curl -fsS -m2 "$BALL" >/dev/null 2>&1 && { ball_ok=1; break; }; sleep 1; done
[ "$ball_ok" = 1 ] || die "object-state server never came up — see $LOG"

echo
if [ "$DRIVER" = "agent" ]; then
  echo "[rebot-agent] >>> handing this sentence to the octos agent ($OLLAMA_MODEL):"
  echo "[rebot-agent] >>> \"$SENTENCE\""
  CMD=("$PY" "$BR/examples/arm_agent.py" "$SENTENCE")
else
  echo "[rebot-agent] >>> running deterministic skill-level pick-and-place (no LLM)"
  CMD=("$PY" "$BR/examples/skill_pickplace.py")
fi
echo
ARM_BRIDGE_URL="$URL" BALL_URL="$BALL" MODEL_NAME="$MODEL" \
  OBJECT_NOUN="${OBJECT_NOUN:-red cube}" ROBOT_NAME="${ROBOT_NAME:-reBotArm B601-DM}" \
  PLATE_X="${PLATE_X:-0.25}" PLATE_Y="${PLATE_Y:-0.0}" \
  ARM_HOME="$ARM_HOME" GRASP_BIAS="$GRASP_BIAS" GRASP_Z="$GRASP_Z" PLACE_Z="$PLACE_Z" \
  APPROACH_Z="$APPROACH_Z" LIFT_ZS="$LIFT_ZS" \
  GRIP_OPEN_W="$GRIP_OPEN_W" GRIP_CLOSE_W="$GRIP_CLOSE_W" \
  OCTOS_PY_DIR="${OCTOS_PY_DIR:-$ROOT}" \
  OLLAMA_BASE="$OLLAMA_BASE" OLLAMA_MODEL="$OLLAMA_MODEL" \
  "${CMD[@]}"

if [ "$HEADLESS" = "1" ]; then
  echo "[rebot-agent] headless run done."
else
  echo "[rebot-agent] done. Viewer + dataflow stay up — Ctrl-C to tear down."
  wait "$DORA_PID"
fi
