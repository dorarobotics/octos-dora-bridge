#!/usr/bin/env bash
# Turnkey UR5e pick-and-place of the red ball, driven over octos HTTP.
# Boots the MuJoCo dataflow + a ball_state side-server, then runs the pick-and-place
# driver (reads live ball pose, picks, places beside it, verifies relocation).
#
# Viewer (watch on the remote desktop):   bash ~/dorarobotics-test/run-arm-pickplace.sh
# Headless tuning:                         HEADLESS=1 GRASP_Z=0.08 bash .../run-arm-pickplace.sh
set -uo pipefail
export DISPLAY="${DISPLAY:-:0}"
export PATH="$HOME/.cargo/bin:$PATH"

PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
BR=$ROOT/octos-dora-bridge
SRC=$ROOT/ur5e-mujoco-live.yml
YML=$ROOT/ur5e-pickplace.yml
URL=http://127.0.0.1:8768
BALL=http://127.0.0.1:8779/ball
MODEL=/home/demo/Public/github_dora_nav_moveit/dora-moveit2/examples/move_group_demo/models/ur5e.xml
CONFIGS=$ROOT/grasp_configs.json
LOG=/tmp/arm-pickplace.log
HEADLESS="${HEADLESS:-0}"

# Precompute the grasp joint waypoints offline (MuJoCo IK -> grasp_configs.json),
# since the dora-moveit2 Cartesian move_to_pose IK is unreliable.
echo "[pickplace] solving grasp IK (offline)…"
MODEL_NAME="$MODEL" IK_OUT="$CONFIGS" "$PY" "$BR/examples/ik_solve_grasp.py" || {
  echo "[pickplace] IK solve failed"; exit 1; }

# Derive the dataflow: set headless flag, append the ball_state side-server node.
if [ "$HEADLESS" = "1" ]; then
  cp "$SRC" "$YML"
else
  sed -e 's|MUJOCO_HEADLESS: "1"|MUJOCO_HEADLESS: "0"\n      DISPLAY: ":0"|' "$SRC" > "$YML"
fi
# Inject the executor interpolation speed (gentler carry = the cradled ball is
# less likely to roll out under base-rotation centrifugal force). Only matches
# inline-flow `env: { ... }` blocks (planner/ik_solver/trajectory_executor); the
# block-style moveit_arm env is untouched. Only trajectory_executor reads it.
sed -i "/env: {.*ROBOT_CONFIG_MODULE/ s| }|, EXEC_INTERP_SPEED: \"${EXEC_INTERP_SPEED:-0.1}\" }|" "$YML"

cat >> "$YML" <<YAML

  - id: ball_state
    path: $PY
    args: $BR/examples/ball_state.py
    env: { BALL_HTTP_HOST: "127.0.0.1", BALL_HTTP_PORT: "8779" }
    inputs:
      joint_positions: mujoco_sim/joint_positions
YAML

cleanup() {
  echo "[pickplace] tearing down…"
  dora stop --grace 3 >/dev/null 2>&1 || true
  dora destroy >/dev/null 2>&1 || true
  pkill -f octos_spec_bridge 2>/dev/null || true
  pkill -f ball_state.py 2>/dev/null || true
  pkill -f dora_mujoco 2>/dev/null || true
}
trap cleanup EXIT

pkill -f octos_spec_bridge 2>/dev/null || true; pkill -f ball_state.py 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true; sleep 2
dora up >/dev/null 2>&1; sleep 2
echo "[pickplace] starting dataflow (log: $LOG)…"
dora start "$YML" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[pickplace] waiting for bridge + ball server…"
for _ in $(seq 1 90); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && break; \
  kill -0 "$DORA_PID" 2>/dev/null || { echo "dataflow exited early:"; tail -30 "$LOG"; exit 1; }; sleep 1; done
for _ in $(seq 1 30); do curl -fsS -m2 "$BALL" >/dev/null 2>&1 && break; sleep 1; done

echo "[pickplace] running joint-space pick-and-place driver…"
ARM_BRIDGE_URL="$URL" BALL_URL="$BALL" GRASP_CONFIGS="$CONFIGS" \
  CLOSE_WIDTH="${CLOSE_WIDTH:-0.0}" \
  PLACE_X="${PLACE_X:-0.30}" PLACE_Y="${PLACE_Y:-0.25}" SETTLE_S="${SETTLE_S:-1.5}" \
  "$PY" "$BR/examples/arm_pick_place_joint_driver.py"

if [ "$HEADLESS" = "1" ]; then
  echo "[pickplace] headless run done."
else
  echo "[pickplace] done. Viewer + dataflow stay up — Ctrl-C to tear down."
  wait "$DORA_PID"
fi
