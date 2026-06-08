#!/usr/bin/env bash
# ============================================================================
#  octos LLM agent drives the UR5e pick-and-place from a natural-language sentence.
#
#  An LLM (Ollama qwen3:8b) reads your sentence, senses the red ball + green plate,
#  and sequences the skill tools (get_ball_position / get_plate_position / pick_at /
#  place_at). The skills solve IK on demand and call the bridge verbs — the robot
#  executes the SAME way as the scripted demo, but the PLAN is the LLM's.
#
#  RUN IT (from a terminal inside the epyc remote desktop, so the viewer shows):
#      bash ~/dorarobotics-test/run-arm-agent.sh
#      bash ~/dorarobotics-test/run-arm-agent.sh "put the red ball on the green plate"
#
#  Headless (no viewer, for logs):   HEADLESS=1 bash ~/dorarobotics-test/run-arm-agent.sh
#  Tear down: Ctrl-C.
# ============================================================================
set -uo pipefail
export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
BR=$ROOT/octos-dora-bridge
SRC=$ROOT/ur5e-mujoco-live.yml
YML=$ROOT/ur5e-agent.yml
URL=http://127.0.0.1:8768
BALL=http://127.0.0.1:8779/ball
MODEL=/home/demo/Public/github_dora_nav_moveit/dora-moveit2/examples/move_group_demo/models/ur5e.xml
OLLAMA_BASE="${OLLAMA_BASE:-http://127.0.0.1:11434/v1}"
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3:8b}"
LOG=/tmp/arm-agent.log
HEADLESS="${HEADLESS:-0}"
SENTENCE="${*:-Pick up the red ball and place it on the green plate}"

die() { echo "[agent] ERROR: $*" >&2; exit 1; }

# ---- preflight: fail early with a clear message if a prerequisite is missing ----
echo "[agent] preflight checks…"
[ -f "$MODEL" ] || die "MuJoCo model not found: $MODEL"
command -v dora >/dev/null || die "dora CLI not on PATH ($HOME/.cargo/bin)"
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
echo "[agent] preflight OK (model, dora, Ollama+$OLLAMA_MODEL, octos_py, openai)"

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
  echo "[agent] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  pkill -f octos_spec_bridge 2>/dev/null || true
  pkill -f ball_state.py 2>/dev/null || true
  pkill -f dora_mujoco 2>/dev/null || true
}
trap cleanup EXIT

# ---- robust dora bring-up: ensure the coordinator actually answers before start ----
echo "[agent] resetting dora daemon…"
pkill -f octos_spec_bridge 2>/dev/null || true; pkill -f ball_state.py 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true
sleep 2
dora up >/dev/null 2>&1 || true
ready=0
for _ in $(seq 1 15); do
  if dora list >/dev/null 2>&1; then ready=1; break; fi
  dora up >/dev/null 2>&1 || true
  sleep 1
done
[ "$ready" = 1 ] || die "dora coordinator never came up (try: dora destroy && dora up)"

echo "[agent] starting dataflow (log: $LOG)…"
dora start "$YML" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[agent] waiting for bridge + ball server…"
for _ in $(seq 1 90); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && break; \
  kill -0 "$DORA_PID" 2>/dev/null || { echo "[agent] dataflow exited early:"; tail -30 "$LOG"; exit 1; }; sleep 1; done
for _ in $(seq 1 30); do curl -fsS -m2 "$BALL" >/dev/null 2>&1 && break; sleep 1; done

echo
echo "[agent] >>> handing this sentence to the octos agent ($OLLAMA_MODEL):"
echo "[agent] >>> \"$SENTENCE\""
echo
ARM_BRIDGE_URL="$URL" BALL_URL="$BALL" MODEL_NAME="$MODEL" \
  PLATE_X="${PLATE_X:-0.25}" PLATE_Y="${PLATE_Y:-0.0}" \
  OCTOS_PY_DIR="${OCTOS_PY_DIR:-$ROOT}" \
  OLLAMA_BASE="$OLLAMA_BASE" OLLAMA_MODEL="$OLLAMA_MODEL" \
  "$PY" "$BR/examples/arm_agent.py" "$SENTENCE"

if [ "$HEADLESS" = "1" ]; then
  echo "[agent] headless run done."
else
  echo "[agent] done. Viewer + dataflow stay up — Ctrl-C to tear down."
  wait "$DORA_PID"
fi
