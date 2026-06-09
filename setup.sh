#!/usr/bin/env bash
# ============================================================================
#  One-shot setup for the SO-101 pick-and-place demo.
#
#  Run from inside an octos-dora-bridge checkout:
#      bash setup.sh
#
#  It clones the other two repos AS SIBLINGS, creates a venv, and installs the
#  Python deps so `examples/run-so101-demo.sh` just works. Idempotent — re-running
#  skips anything already present. See RUNNING_SO101.md for the full walkthrough.
#
#  Env overrides:
#      BRANCH=feat/so101   branch to check out in all three repos
#      VENV=<parent>/venv  venv location
#      WITH_AGENT=1        also set up the optional LLM-agent variant (octos_py)
# ============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # octos-dora-bridge
PARENT="$(cd "$HERE/.." && pwd)"
BRANCH="${BRANCH:-feat/so101}"
VENV="${VENV:-$PARENT/venv}"
WITH_AGENT="${WITH_AGENT:-0}"

say() { echo "[setup] $*"; }

clone() {  # clone <url> <dir>
  local url="$1" dir="$2"
  if [ -d "$PARENT/$dir/.git" ]; then
    say "$dir already present — skipping clone"
  else
    say "cloning $dir…"
    git -C "$PARENT" clone "$url" "$dir"
  fi
  git -C "$PARENT/$dir" checkout "$BRANCH" 2>/dev/null \
    || say "  (branch '$BRANCH' not found in $dir — staying on default)"
}

say "parent dir: $PARENT"
clone https://github.com/bobdingAI/dora-moveit2.git           dora-moveit2
clone https://github.com/dorarobotics/moveit-arm-dora-node.git moveit-arm-dora-node
# octos-dora-bridge is the repo we're already in.

# --- python venv + deps ------------------------------------------------------
if [ ! -d "$VENV" ]; then
  say "creating venv at $VENV…"
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
PY="$VENV/bin/python"

say "installing python deps (dora-rs runtime + mujoco + the repos)…"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q "dora-rs==0.3.*" mujoco numpy pyarrow
# Editable installs — layouts vary slightly; install what exists, warn otherwise.
for pkg in "$PARENT/dora-moveit2/dora_moveit" "$PARENT/dora-moveit2/dora-mujoco" \
           "$PARENT/moveit-arm-dora-node" "$HERE"; do
  if [ -f "$pkg/pyproject.toml" ] || [ -f "$pkg/setup.py" ]; then
    "$PY" -m pip install -q -e "$pkg" || say "  WARN: editable install failed for $pkg"
  else
    say "  note: no pyproject/setup in $pkg — relying on PYTHONPATH at runtime"
  fi
done

# --- optional: LLM-agent variant (octos_py is VENDORED; just needs openai + Ollama) --
if [ "$WITH_AGENT" = "1" ]; then
  say "setting up the optional LLM-agent variant…"
  # octos_py is vendored in moveit-arm-dora-node/skill_pack/octos_py — no clone needed.
  "$PY" -m pip install -q openai
  command -v ollama >/dev/null \
    && say "  ollama found — make sure 'ollama pull qwen3:8b' has been run" \
    || say "  NOTE: install Ollama (https://ollama.com) and run 'ollama pull qwen3:8b'"
fi

# --- dora CLI check (can't portably auto-install) ----------------------------
if ! command -v dora >/dev/null; then
  say "WARNING: the 'dora' CLI is not on PATH. Install it (must match dora-rs 0.3.x):"
  say "    cargo install dora-cli --locked    # or grab a release from https://github.com/dora-rs/dora/releases"
fi

cat <<DONE

[setup] done. To run the demo:

    cd $HERE
    export PYTHON=$PY
    bash examples/run-so101-demo.sh
$( [ "$WITH_AGENT" = "1" ] && echo "
  LLM-agent variant (octos_py is vendored; needs Ollama + qwen3:8b running):
    see RUNNING_SO101.md > 'drive it from a sentence'" )
DONE
