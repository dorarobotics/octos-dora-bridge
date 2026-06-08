#!/usr/bin/env bash
# Verify move_to_pose actually places the gripper TCP at the commanded Cartesian
# target. Boots with a tcp_probe node (FK -> pinch site world xyz) and commands a
# few top-down poses, reporting commanded vs actual TCP.
set -uo pipefail
export PATH="$HOME/.cargo/bin:$PATH"
PY=/home/demo/anaconda3/envs/dora-moveit/bin/python
ROOT=/home/demo/dorarobotics-test
BR=$ROOT/octos-dora-bridge
URL=http://127.0.0.1:8768
MODEL=/home/demo/Public/github_dora_nav_moveit/dora-moveit2/examples/move_group_demo/models/ur5e.xml
SRC=$ROOT/ur5e-mujoco-live.yml
YML=$ROOT/ur5e-tcp-probe.yml
LOG=/tmp/tcp-probe.log

cp "$SRC" "$YML"
cat >> "$YML" <<YAML

  - id: tcp_probe
    path: $PY
    args: $BR/examples/tcp_probe.py
    env: { MODEL_NAME: "$MODEL" }
    inputs:
      joint_positions: mujoco_sim/joint_positions
YAML

pkill -f octos_spec_bridge 2>/dev/null || true; pkill -f tcp_probe 2>/dev/null || true
dora destroy >/dev/null 2>&1 || true; sleep 2
dora up >/dev/null 2>&1; sleep 2
dora start "$YML" --attach > "$LOG" 2>&1 &
for _ in $(seq 1 90); do curl -fsS -m2 "$URL/healthz" >/dev/null 2>&1 && break; sleep 1; done

move_pose() { # x y z
  curl -s -X POST "$URL/tools/vendor.moveit.arm.move_to_pose" -H 'Content-Type: application/json' \
    -d "{\"args\":{\"pose\":{\"position\":[$1,$2,$3],\"orientation\":[1.0,0.0,0.0,0.0]},\"control_source\":\"tcp\"}}"
}

for tgt in "0.35 -0.15 0.25" "0.35 -0.15 0.10" "0.30 0.25 0.25" "0.40 0.0 0.30"; do
  read -r x y z <<< "$tgt"
  echo "=== commanded TCP target: ($x, $y, $z) top-down ==="
  r=$(move_pose "$x" "$y" "$z"); echo "  resp: $r"
  sleep 2
  echo "  actual: $(grep 'TCP' "$LOG" | tail -1)"
done

dora stop --grace 3 >/dev/null 2>&1 || true; dora destroy >/dev/null 2>&1 || true
echo "=== tcp probe done ==="
