#!/usr/bin/env bash
set -euo pipefail

export NO_PROXY="${NO_PROXY:-127.0.0.1,localhost}"
export no_proxy="${no_proxy:-127.0.0.1,localhost}"

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

find_bridge_repo() {
  local candidates=(
    "${OCTOS_DORA_BRIDGE:-}"
    "$SKILL_DIR/../.."
    "$SKILL_DIR/../skills/octos-dora-bridge"
    "$HOME/.octos/skills/skills/octos-dora-bridge"
    "$HOME/octos-dora-bridge"
  )
  local d
  for d in "${candidates[@]}"; do
    [ -n "$d" ] || continue
    if [ -d "$d/dataflows" ] && [ -d "$d/bridge" ]; then
      cd "$d" && pwd
      return 0
    fi
  done
  return 1
}

BRIDGE_REPO="$(find_bridge_repo || true)"
if [ -n "$BRIDGE_REPO" ]; then
  RUN_DIR="${ADORA_RUN_DIR:-${SO101_BRIDGE_RUN_DIR:-$BRIDGE_REPO/.adora-hw-run}}"
else
  RUN_DIR="${ADORA_RUN_DIR:-${SO101_BRIDGE_RUN_DIR:-$SKILL_DIR/.run}}"
fi
CONTROL_PORT="${ADORA_DORA_CONTROL_PORT:-${SO101_DORA_CONTROL_PORT:-6112}}"
BRIDGE_HTTP_PORT="${ADORA_HTTP_PORT:-8768}"

if [ -f "$RUN_DIR/dataflow.uuid" ]; then
  UUID="$(cat "$RUN_DIR/dataflow.uuid")"
  dora stop "$UUID" --coordinator-port "$CONTROL_PORT" --grace-duration 4s >/dev/null 2>&1 || true
  rm -f "$RUN_DIR/dataflow.uuid"
fi

if [ -f "$RUN_DIR/node.pids" ]; then
  while read -r PID; do
    [ -n "$PID" ] || continue
    kill "$PID" >/dev/null 2>&1 || true
  done < "$RUN_DIR/node.pids"
  sleep 2
  while read -r PID; do
    [ -n "$PID" ] || continue
    kill -9 "$PID" >/dev/null 2>&1 || true
  done < "$RUN_DIR/node.pids"
  rm -f "$RUN_DIR/node.pids"
fi

for f in "$RUN_DIR/daemon.pid" "$RUN_DIR/coordinator.pid"; do
  [ -f "$f" ] || continue
  PID="$(cat "$f")"
  if [ -n "$PID" ]; then
    kill "$PID" >/dev/null 2>&1 || true
    sleep 1
    kill -9 "$PID" >/dev/null 2>&1 || true
  fi
  rm -f "$f"
done

if command -v fuser >/dev/null 2>&1; then
  fuser -k "$BRIDGE_HTTP_PORT/tcp" >/dev/null 2>&1 || true
fi

echo "ADORA bridge stopped"
