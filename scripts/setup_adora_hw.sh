#!/usr/bin/env bash
# ============================================================================
#  One-shot Python environment setup for ADORA hardware.
#
#  Run from inside an octos-dora-bridge checkout:
#      bash scripts/setup_adora_hw.sh
#
#  It creates one venv, installs the ADORA hardware runtime extra from this
#  repo's pyproject.toml, and installs the local robot stack repos editable with
#  --no-deps so their older package metadata cannot replace the validated dora
#  runtime pins.
#
#  Env overrides:
#      VENV=/path/to/venv
#      DORA_MOVEIT2=/path/to/dora-moveit2
#      MOVEIT_ARM=/path/to/moveit-arm-dora-node
#      REBOT_HW=/path/to/rebot-hw-dora-node
#      INSTALL_SCSERVO_FROM=/path/to/scservo_sdk-parent-or-package
# ============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT="$(cd "$HERE/.." && pwd)"

VENV="${VENV:-$PARENT/adora-venv}"
DORA_MOVEIT2="${DORA_MOVEIT2:-$PARENT/dora-moveit2}"
MOVEIT_ARM="${MOVEIT_ARM:-$PARENT/moveit-arm-dora-node}"
REBOT_HW="${REBOT_HW:-$PARENT/rebot-hw-dora-node}"

say() { echo "[setup-adora-hw] $*"; }
die() { echo "[setup-adora-hw] ERROR: $*" >&2; exit 1; }

need_dir() {
  local label="$1" path="$2"
  [ -d "$path" ] || die "$label not found: $path"
}

need_dir "dora-moveit2 checkout" "$DORA_MOVEIT2"
need_dir "moveit-arm-dora-node checkout" "$MOVEIT_ARM"
need_dir "rebot-hw-dora-node checkout" "$REBOT_HW"

if [ ! -d "$VENV" ]; then
  say "creating venv at $VENV"
  python3 -m venv "$VENV"
fi

PY="$VENV/bin/python"
[ -x "$PY" ] || die "venv python not executable: $PY"

say "installing ADORA hardware runtime extra"
"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install -e "$HERE[adora-hw]"

say "installing local robot stack checkouts with --no-deps"
"$PY" -m pip install --no-deps -e "$HERE/bridge"
"$PY" -m pip install --no-deps -e "$MOVEIT_ARM"
"$PY" -m pip install --no-deps -e "$REBOT_HW"
"$PY" -m pip install --no-deps -e "$DORA_MOVEIT2/dora_moveit"
"$PY" -m pip install --no-deps -e "$DORA_MOVEIT2/examples/move_group_demo"

if ! "$PY" -c 'import scservo_sdk' >/dev/null 2>&1; then
  if [ -n "${INSTALL_SCSERVO_FROM:-}" ]; then
    say "installing scservo_sdk from $INSTALL_SCSERVO_FROM"
    SITE_PACKAGES="$("$PY" - <<'PY'
import sysconfig
print(sysconfig.get_paths()["purelib"])
PY
)"
    if [ -d "$INSTALL_SCSERVO_FROM/scservo_sdk" ]; then
      cp -a "$INSTALL_SCSERVO_FROM/scservo_sdk" "$SITE_PACKAGES/"
    elif [ -d "$INSTALL_SCSERVO_FROM" ] && [ -f "$INSTALL_SCSERVO_FROM/__init__.py" ]; then
      mkdir -p "$SITE_PACKAGES/scservo_sdk"
      cp -a "$INSTALL_SCSERVO_FROM"/. "$SITE_PACKAGES/scservo_sdk/"
    else
      die "INSTALL_SCSERVO_FROM must point to scservo_sdk or its parent directory"
    fi
  else
    say "WARNING: scservo_sdk is still missing."
    say "Set INSTALL_SCSERVO_FROM=/path/to/scservo_sdk-parent-or-package and rerun, or install the vendor SDK manually."
  fi
fi

say "checking imports"
if ! "$PY" - <<'PY'
import dora, draccus, lerobot, torch, uvicorn
import octos_spec_bridge, moveit_arm_node, rebot_hw_node, dora_moveit
import scservo_sdk
print("adora hw venv ok")
PY
then
  die "import check failed; fix the missing package above and rerun"
fi

cat <<DONE

[setup-adora-hw] done.

Use this environment for the ADORA bridge:

    ADORA_VENV_PYTHON=$PY \\
    DORA_MOVEIT2=$DORA_MOVEIT2 \\
    bash $HERE/skills/Adora-RGB-pick/start_bridge.sh

DONE
