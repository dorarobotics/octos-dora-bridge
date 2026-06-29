#!/usr/bin/env bash
# Turnkey visual nav-base demo for epyc. Run from a terminal INSIDE the remote
# desktop (so the rerun viewer appears). Boots a kinematic toy sim + rerun viewer
# + nav-base node + bridge, then drives a scripted skill sequence over octos HTTP
# (:8769). Watch the blue robot box drive to goals, spin, stop, and halt on estop.
#
#   bash ~/dorarobotics-test/run-nav-viz.sh
#
# Tear down with Ctrl-C.
#
# Box autodetect: this is the epyc launcher (rerun viewer, ~/dorarobotics-test).
# On the asus box (GPU-less, ~/octos-deploy) rerun's GL viewer renders BLACK over
# RustDesk/NoMachine, so we delegate to the matplotlib variant there instead.
set -euo pipefail

if [ ! -d "$HOME/dorarobotics-test" ] && [ -d "$HOME/octos-deploy" ]; then
  echo "[nav-viz] detected ~/octos-deploy (asus layout) — using run-nav-viz-asus.sh (matplotlib viewer)"
  exec bash "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run-nav-viz-asus.sh" "$@"
fi

export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
BR=$ROOT/octos-dora-bridge
VIZ=$ROOT/nav-base-viz-live.yml
BRIDGE_URL="http://127.0.0.1:8769"
LOG=/tmp/nav-viz-dataflow.log

echo "[nav-viz] DISPLAY=$DISPLAY  (rerun viewer will open on the desktop)"

# Write the absolute-path live dataflow (toy sim + rerun + nav_base + bridge).
cat > "$VIZ" <<YAML
nodes:
  - id: toy_sim
    path: $PY
    args: $BR/examples/nav_toy_sim.py
    env: { TOY_SIM_DT: "0.05", DISPLAY: ":0" }
    inputs:
      tick: dora/timer/millis/50
      goal: nav_base/dora_nav_goal
      cancel: nav_base/dora_nav_cancel
      cmd_vel: nav_base/dora_nav_cmd_vel
    outputs: [pose, status, obstacles]

  - id: nav_base
    path: $PY
    args: -m nav_base_node
    env:
      ROBOT_ID: nav-base-001
      WAYPOINTS_PATH: $ROOT/nav-base-dora-node/examples/waypoints.yaml
      HEARTBEAT_TIMEOUT_MS: "0"
      LOG_LEVEL: INFO
    inputs:
      cmd_request: bridge/cmd_request
      dora_nav_pose: toy_sim/pose
      dora_nav_status: toy_sim/status
      dora_nav_obstacles: toy_sim/obstacles
    outputs: [cmd_response, capabilities, state, safety_event, dora_nav_goal, dora_nav_cancel, dora_nav_cmd_vel]

  - id: rerun_viz
    path: $PY
    args: $BR/examples/nav_rerun_viz.py
    env: { DISPLAY: ":0" }
    inputs:
      pose: toy_sim/pose
      obstacles: toy_sim/obstacles
      status: toy_sim/status
      goal: nav_base/dora_nav_goal
      safety_event: nav_base/safety_event
    outputs: [ready]

  - id: bridge
    path: $PY
    args: -m octos_spec_bridge
    env:
      ROBOT_ID: nav-base-001
      HTTP_HOST: "127.0.0.1"
      HTTP_PORT: "8769"
      CMD_TIMEOUT_S: "30"
      LOG_LEVEL: INFO
    inputs:
      cmd_response: nav_base/cmd_response
      capabilities: nav_base/capabilities
      state: nav_base/state
      safety_event: nav_base/safety_event
    outputs: [cmd_request]
YAML

cleanup() {
  echo "[nav-viz] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  # Kill the real daemon/coordinator process names (a SPACE, not a hyphen) — dora
  # destroy alone leaks them; leftover daemons accumulate and co-spawn the dataflow.
  pkill -9 -f "dora daemon" 2>/dev/null || true
  pkill -9 -f "dora coordinator" 2>/dev/null || true
  pkill -f "octos_spec_bridge" 2>/dev/null || true
  pkill -f "nav_rerun_viz.py" 2>/dev/null || true
  pkill -f "nav_toy_sim.py" 2>/dev/null || true
}
trap cleanup EXIT

echo "[nav-viz] clearing stale processes/daemon…"
pkill -f "octos_spec_bridge" 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true
pkill -9 -f "dora daemon" 2>/dev/null || true
pkill -9 -f "dora coordinator" 2>/dev/null || true
sleep 1

echo "[nav-viz] dora up…"
dora up >/dev/null
echo "[nav-viz] starting dataflow (log: $LOG)…"
dora start "$VIZ" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[nav-viz] waiting for bridge $BRIDGE_URL/healthz…"
for _ in $(seq 1 60); do
  curl -fsS -m 2 "$BRIDGE_URL/healthz" >/dev/null 2>&1 && break
  if ! kill -0 "$DORA_PID" 2>/dev/null; then
    echo "[nav-viz] dataflow exited early — see $LOG"; tail -30 "$LOG"; exit 1
  fi
  sleep 1
done

echo "[nav-viz] running scripted skill demo…"
NAV_BRIDGE_URL="$BRIDGE_URL" "$PY" "$BR/examples/nav_demo_driver.py"

echo
echo "[nav-viz] demo finished. The viewer + dataflow stay up — Ctrl-C to tear down."
wait "$DORA_PID"
