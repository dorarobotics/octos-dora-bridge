#!/usr/bin/env bash
# Diagnostic: does the UR5e sim's joint state actually change during a move?
# Boots headless, reads joint_positions before/after a move_to_joint_state, and
# dumps planner/executor/control activity from the dataflow log.
set -uo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
URL=http://127.0.0.1:8768
LOG=/tmp/probe-arm.log

pkill -f octos_spec_bridge 2>/dev/null || true
pkill -f dora_mujoco 2>/dev/null || true
echo "=== dora destroy ==="; dora destroy 2>&1 | tail -3 || true
sleep 2
echo "=== dora up ==="; dora up 2>&1 | tail -3
sleep 2
echo "=== dora start ==="; dora start /home/demo/dorarobotics-test/ur5e-mujoco-live.yml --attach > "$LOG" 2>&1 &
sleep 3
echo "=== dora list ==="; dora list 2>&1 | tail -5
echo "=== waiting healthz (90s) ==="
ok=0
for _ in $(seq 1 90); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && { ok=1; break; }; sleep 1; done
if [ "$ok" != 1 ]; then echo "HEALTHZ FAILED — dataflow log head:"; head -40 "$LOG"; fi

joints() {
  curl -s -X POST "$URL/tools/get_state" -H 'Content-Type: application/json' -d '{"args":{}}' \
    | "$PY" -c 'import sys,json; d=json.load(sys.stdin); s=d.get("data",{}).get("stream") or {}; print(s.get("joint_positions"))'
}

echo "=== mujoco model/actuator info ==="
grep -E "DOF \(nq\)|Actuators \(nu\)|Control inputs|^  \[[0-9]\]" "$LOG" | head -12

echo "=== BEFORE move ==="; B=$(joints); echo "$B"
echo "=== move_to_joint_state -> [-0.5,-1.2,1.0,-1.4,-1.57,0.3] ==="
curl -s -X POST "$URL/tools/vendor.moveit.arm.move_to_joint_state" -H 'Content-Type: application/json' \
  -d '{"args":{"joints":[-0.5,-1.2,1.0,-1.4,-1.57,0.3],"control_source":"probe"}}'; echo
sleep 1
echo "=== AFTER move ==="; A=$(joints); echo "$A"

echo "=== changed? ==="
"$PY" - "$B" "$A" <<'PYEOF'
import ast, sys
b = ast.literal_eval(sys.argv[1]) if sys.argv[1] not in ("None","") else None
a = ast.literal_eval(sys.argv[2]) if sys.argv[2] not in ("None","") else None
if not b or not a:
    print("MISSING joint data: before=%r after=%r" % (b, a)); raise SystemExit
md = max(abs(x-y) for x, y in zip(a, b))
print("max |delta| across joints = %.5f rad  ->  %s" % (md, "MOVED" if md > 0.01 else "NO MOTION"))
PYEOF

echo "=== planner / executor / control activity (tail) ==="
grep -iE "execution_status|trajectory|joint_command|control_input|plan_status|waypoint|exec" "$LOG" | tail -25
echo "=== any errors? ==="
grep -iE "error|traceback|exception|fail" "$LOG" | tail -15

dora stop --grace 3 >/dev/null 2>&1 || true
dora destroy >/dev/null 2>&1 || true
echo "=== probe done ==="
