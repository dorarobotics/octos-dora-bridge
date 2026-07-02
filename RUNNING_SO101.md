# Running the SO-101 pick-and-place demo

A LeRobot **SO-101** (5-DOF arm) picks a red cube and places it on a green plate,
simulated in MuJoCo and driven through the SPEC-V1 HTTP bridge. End to end it
exercises the whole stack: a deterministic skill → the bridge → the arm SPEC node
→ the MoveGroup planner/IK/executor → the MuJoCo sim.

![pick and place: SO-101 fetches the cube and places it on the green plate]
<!-- add a gif/screenshot here if you like -->

---

## What you need

The demo spans **three repositories** — clone them side by side:

```
<parent>/
├── dora-moveit2          # MuJoCo sim + MoveGroup framework + SO-101 model/config
├── moveit-arm-dora-node  # arm SPEC node (moveit_arm_node) + skill_pack
└── octos-dora-bridge     # SPEC HTTP bridge + dataflow wiring  (this repo)
```

```bash
git clone https://github.com/dorarobotics/octos-dora-bridge.git
git clone https://github.com/bobdingAI/dora-moveit2.git
git clone https://github.com/dorarobotics/moveit-arm-dora-node.git
# (the SO-101 work currently lives on the `feat/so101` branch of each)
for r in octos-dora-bridge dora-moveit2 moveit-arm-dora-node; do
  git -C "$r" checkout feat/so101 2>/dev/null || true
done
```

> The hardware backends repo (`rebot-hw-dora-node`) is **not** needed — this is a
> pure simulation; the dataflow uses the MuJoCo sim node, not a hardware backend.

### Prerequisites

- **dora-rs 0.3.x** — the `dora` CLI on your `PATH` *and* the matching `dora-rs`
  Python package in your venv (CLI and Python versions must match).
- **Python 3.10+** with `mujoco`, `numpy`, `pyarrow`.
- A desktop/display for the MuJoCo viewer (or run `HEADLESS=1`).

---

## Setup (one time)

**Quick path — one command.** From inside an `octos-dora-bridge` checkout:

```bash
bash scripts/setup.sh          # clones the other two repos as siblings, makes a venv, installs deps
# WITH_AGENT=1 bash scripts/setup.sh   # also sets up the optional LLM-agent variant (see below)
```

`scripts/setup.sh` is idempotent (re-running skips what's already there) and prints the exact
run command at the end. It can't install the `dora` CLI for you — see the note below.

**Manual path**, if you prefer to do it yourself:

```bash
cd <parent>
python3 -m venv venv && source venv/bin/activate

# dora-rs python runtime + core deps
pip install "dora-rs==0.3.*" mujoco numpy pyarrow

# install the three packages (editable) so their nodes/modules import
pip install -e dora-moveit2/dora_moveit
pip install -e dora-moveit2/dora-mujoco
pip install -e moveit-arm-dora-node
pip install -e octos-dora-bridge

# install the dora CLI (if not already present) — see https://dora-rs.ai
#   cargo install dora-cli --locked       # or download a release binary
```

> Exact package layout may differ slightly per repo — the rule is simply that the
> venv's `python` must be able to `import dora_moveit, dora_mujoco, moveit_arm_node,
> octos_spec_bridge` and run `mujoco`. The launcher checks this and tells you what's
> missing.

---

## Run it

```bash
cd <parent>/octos-dora-bridge
export PYTHON=<parent>/venv/bin/python
bash examples/run-so101-demo.sh
```

The launcher:

1. Cleans up any previous run (tears down the dora daemon and frees the bridge ports).
2. Opens the **MuJoCo viewer** with the arm at home and the cube at its start spot.
3. **Waits for you to press ENTER** — so you don't miss the motion.
4. Runs the pick: reach out → grasp + lift (a short pause at the grasp makes it
   clear) → carry → place on the green plate.
5. Leaves the viewer up. Press **Ctrl-C** to tear down; re-run to repeat.

You should see, and the terminal will confirm:

```
object: x=0.220, y=0.000   plate: x=0.120, y=0.000
OK: grasped and lifted the object from (0.220, 0.000); now holding it.
OK: placed the object at (0.120, 0.000) — ~1 cm from target.
```

### Options

| Env var | Default | Effect |
|---|---|---|
| `PYTHON` | `python3` | interpreter (point at your venv) |
| `DORA_MOVEIT2` | `../dora-moveit2` | path to the dora-moveit2 checkout |
| `MOVEIT_ARM` | `../moveit-arm-dora-node` | path to the arm node checkout |
| `EXEC_INTERP_SPEED` | `0.5` | motion speed (higher = faster; `1.0` ≈ 4×) |
| `GRIP_DWELL` | `3.0` | pause (seconds) at the grasp |
| `HEADLESS` | `0` | `1` = no viewer (CI/tuning) |
| `AUTO` | `0` | `1` = skip the ENTER prompt, pick immediately |

---

## Optional: drive it from a sentence (LLM-agent variant)

The default demo above is **deterministic** (a fixed pick→place script) and needs
nothing beyond the three repos. There's also an **agent** variant (`arm_agent.py`)
where a local LLM reads a sentence like *"pick up the red cube and place it on the
green plate"* and sequences the skill tools itself. It needs just two things:

1. **`openai`** (the provider client) — the agent SDK itself, `octos_py`, is already
   **vendored** in `moveit-arm-dora-node/skill_pack/octos_py/`, so there's no extra
   clone (see that folder's `VENDORED.md` for origin):

   ```bash
   pip install openai
   ```

2. **Ollama** running a local model:

   ```bash
   # install Ollama from https://ollama.com, then:
   ollama pull qwen3:8b
   ollama serve        # serves an OpenAI-compatible API on :11434
   ```

`WITH_AGENT=1 bash scripts/setup.sh` installs `openai` and reminds you about Ollama. No API
keys are involved — the agent talks to your **local** Ollama (`api_key="ollama"` is a
placeholder); `OPENAI_API_KEY` is only read if you repoint the provider at OpenAI.

To drive it from a sentence, run `arm_agent.py` (in `skill_pack`) against a running
bridge, e.g.:

```bash
ARM_BRIDGE_URL=http://127.0.0.1:8768 BALL_URL=http://127.0.0.1:8779/ball \
MODEL_NAME=<...>/so101_pickplace.xml ROBOT_MANIFEST=<...>/manifests/so101.json \
  <parent>/venv/bin/python <...>/skill_pack/arm_agent.py "pick up the red cube and place it on the green plate"
```

---

## Run it as an octos skill (full Agentic OS)

The launcher above runs the pick-and-place directly. To instead drive the robot from
**[octos](https://github.com/dorarobotics/octos)** — the Agentic OS — as a proper
**app-skill**, so a user just chats *"pick up the cube and place it on the green
plate"*:

### What an octos skill is

A skill is a directory octos loads from `~/.octos/skills/<name>/` with three parts —
this repo ships all three under `skills/so101/` (and `skills/rebot/`):

| File | Role |
|---|---|
| `SKILL.md` | YAML frontmatter = **lifecycle hooks** octos runs (`init` brings the dora dataflow up, `ready_check` waits on the bridge `/healthz`, `emergency_shutdown` e-stops) + the doc the LLM reads |
| `manifest.json` | declares the **tools** (`get_object_position`, `get_plate_position`, `pick_at`, `place_at`) with JSON Schema |
| `main` | the executable octos **spawns per tool call** — `main <tool>` with JSON args on stdin → `{"output":..,"success":..}` on stdout. It dispatches to the `arm_skills` pack (IK + grasp logic over the bridge), so one tool call = a full sub-action |

### Steps (on a host where octos runs)

```bash
# 1. install octos (Agentic OS) + give it an LLM provider
curl -fsSL https://github.com/dorarobotics/octos/releases/latest/download/install.sh | bash
export ANTHROPIC_API_KEY=...          # or configure a local Ollama provider

# 2. install the dora-side runtime (same 3 repos as above; e.g. via scripts/setup.sh)
#    — gives you the bridge, vendor node, dora-moveit2, in a venv with mujoco

# 3. sideload the skill into octos
cp -r octos-dora-bridge/skills/so101 ~/.octos/skills/so101     # (or skills/rebot)
octos skills list                                              # should show so101

# 4. tell the skill where the arm pack + model live (env octos spawns `main` with).
#    main needs a python that can import arm_skills (mujoco/numpy) — point octos's
#    skill interpreter at your venv, or put it first on PATH.
export SKILL_PACK=<parent>/moveit-arm-dora-node/skill_pack
export MODEL_NAME=<parent>/dora-moveit2/examples/move_group_demo/models/so101_pickplace.xml
export ROBOT_MANIFEST=$SKILL_PACK/manifests/so101.json

# 5. run
octos serve            # if not already running as a service
octos chat
> pick up the red cube and place it on the green plate
```

octos runs the skill's `init` hook (starts `dora start dataflows/so101-mujoco-bridge.yaml`
→ bridge on `:8768`), the LLM calls `get_object_position` → `pick_at` → `get_plate_position`
→ `place_at`, and `main` drives the arm for each. Adding a different robot = drop in its
`skills/<robot>/` (same `main`, its own `manifest.json` + `SKILL.md`) — no octos changes.

> **Note:** octos spawns a fresh `main` process per tool call, so the grasp state between
> `pick_at` and `place_at` is persisted to `/tmp/octos_grasp_<skill>.json` and restored —
> the robot keeps physically holding the object between calls. This is handled in `main`.

---

## How it works (one paragraph)

`skill_pickplace.py` (in `moveit-arm-dora-node/skill_pack`) senses the cube and
plate, solves grasp/approach joint configurations on demand with MuJoCo IK, and
drives the arm via the bridge's `move_to_joint_state` / `gripper.set` HTTP verbs.
Because the SO-101's small single rotating jaw can't form a stable rigid top-down
grasp in MuJoCo, the sim uses a **grasp weld**: the `mujoco_sim` node attaches the
cube to the gripper when the jaw is commanded closed (and releases it on open) — a
standard, opt-in sim-grasping technique, enabled here via the `GRASP_WELD` env on
the `mujoco_sim` node in `dataflows/so101-mujoco-bridge.yaml`.

## Troubleshooting

- **`bridge couldn't bind :8768` / viewer flickers** — a previous run's dora daemon
  is still up. The launcher's teardown handles this; if it persists, run
  `dora destroy` and retry.
- **`python deps missing`** — your `PYTHON` venv can't import one of the packages;
  re-check the editable installs above.
- **No window appears** — you're headless; set a display, or use `HEADLESS=1` to run
  without the viewer.
