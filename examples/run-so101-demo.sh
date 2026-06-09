#!/usr/bin/env bash
# ============================================================================
#  SO-101 pick-and-place demo — PORTABLE launcher (no machine-specific paths).
#
#  Brings up the MuJoCo viewer + dora dataflow, waits for you to press ENTER,
#  then runs the pick: the SO-101 reaches out to the red cube, grasps + lifts it
#  (sim grasp weld), and places it onto the green plate.
#
#  Assumes the three repos are cloned side by side (override with env if not):
#      <parent>/dora-moveit2          (sim + MoveGroup framework + SO-101 model)
#      <parent>/moveit-arm-dora-node  (arm SPEC node + skill_pack)
#      <parent>/octos-dora-bridge     (this repo: bridge + dataflow)  <- run from here
#
#  QUICK START (see RUNNING_SO101.md for full setup):
#      export PYTHON=/path/to/venv/bin/python   # a venv with all deps installed
#      bash examples/run-so101-demo.sh
#
#  Env knobs:
#      PYTHON              python interpreter with deps (default: python3)
#      DORA_MOVEIT2        path to dora-moveit2 checkout (default: ../dora-moveit2)
#      MOVEIT_ARM          path to moveit-arm-dora-node checkout (default: ../moveit-arm-dora-node)
#      EXEC_INTERP_SPEED   motion speed, higher=faster (default 0.5; 1.0 ~= 4x)
#      GRIP_DWELL          pause (s) at the grasp so the close is visible (default 3.0)
#      HEADLESS=1          no viewer (CI/tuning)
#      AUTO=1              skip the ENTER prompt; pick immediately
#  Tear down: Ctrl-C.
# ============================================================================
set -uo pipefail

# --- resolve repo locations -------------------------------------------------
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"          # octos-dora-bridge root
PARENT="$(cd "$HERE/.." && pwd)"
export DORA_MOVEIT2="${DORA_MOVEIT2:-$PARENT/dora-moveit2}"
MOVEIT_ARM="${MOVEIT_ARM:-$PARENT/moveit-arm-dora-node}"
export SKILL_PACK="${SKILL_PACK:-$MOVEIT_ARM/skill_pack}"
PYTHON="${PYTHON:-python3}"

MODEL="$DORA_MOVEIT2/examples/move_group_demo/models/so101_pickplace.xml"
MANIFEST="${ROBOT_MANIFEST:-$SKILL_PACK/manifests/so101.json}"
SRC="$HERE/dataflows/so101-mujoco-bridge.yaml"
WORK="${WORK_DIR:-$HERE/.so101-run}"
YML="$WORK/so101-demo.yml"
URL=http://127.0.0.1:8768
BALL=http://127.0.0.1:8779/ball
LOG="$WORK/dataflow.log"
HEADLESS="${HEADLESS:-0}"
export EXEC_INTERP_SPEED="${EXEC_INTERP_SPEED:-0.5}"
export GRIP_DWELL="${GRIP_DWELL:-3.0}"
AUTO="${AUTO:-0}"

die() { echo "[so101-demo] ERROR: $*" >&2; exit 1; }

echo "[so101-demo] preflight…"
command -v dora >/dev/null   || die "dora CLI not on PATH (install dora-rs; see RUNNING_SO101.md)"
command -v "$PYTHON" >/dev/null || die "PYTHON '$PYTHON' not found"
[ -f "$MODEL" ]    || die "model not found: $MODEL  (set DORA_MOVEIT2)"
[ -f "$SRC" ]      || die "dataflow not found: $SRC"
[ -f "$MANIFEST" ] || die "manifest not found: $MANIFEST  (set MOVEIT_ARM)"
"$PYTHON" -c "import mujoco, numpy, pyarrow" 2>/dev/null \
  || die "python deps missing in '$PYTHON' (need mujoco, numpy, pyarrow + the 3 repos installed; see RUNNING_SO101.md)"

mkdir -p "$WORK"
# dora runs each node via the interpreter at './venv-python' relative to the dataflow's
# working dir. This MUST be a wrapper *script*, not a symlink: dora resolves symlinks
# before exec, so a symlink to a venv's python lands on the resolved base interpreter
# (e.g. /usr/bin/python3) and Python loses venv detection (no pyvenv.cfg next to the
# resolved path) — it then imports the *system/user* dora (e.g. ~/.local 0.3.x), whose
# message format mismatches the 0.2.1 CLI ("message format v0.6.0 ... expected v0.2.1").
# Exec-ing $PYTHON by its (unresolved) path from a script keeps venv site-packages.
cat > "$WORK/venv-python" <<EOF
#!/bin/bash
exec "$("$PYTHON" -c 'import sys;print(sys.executable)')" "\$@"
EOF
chmod +x "$WORK/venv-python"

# --- tame dora's embedded zenoh -----------------------------------------------
# dora uses zenoh only for cross-MACHINE data routing; node<->daemon comm is TCP, so a
# single-machine dataflow needs no peer discovery. On a box with many interfaces (e.g.
# tailscale/docker), zenoh's multicast+gossip scouting discovers unrelated peers and can
# panic (PoisonError) — taking trajectory_executor/gripper_merge down. Disable scouting
# and pin zenoh to loopback. dora reads this via $ZENOH_CONFIG. Override by pre-setting it.
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

# The move_group_demo nodes import `move_group_demo.config.<robot>`; that package lives
# under examples/ and isn't pip-installed, so put its parent on PYTHONPATH (inherited by
# nodes the daemon spawns).
export PYTHONPATH="$DORA_MOVEIT2/examples/move_group_demo${PYTHONPATH:+:$PYTHONPATH}"

# --- hard teardown (daemon-level): a leftover dora daemon respawns the bridge on
#     :8768, so a relaunch's bridge can't bind. Kill the daemon + free the ports.
#     Never kill ourselves (the pattern matches this script's own name). ---------
hard_teardown() {
  for _pid in $(pgrep -f "run-so101-demo|so101-demo" 2>/dev/null); do
    [ "$_pid" = "$$" ] && continue
    [ "$_pid" = "$PPID" ] && continue
    kill -9 "$_pid" 2>/dev/null
  done
  dora stop --grace 2 >/dev/null 2>&1
  dora destroy   >/dev/null 2>&1
  sleep 2
  # The dora coordinator/daemon processes are literally "dora coordinator"/"dora
  # daemon" (a SPACE, not a hyphen). Matching the hyphenated form kills nothing, so
  # daemons accumulate across runs and multiple daemons each spawn the dataflow ->
  # double-builds, :8768/:8779 port collisions, and a viewer restart-loop. Kill the
  # real names so exactly one daemon ever runs.
  pkill -9 -f "dora daemon" 2>/dev/null
  pkill -9 -f "dora coordinator" 2>/dev/null
  pkill -9 -f "dora_mujoco|moveit_arm_node|ball_state|trajectory_execution|planning_scene|move_group_demo|octos_spec_bridge|skill_pickplace" 2>/dev/null
  if command -v fuser >/dev/null; then
    for _ in 1 2 3 4 5 6; do fuser -k 8768/tcp 8779/tcp >/dev/null 2>&1; sleep 1; done
  fi
  sleep 1
}
cleanup() { echo; echo "[so101-demo] tearing down…"; hard_teardown; }
trap cleanup EXIT

echo "[so101-demo] clearing any previous run (daemon + ports)…"
hard_teardown

# --- build the runnable dataflow: substitute repo paths, set viewer + speed,
#     append the ball_state sensing node the deterministic skill reads. ---------
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

echo "[so101-demo] starting dora daemon…"
dora up >/dev/null 2>&1 || true
# POLL only — re-running `dora up` here spawns a second daemon, and two daemons
# co-spawn the dataflow (two windows). One up, then just wait for the coordinator.
for _ in $(seq 1 20); do dora list >/dev/null 2>&1 && break; sleep 1; done
dora list >/dev/null 2>&1 || die "dora coordinator never came up (try: dora destroy && dora up)"

echo "[so101-demo] launching viewer + dataflow (log: $LOG)…"
dora start "$YML" --attach > "$LOG" 2>&1 &
DORA_PID=$!

echo "[so101-demo] waiting for bridge + object server…"
for _ in $(seq 1 150); do
  curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && break
  kill -0 "$DORA_PID" 2>/dev/null || { echo "[so101-demo] dataflow exited early:"; tail -25 "$LOG"; exit 1; }
  sleep 2
done
curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 || die "bridge /healthz never came up — see $LOG"
grep -qi "address already in use" "$LOG" && die "bridge couldn't bind :8768 — see $LOG"
for _ in $(seq 1 30); do curl -fsS -m2 "$BALL" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS -m2 "$BALL" >/dev/null 2>&1 || die "object-state server never came up — see $LOG"

echo
echo "[so101-demo] viewer is UP. cube at: $(curl -fsS -m2 "$BALL" 2>/dev/null)"
if [ "$AUTO" != "1" ]; then
  read -r -p "[so101-demo] Put the MuJoCo window in view, then press ENTER to start the pick… " _
fi
echo "[so101-demo] >>> running pick-and-place (cube -> green plate)…"
ARM_BRIDGE_URL="$URL" BALL_URL="$BALL" MODEL_NAME="$MODEL" ROBOT_MANIFEST="$MANIFEST" \
  "$PYTHON" "$SKILL_PACK/skill_pickplace.py"

if [ "$HEADLESS" = "1" ]; then
  echo "[so101-demo] headless run done."
else
  echo "[so101-demo] done — cube is on the plate. Viewer stays up; re-run to repeat. Ctrl-C to quit."
  wait "$DORA_PID"
fi
