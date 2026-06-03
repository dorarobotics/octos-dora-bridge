#!/usr/bin/env bash
# Manual smoke test against the AgiBot A2 MuJoCo sim at 192.168.100.100.
#
# Prereqs:
#   - dora CLI on PATH
#   - this venv has octos-spec-bridge + agibot-a2-dora-node installed
#   - A2 sim is running at 192.168.100.100:56322 (verify with the curl in step 1)
#
# Not in CI — run locally before tagging a release.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRIDGE_URL="http://127.0.0.1:8765"

echo "[1/5] Sim reachable?"
curl -fsS -o /dev/null -m 3 -X POST \
  http://192.168.100.100:56322/rpc/aimdk.protocol.McBaseService/GetState \
  -H "Content-Type: application/json" -d '{}'
echo "      OK"

echo "[2/5] Starting dora dataflow…"
cd "$REPO_ROOT"
dora up >/dev/null
dora start dataflows/a2-bridge.yaml >/tmp/dora-start.log 2>&1 &
DORA_PID=$!
trap "kill $DORA_PID 2>/dev/null || true; dora stop --grace 5 >/dev/null 2>&1 || true" EXIT

echo "[3/5] Waiting for bridge /healthz…"
for _ in $(seq 1 30); do
  if curl -fsS -m 2 "$BRIDGE_URL/healthz" >/dev/null 2>&1; then
    echo "      OK"
    break
  fi
  sleep 1
done
curl -fsS "$BRIDGE_URL/healthz" >/dev/null

echo "[4/5] robot.heartbeat round-trip…"
HB=$(curl -fsS -X POST "$BRIDGE_URL/tools/robot.heartbeat" \
  -H "Content-Type: application/json" -d '{"args":{}}')
echo "      response: $HB"
echo "$HB" | python -c "import sys, json; r=json.load(sys.stdin); assert r['ok'] and r['code']=='0', r"

echo "[5/5] vendor.agibot.a2.motion.set_action(RL_LOCOMOTION_DEFAULT)…"
SA=$(curl -fsS -X POST "$BRIDGE_URL/tools/vendor.agibot.a2.motion.set_action" \
  -H "Content-Type: application/json" \
  -d '{"args":{"action":"RL_LOCOMOTION_DEFAULT"}}')
echo "      response: $SA"
echo "$SA" | python -c "import sys, json; r=json.load(sys.stdin); assert r['ok'] and r['data'].get('applied'), r"

echo
echo "ALL SMOKE CHECKS PASSED"
