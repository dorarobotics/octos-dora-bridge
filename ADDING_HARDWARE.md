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
  3. dataflows/<robot>-bridge.yaml                    (portable dora dataflow template)
  4. (optional) an imperative skill pack              (lives WITH the vendor node)
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
3. **`dataflows/<robot>-bridge.yaml`** in this repo — the portable dora dataflow
   template. Keep reusable wiring here, not machine-local paths. If a node needs
   a local checkout, Python wrapper, serial manifest, or tuned runtime value, use
   placeholders or simple relative paths and resolve them in the robot's startup
   script before calling `dora start`.
4. **(Optional) imperative skill pack** — high-level skills like `pick_at(x,y)`
   that compose raw verbs + IK. These are hardware-class-specific and live **with
   the vendor node**, never in this repo. Example: `moveit-arm-dora-node/skill_pack/`
   is one generic arm skill pack driven by a per-robot **manifest**
   (`manifests/<robot>.json`: HOME, grasp heights, gripper widths, object noun…).
   Adding another arm of that class = a new manifest, no skill code change.

## Dataflow templates vs runtime files

Keep these separate:

```
dataflows/<robot>-bridge.yaml      # portable template, committed
.<robot>-run/<robot>-bridge.yml    # resolved local runtime file, generated
```

Dora does not interpolate shell variables in `path:` or `args:` fields. A checked
in dataflow may therefore contain placeholders such as `__DORA_MOVEIT2__`,
`__VENV_PY__`, or `path: ./venv-python`, but the file passed to `dora start`
should already contain absolute paths for the current machine.

The startup script for the robot should:

1. locate this repo and any required external checkout, such as `dora-moveit2`;
2. choose or generate the Python wrapper used by all dora nodes;
3. create the local run directory;
4. create a default hardware manifest if the operator has not provided one;
5. substitute placeholders in `dataflows/<robot>-bridge.yaml`;
6. write the result under the run directory; and
7. call `dora start` on the resolved file.

Do not commit generated run directories. They commonly contain absolute paths,
serial ports, tuned local values, logs, and dora session files.

Example for ADORA:

```
dataflows/adora-hw-bridge.yaml
  -> .adora-hw-run/adora-hw-bridge.yml
```

The ADORA startup script documents and resolves the relevant environment
variables:

| Variable | Purpose |
|----------|---------|
| `ADORA_RUN_DIR` | local output directory for the resolved YAML, manifest, logs, and dora session files |
| `ADORA_DORA_DATAFLOW` | explicit resolved dataflow override |
| `ADORA_ROBOT_ID` | robot id advertised by `moveit_arm` and the HTTP bridge |
| `ADORA_PORT` | serial device written into the generated hardware manifest |
| `ADORA_ROBOT_MANIFEST` | hardware manifest consumed by `rebot_hw_node` |
| `ADORA_VENV_PYTHON` | Python executable or wrapper used by all dora nodes |
| `DORA_MOVEIT2` | local `dora-moveit2` checkout used for planner, IK, and executor node paths |
| `ADORA_EXEC_INTERP_SPEED` | trajectory interpolation speed |
| `ADORA_HTTP_PORT` | HTTP bridge port |

## Reproducible runtime dependencies

Do not treat a local venv such as `/home/dora/so101-sim/venv` as part of the
portable hardware definition. A portable robot integration should document:

1. the PyPI runtime packages needed by that hardware path;
2. the local repositories that must be installed editable or added to
   `PYTHONPATH`; and
3. any vendor SDKs that are not available as normal PyPI packages.

For ADORA hardware, the root `pyproject.toml` exposes an `adora-hw` optional
dependency set. It must be installed into the same Python environment used by
`skills/Adora-RGB-pick/start_bridge.sh`. The remaining robot stack modules come
from local checkouts:

```bash
python -m pip install -e 'octos-dora-bridge[adora-hw]'
python -m pip install --no-deps -e octos-dora-bridge/bridge
python -m pip install --no-deps -e moveit-arm-dora-node
python -m pip install --no-deps -e rebot-hw-dora-node
python -m pip install --no-deps -e dora-moveit2/dora_moveit
python -m pip install --no-deps -e dora-moveit2/examples/move_group_demo
```

Use `--no-deps` for the editable repository installs when the robot runtime
extra pins the validated Dora/PyArrow/LeRobot/Torch versions. This prevents
older package metadata in a sibling repository from silently downgrading or
upgrading the working dora runtime.

If the hardware backend imports a vendor SDK that is not packaged on PyPI, such
as `scservo_sdk`, document its source and ensure the final venv can import it.

## Worked example: reBotArm B601-DM

Added with **zero edits** to `bridge/`, `octos_py`, or `dora_moveit/`:
- dora-moveit2: `config/rebot.py` + `models/rebot_pickplace.xml` (data).
- here: `skills/rebot/SKILL.md` (declarative).
- moveit-arm-dora-node: `skill_pack/manifests/rebot.json` (the only robot-specific
  file for the imperative demo; the skill code is shared with UR5e).

See `moveit-arm-dora-node/skill_pack/README.md` for the arm skill pack.
