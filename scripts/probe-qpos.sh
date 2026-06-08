#!/usr/bin/env bash
# Definitive indexing probe: dump full qpos alongside moveit_arm's reported joints
# across a known move. Tells us the true arm qpos offset and whether moveit reads
# the wrong slice.
set -uo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
URL=http://127.0.0.1:8768
SRC=$ROOT/ur5e-mujoco-live.yml
YML=$ROOT/ur5e-qpos-probe.yml
LOG=/tmp/qpos-probe.log

# Append a qpos_dump node subscribed to mujoco_sim/joint_positions.
cp "$SRC" "$YML"
cat >> "$YML" <<YAML

  - id: qpos_dump
    path: $PY
    args: $ROOT/octos-dora-bridge/examples/qpos_dump.py
    inputs:
      joint_positions: mujoco_sim/joint_positions
      control_input: gripper_merge/control_input
YAML

pkill -f octos_spec_bridge 2>/dev/null || true; pkill -f dora_mujoco 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true; sleep 2
dora up 2>&1 | tail -1; sleep 2
dora start "$YML" --attach > "$LOG" 2>&1 &
for _ in $(seq 1 90); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && break; sleep 1; done

moveit_joints() {
  curl -s -X POST "$URL/tools/get_state" -H 'Content-Type: application/json' -d '{"args":{}}' \
    | "$PY" -c 'import sys,json;d=json.load(sys.stdin);s=d.get("data",{}).get("stream") or {};print("moveit joint_positions:", s.get("joint_positions"))'
}

echo "=== BEFORE: moveit-reported vs full qpos ==="; moveit_joints
grep "QPOS" "$LOG" | tail -1
echo "=== move arm to [-0.5,-1.2,1.0,-1.4,-1.57,0.3] ==="
curl -s -X POST "$URL/tools/vendor.moveit.arm.move_to_joint_state" -H 'Content-Type: application/json' \
  -d '{"args":{"joints":[-0.5,-1.2,1.0,-1.4,-1.57,0.3],"control_source":"probe"}}' >/dev/null; sleep 2
echo "=== AFTER: moveit-reported vs full qpos ==="; moveit_joints
grep "QPOS" "$LOG" | tail -1
echo "=== control_input commanded to sim (last few distinct) ==="
grep "CTRL_IN" "$LOG" | tail -6
echo "=== executor activity ==="
grep -iE "waypoint|complete|trajectory #" "$LOG" | tail -5
echo "(expected: true arm qpos[7:13] ~= the commanded target; CTRL_IN arm ~= target)"

dora stop --grace 3 >/dev/null 2>&1 || true; dora destroy >/dev/null 2>&1 || true
echo "=== probe done ==="
