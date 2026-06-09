#!/usr/bin/env bash
# ============================================================================
#  SO-101 pick-and-place demo — ISOLATED-daemon launcher for SHARED / ROBOT boxes.
#
#  Use this instead of run-so101-demo.sh when the machine ALREADY runs a dora daemon
#  you must not disturb (e.g. an FF robot running its own dataflow on the default
#  coordinator :6013). This script:
#    * brings up its OWN dora coordinator+daemon on non-default ports (default 6113/6114),
#    * starts the demo there, then tears down ONLY its own coordinator/daemon by PID.
#  It NEVER runs `dora up`, `dora destroy`, or pkills any daemon, and never touches the
#  default ports — so a co-resident robot dataflow keeps running untouched.
#
#  It also applies the three fixes needed beyond "dora 0.2.1":
#    1. venv-python WRAPPER SCRIPT (not a symlink) — preserves venv detection so nodes
#       import the venv's dora-rs 0.2.1 (not a system/user 0.3.x → message-format clash).
#    2. ZENOH_CONFIG disabling zenoh multicast/gossip scouting + loopback-only — stops the
#       cross-network peer storm that otherwise panics nodes on multi-interface boxes.
#    3. PYTHONPATH = examples/move_group_demo — so the move_group nodes import their config.
#
#  QUICK START:
#      export PYTHON=/path/to/venv/bin/python    # venv with dora-rs==0.2.1 + deps + repos
#      bash examples/run-so101-isolated.sh        # headless by default on a server
#
#  Env knobs (plus the run-so101-demo.sh ones): COORD_PORT (6113), DAEMON_LISTEN_PORT (6114).
#  HEADLESS defaults to 1 here (servers/robots are usually display-less); set HEADLESS=0 for a viewer.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="$(cd "$HERE/.." && pwd)"
export DORA_MOVEIT2="${DORA_MOVEIT2:-$PARENT/dora-moveit2}"
MOVEIT_ARM="${MOVEIT_ARM:-$PARENT/moveit-arm-dora-node}"
export SKILL_PACK="${SKILL_PACK:-$MOVEIT_ARM/skill_pack}"
PYTHON="${PYTHON:-python3}"

MODEL="$DORA_MOVEIT2/examples/move_group_demo/models/so101_pickplace.xml"
MANIFEST="${ROBOT_MANIFEST:-$SKILL_PACK/manifests/so101.json}"
SRC="$HERE/dataflows/so101-mujoco-bridge.yaml"
WORK="${WORK_DIR:-$HERE/.so101-iso}"
YML="$WORK/so101-demo.yml"
URL=http://127.0.0.1:8768
BALL=http://127.0.0.1:8779/ball
NAME="${DATAFLOW_NAME:-so101-iso}"
CP="${COORD_PORT:-6113}"
LP="${DAEMON_LISTEN_PORT:-6114}"
CF="--coordinator-port $CP"
HEADLESS="${HEADLESS:-1}"
AUTO="${AUTO:-1}"
export EXEC_INTERP_SPEED="${EXEC_INTERP_SPEED:-0.5}"
export GRIP_DWELL="${GRIP_DWELL:-3.0}"

die() { echo "[so101-iso] ERROR: $*" >&2; exit 1; }

echo "[so101-iso] preflight…"
command -v dora >/dev/null     || die "dora CLI not on PATH (need the 0.2.1 CLI; see DEPLOYMENT.md)"
command -v "$PYTHON" >/dev/null || die "PYTHON '$PYTHON' not found"
[ -f "$MODEL" ]    || die "model not found: $MODEL  (set DORA_MOVEIT2)"
[ -f "$SRC" ]      || die "dataflow not found: $SRC"
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST (set MOVEIT_ARM)"
"$PYTHON" -c "import mujoco, numpy, pyarrow, dora" 2>/dev/null \
  || die "python deps missing in '$PYTHON' (need mujoco,numpy,pyarrow,dora-rs==0.2.1 + repos)"

mkdir -p "$WORK"

# 1) venv-python wrapper SCRIPT (see header note #1)
cat > "$WORK/venv-python" <<EOF
#!/bin/bash
exec "$("$PYTHON" -c 'import sys;print(sys.executable)')" "\$@"
EOF
chmod +x "$WORK/venv-python"

# 2) zenoh: disable scouting, pin to loopback (see header note #2). Override via $ZENOH_CONFIG.
if [ -z "${ZENOH_CONFIG:-}" ]; then
  cat > "$WORK/zenoh.json5" <<'Z'
{
  mode: "peer",
  scouting: { multicast: { enabled: false }, gossip: { enabled: false } },
  listen:  { endpoints: ["tcp/127.0.0.1:0"] },
  connect: { endpoints: [] },
}
Z
  export ZENOH_CONFIG="$WORK/zenoh.json5"
fi
export DORA_ZENOH_CONNECT=""

# 3) PYTHONPATH for move_group_demo (see header note #3)
export PYTHONPATH="$DORA_MOVEIT2/examples/move_group_demo${PYTHONPATH:+:$PYTHONPATH}"

# --- build the runnable yml (headless toggle, speed, ball_state sensing node) ---------
sed -e "s|\${DORA_MOVEIT2}|$DORA_MOVEIT2|g" \
    -e "s|\${SKILL_PACK}|$SKILL_PACK|g" \
    -e "s|path: ./venv-python|path: $WORK/venv-python|g" \
    "$SRC" > "$YML"
if [ "$HEADLESS" != "1" ]; then
  sed -i.bak -e 's|MUJOCO_HEADLESS: "1"|MUJOCO_HEADLESS: "0"|' "$YML" && rm -f "$YML.bak"
fi
sed -i.bak "/env: {.*ROBOT_CONFIG_MODULE/ s| }|, EXEC_INTERP_SPEED: \"${EXEC_INTERP_SPEED}\" }|" "$YML" && rm -f "$YML.bak"
sed -i.bak "/id: trajectory_executor/,/outputs:/ s|tick: dora/timer/millis/[0-9]*|tick: dora/timer/millis/${EXEC_TICK_MS:-20}|" "$YML" && rm -f "$YML.bak"
grep -q "id: ball_state" "$YML" || cat >> "$YML" <<YAML

  - id: ball_state
    path: $WORK/venv-python
    args: $SKILL_PACK/sim/ball_state.py
    env: { BALL_HTTP_HOST: "127.0.0.1", BALL_HTTP_PORT: "8779" }
    inputs:
      joint_positions: mujoco_sim/joint_positions
YAML

# --- isolated coordinator+daemon; teardown kills ONLY our own PIDs --------------------
COORD_PID=""; DAEMON_PID=""
cleanup() {
  echo "[so101-iso] tearing down (only my coordinator/daemon + dataflow)…"
  dora stop "$NAME" $CF --grace-duration 4s >/dev/null 2>&1 || true
  sleep 2
  [ -n "$DAEMON_PID" ] && kill "$DAEMON_PID" 2>/dev/null; [ -n "$COORD_PID" ] && kill "$COORD_PID" 2>/dev/null
  sleep 1
  [ -n "$DAEMON_PID" ] && kill -9 "$DAEMON_PID" 2>/dev/null; [ -n "$COORD_PID" ] && kill -9 "$COORD_PID" 2>/dev/null
}
trap cleanup EXIT

echo "[so101-iso] starting my coordinator :$CP + daemon (listen :$LP)…"
dora coordinator --port "$CP" > "$WORK/coord.log" 2>&1 & COORD_PID=$!
sleep 3
dora daemon --coordinator-addr 127.0.0.1 --coordinator-port "$CP" --local-listen-port "$LP" > "$WORK/daemon.log" 2>&1 & DAEMON_PID=$!
sleep 4

echo "[so101-iso] starting dataflow '$NAME'…"
dora start "$YML" --name "$NAME" --detach $CF > "$WORK/start.log" 2>&1 || { echo "start failed:"; cat "$WORK/start.log"; exit 1; }

echo "[so101-iso] waiting for bridge :8768 …"
ok=no
for _ in $(seq 1 150); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && { ok=yes; break; }; sleep 2; done
if [ "$ok" != yes ]; then
  echo "[so101-iso] bridge never came up. node logs:"
  for n in mujoco_sim planning_scene move_group_planner trajectory_executor gripper_merge octos_spec_bridge ball_state; do
    echo "  --- $n ---"; dora logs "$NAME" "$n" $CF 2>&1 | tail -10
  done
  exit 1
fi
for _ in $(seq 1 30); do curl -fsS -m2 "$BALL" >/dev/null 2>&1 && break; sleep 1; done
echo "[so101-iso] bridge UP. cube: $(curl -fsS -m2 "$BALL" 2>/dev/null)"

if [ "$AUTO" != "1" ] && [ "$HEADLESS" != "1" ]; then
  read -r -p "[so101-iso] Put the viewer in view, then press ENTER to start the pick… " _
fi
echo "[so101-iso] >>> pick-and-place (cube -> green plate)…"
ARM_BRIDGE_URL="$URL" BALL_URL="$BALL" MODEL_NAME="$MODEL" ROBOT_MANIFEST="$MANIFEST" \
  "$PYTHON" "$SKILL_PACK/skill_pickplace.py"; RC=$?
echo "[so101-iso] pick exit=$RC ; cube now: $(curl -fsS -m2 "$BALL" 2>/dev/null)"
if [ "$HEADLESS" != "1" ]; then
  echo "[so101-iso] done. viewer stays up until Ctrl-C."
  wait "$DAEMON_PID"
fi
exit $RC
