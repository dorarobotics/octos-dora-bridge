#!/usr/bin/env bash
# Turnkey LeKiwi MuJoCo demo for epyc. Run from a terminal INSIDE the remote
# desktop so the MuJoCo window appears. Boots the dataflow (sim + nav_base +
# bridge on :8770), waits for /healthz, then drives forward/turn/stop over
# octos HTTP. Tear down with Ctrl-C.
set -euo pipefail

export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

ROOT="${ROOT:-$HOME/dorarobotics-test}"
BR="$ROOT/octos-dora-bridge"
export LEKIWI_SIM_DIR="${LEKIWI_SIM_DIR:-$ROOT/LeKiwi-sim}"
PY="${PY:-/home/demo/anaconda3/envs/dora-moveit/bin/python}"
BRIDGE_URL="http://127.0.0.1:8770"
LOG=/tmp/lekiwi-viz-dataflow.log

cleanup() {
  echo "[lekiwi-viz] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  pkill -9 -f "dora daemon" 2>/dev/null || true
  pkill -9 -f "dora coordinator" 2>/dev/null || true
  pkill -f "octos_spec_bridge" 2>/dev/null || true
  pkill -f "lekiwi_mujoco_sim" 2>/dev/null || true
}
trap cleanup EXIT

echo "[lekiwi-viz] clearing stale daemon…"
dora destroy >/dev/null 2>&1 || true
pkill -9 -f "dora daemon" 2>/dev/null || true
sleep 1

cd "$BR"
echo "[lekiwi-viz] dora up…"; dora up >/dev/null
echo "[lekiwi-viz] starting dataflow (log: $LOG)…"
dora start dataflows/lekiwi-mujoco-bridge.yaml --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[lekiwi-viz] waiting for bridge $BRIDGE_URL/healthz…"
for _ in $(seq 1 60); do
  curl -fsS -m 2 "$BRIDGE_URL/healthz" >/dev/null 2>&1 && break
  if ! kill -0 "$DORA_PID" 2>/dev/null; then
    echo "[lekiwi-viz] dataflow exited early — see $LOG"; tail -30 "$LOG"; exit 1
  fi
  sleep 1
done

echo "[lekiwi-viz] running scripted demo…"
LEKIWI_BRIDGE_URL="$BRIDGE_URL" "$PY" "$BR/examples/lekiwi_demo_driver.py"

echo "[lekiwi-viz] demo finished. Viewer + dataflow stay up — Ctrl-C to tear down."
wait "$DORA_PID"
