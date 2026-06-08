#!/usr/bin/env bash
# Turnkey visual arm demo for epyc. Run from a terminal INSIDE the remote
# desktop (so the MuJoCo viewer appears). Boots the UR5e MuJoCo dataflow with the
# viewer visible, then drives a scripted skill sequence over octos HTTP (:8768).
#
#   bash ~/dorarobotics-test/run-arm-viz.sh
#
# Tear down with Ctrl-C.
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
SRC="$ROOT/ur5e-mujoco-live.yml"
VIZ="$ROOT/ur5e-mujoco-viz.yml"
BRIDGE_URL="http://127.0.0.1:8768"
LOG=/tmp/arm-viz-dataflow.log

echo "[arm-viz] DISPLAY=$DISPLAY  (MuJoCo viewer will open on the desktop)"

# Derive a viewer-on dataflow from the headless live copy.
sed -e 's|MUJOCO_HEADLESS: "1"|MUJOCO_HEADLESS: "0"\n      DISPLAY: ":0"|' "$SRC" > "$VIZ"

cleanup() {
  echo "[arm-viz] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  pkill -f "octos_spec_bridge" 2>/dev/null || true
  pkill -f "dora_mujoco/dora_mujoco/main.py" 2>/dev/null || true
}
trap cleanup EXIT

echo "[arm-viz] clearing stale processes/daemon…"
pkill -f "octos_spec_bridge" 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true
sleep 1

echo "[arm-viz] dora up…"
dora up >/dev/null
echo "[arm-viz] starting dataflow (log: $LOG)…"
dora start "$VIZ" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[arm-viz] waiting for bridge $BRIDGE_URL/healthz…"
for _ in $(seq 1 60); do
  curl -fsS -m 2 "$BRIDGE_URL/healthz" >/dev/null 2>&1 && break
  if ! kill -0 "$DORA_PID" 2>/dev/null; then
    echo "[arm-viz] dataflow exited early — see $LOG"; tail -30 "$LOG"; exit 1
  fi
  sleep 1
done

echo "[arm-viz] running scripted skill demo…"
ARM_BRIDGE_URL="$BRIDGE_URL" "$PY" "$ROOT/octos-dora-bridge/examples/arm_demo_driver.py"

echo
echo "[arm-viz] demo finished. The viewer + dataflow stay up — Ctrl-C to tear down."
wait "$DORA_PID"
