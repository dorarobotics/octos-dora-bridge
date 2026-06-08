#!/usr/bin/env bash
# Deterministic reBotArm pick-and-place (octos skill layer, NO LLM) — for first
# bring-up and geometry tuning. Thin wrapper over run-rebot-agent.sh with
# DRIVER=skill, so the dataflow bring-up / reset / viewer logic is shared.
#
#   bash ~/dorarobotics-test/run-rebot-pickplace.sh
#   HEADLESS=1 bash ~/dorarobotics-test/run-rebot-pickplace.sh   # no viewer
#
# Tune grasp geometry via env, e.g.:
#   GRASP_Z=0.025 APPROACH_Z=0.16 ARM_HOME="0,-0.9,-1.4,0,0,0" \
#     bash ~/dorarobotics-test/run-rebot-pickplace.sh
exec env DRIVER=skill bash "$(dirname "$0")/run-rebot-agent.sh" "$@"
