#!/usr/bin/env bash
# Reference launcher for the visual nav-base demo on the "asus" box (a GPU-less
# Ubuntu 22.04 desktop viewed over RustDesk/NoMachine). Boots: toy sim +
# matplotlib viewer (examples/nav_mpl_viz.py) + nav_base node + bridge on
# DISPLAY :0, waits for the octos bridge (:8769), then runs a continuous patrol
# loop (examples/nav_demo_loop.py).
#
# Why matplotlib instead of the rerun viewer: rerun's GL viewer renders via
# software Vulkan/llvmpipe on a GPU-less host and shows BLACK over RustDesk/
# NoMachine (the GL surface isn't captured). The matplotlib (TkAgg) window is a
# plain raster window that remote-desktop tools capture reliably.
#
# Environment this script assumes (adjust paths for other hosts):
#   - repos cloned under ~/octos-deploy/{octos-dora-bridge,nav-base-dora-node}
#   - bridge venv at octos-dora-bridge/bridge/.venv with: this bridge (editable),
#     nav-base-dora-node (editable), dora-rs==0.4.0, matplotlib (tkinter present)
#   - official dora 0.4.0 CLI on PATH (here ~/.local/bin/dora)
#   - an X session on DISPLAY :0 the remote-desktop tool is mirroring
#
# Usage:  bash scripts/run-nav-viz-asus.sh    (idempotent: cleans prior run first)
set -uo pipefail

export DISPLAY=":0"
export XAUTHORITY="$HOME/.Xauthority"
export PATH="$HOME/dora1/bin:$HOME/.cargo/bin:$PATH"

ROOT=$HOME/octos-deploy
BR=$ROOT/octos-dora-bridge
# Wrapper resolves the venv only with a relative ./venv-python-dora1 and the dataflow
# living IN dataflows/ (dora sets node CWD to the dataflow file's dir).
DRIVER_PY=$BR/bridge/.venv-dora1/bin/python
WAYPOINTS=$ROOT/nav-base-dora-node/examples/waypoints.yaml
VIZ=$BR/dataflows/nav-base-viz-live-dora1.yml
BRIDGE_URL="http://127.0.0.1:8769"
LOG=$ROOT/nav-viz-dataflow.log
STATE=$ROOT/navviz.state
: > "$STATE"
echo "DISPLAY=$DISPLAY rerun viewer opens on the desktop" >> "$STATE"

cat > "$VIZ" <<YAML
nodes:
  - id: toy_sim
    path: ./venv-python-dora1
    args: ../examples/nav_toy_sim.py
    env: { TOY_SIM_DT: "0.05", DISPLAY: ":0" }
    inputs:
      tick: dora/timer/millis/50
      goal: nav_base/dora_nav_goal
      cancel: nav_base/dora_nav_cancel
      cmd_vel: nav_base/dora_nav_cmd_vel
    outputs: [pose, status, obstacles]

  - id: nav_base
    path: ./venv-python-dora1
    args: -m nav_base_node
    env:
      ROBOT_ID: nav-base-001
      WAYPOINTS_PATH: $WAYPOINTS
      HEARTBEAT_TIMEOUT_MS: "0"
      LOG_LEVEL: INFO
    inputs:
      cmd_request: bridge/cmd_request
      dora_nav_pose: toy_sim/pose
      dora_nav_status: toy_sim/status
      dora_nav_obstacles: toy_sim/obstacles
    outputs: [cmd_response, capabilities, state, safety_event, dora_nav_goal, dora_nav_cancel, dora_nav_cmd_vel]

  - id: rerun_viz
    path: ./venv-python-dora1
    args: ../examples/nav_mpl_viz.py
    env: { DISPLAY: ":0" }
    inputs:
      pose: toy_sim/pose
      obstacles: toy_sim/obstacles
      status: toy_sim/status
      goal: nav_base/dora_nav_goal
      safety_event: nav_base/safety_event
    outputs: [ready]

  - id: bridge
    path: ./venv-python-dora1
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

# Cleanup any prior run (daemons first, then nodes).
for i in $(seq 1 8); do
  pkill -9 -f dora-coordinator 2>/dev/null
  pkill -9 -f dora-daemon 2>/dev/null
  pkill -9 -f "dora up" 2>/dev/null
  sleep 1
  [ "$(pgrep -cf 'dora-coordinator|dora-daemon')" = "0" ] && break
done
pkill -9 -f "bridge/.venv-dora1/bin/python" 2>/dev/null
sleep 2

cd "$BR"
echo "dora up" >> "$STATE"
dora up > "$ROOT/up-viz.log" 2>&1 &
sleep 8

echo "dora start (attached)" >> "$STATE"
# Use the RELATIVE dataflow path from $BR (mirrors the working headless run); an
# absolute path makes dora 0.4.0 pick a node CWD that breaks ./venv-python-dora1.
dora start dataflows/nav-base-viz-live-dora1.yml --attach > "$LOG" 2>&1 &
DORA_PID=$!

ok=0
for _ in $(seq 1 60); do
  if curl -fsS -m 2 "$BRIDGE_URL/healthz" >/dev/null 2>&1; then ok=1; break; fi
  if ! kill -0 "$DORA_PID" 2>/dev/null; then echo "DATAFLOW_EXITED_EARLY" >> "$STATE"; break; fi
  sleep 1
done

if [ "$ok" = "1" ]; then
  echo "HEALTHZ_OK starting continuous patrol loop" >> "$STATE"
  # Continuous patrol (no estop, so it never latches) — runs in background so the
  # robot keeps driving in the rerun viewer for as long as the dataflow is up.
  NAV_BRIDGE_URL="$BRIDGE_URL" setsid nohup "$DRIVER_PY" "$BR/examples/nav_demo_loop.py" \
    > "$ROOT/nav-loop.log" 2>&1 < /dev/null &
  echo "LOOP_STARTED pid=$!" >> "$STATE"
else
  echo "HEALTHZ_FAILED" >> "$STATE"
  tail -25 "$LOG" >> "$STATE" 2>/dev/null
fi
echo "DONE viewer+dataflow stay up" >> "$STATE"
wait "$DORA_PID" 2>/dev/null
