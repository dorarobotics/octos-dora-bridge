# Adding new hardware (without touching octos or the bridge)

This repo's bridge (`bridge/octos_spec_bridge`) and the octos agent SDK are
**generic and frozen**. The `dora-moveit2` MoveGroup framework is generic too.
Adding a new robot must not edit any of them — it is purely additive.

## The contract

```
FROZEN (never edited per-robot):
  octos_py            — agent SDK
  bridge/             — SPEC-VENDOR-NODE-V1 HTTP bridge (auto-exposes /tools)
  dora-moveit2/dora_moveit/   — MoveGroup framework (config-driven)

PER-ROBOT (added each time, decoupled):
  1. a vendor node implementing SPEC-VENDOR-NODE-V1  (adverts capabilities + verbs)
  2. skills/<robot>/SKILL.md                          (declarative octos skill — THIS repo)
  3. (optional) an imperative skill pack              (lives WITH the vendor node)
```

Verbs are **auto-discovered** from the vendor node's capabilities advert and
exposed at `POST /tools/{verb}`. The octos agent builds its toolset from that
catalog — so a new robot's verbs appear with zero bridge/agent code changes.

## Checklist to add a robot

1. **Vendor node (SPEC-V1).** Reuse an existing one if the class fits. For arms on
   dora-moveit2 this is `moveit_arm_node`, selected per-robot with env only:
   - `ROBOT_CONFIG_MODULE` → a new `config/<robot>.py` (joint limits, HOME, named
     poses, `ARM_QPOS_START`) in the dora-moveit2 examples — *data, not framework code*.
   - a MuJoCo/real model for that robot.
2. **`skills/<robot>/SKILL.md`** in this repo — the declarative octos skill:
   frontmatter (robot_type, safety tier, lifecycle hooks: preflight/init/
   ready_check/shutdown/emergency_shutdown) + verb docs. Copy `skills/ur5e/SKILL.md`
   or `skills/rebot/SKILL.md` and adjust. This is the only file added *here*, and
   it is declarative (no code).
3. **(Optional) imperative skill pack** — high-level skills like `pick_at(x,y)`
   that compose raw verbs + IK. These are hardware-class-specific and live **with
   the vendor node**, never in this repo. Example: `moveit-arm-dora-node/skill_pack/`
   is one generic arm skill pack driven by a per-robot **manifest**
   (`manifests/<robot>.json`: HOME, grasp heights, gripper widths, object noun…).
   Adding another arm of that class = a new manifest, no skill code change.

## Worked example: reBotArm B601-DM

Added with **zero edits** to `bridge/`, `octos_py`, or `dora_moveit/`:
- dora-moveit2: `config/rebot.py` + `models/rebot_pickplace.xml` (data).
- here: `skills/rebot/SKILL.md` (declarative).
- moveit-arm-dora-node: `skill_pack/manifests/rebot.json` (the only robot-specific
  file for the imperative demo; the skill code is shared with UR5e).

See `moveit-arm-dora-node/skill_pack/README.md` for the arm skill pack.
