# Deployment guide — octos + SO-101/reBot on a fresh Linux box

This is the **validated install sequence** for standing up the octos robot demo on a
fresh machine, plus the **environment gotchas** found while validating it on a clean
Ubuntu 22.04 host ("super", x86_64). Read the *Known blockers* section first — the
**dora runtime** currently needs attention before a fresh-box dataflow runs.

Reference box used for validation: **Ubuntu 22.04.5, glibc 2.35, x86_64**, no GPU
display (headless MuJoCo via EGL), Anthropic API key for octos.

---

## 0. Layout

```
~/octos-deploy/
├── octos                 # dorarobotics/octos (built from source -> octos binary)
├── dora-moveit2          # bobdingAI/dora-moveit2  (sim + MoveGroup framework)
├── moveit-arm-dora-node  # dorarobotics/...        (arm SPEC vendor node + skill_pack)
├── octos-dora-bridge     # dorarobotics/...        (bridge + dataflows + skills)
└── venv                  # python venv (mujoco + the repos + dora python)
```
All four repos are **public** — clone without auth.

---

## 1. octos (the Agentic OS)

> **Gotcha — glibc.** The prebuilt octos release (`octos-org/octos` v1.1.0) is linked
> against **glibc 2.38/2.39**. On **Ubuntu 22.04 (glibc 2.35)** it fails with
> `version 'GLIBC_2.38' not found`. Either use **Ubuntu 24.04+**, or **build from
> source** (below). Rust toolchain required (`cargo`); all C build deps were already
> present on the test box (gcc, pkg-config, cmake, libssl-dev, protoc).

```bash
mkdir -p ~/octos-deploy && cd ~/octos-deploy
git clone https://github.com/dorarobotics/octos.git
# build the CLI (produces the `octos` binary), install into ~/.octos/bin
cd octos
cargo install --path crates/octos-cli --root ~/.octos --force   # ~15-30 min
~/.octos/bin/octos --version        # -> octos 0.1.0 ...
```

Provider key (octos chat): export `ANTHROPIC_API_KEY` (the test box has it in
`~/.bashrc`); octos can also use a local Ollama instance.

---

## 2. The robot stack (dora + mujoco + repos)

```bash
cd ~/octos-deploy
git clone https://github.com/bobdingAI/dora-moveit2.git
git clone https://github.com/dorarobotics/moveit-arm-dora-node.git
git clone https://github.com/dorarobotics/octos-dora-bridge.git
git -C dora-moveit2 checkout master
git -C moveit-arm-dora-node checkout main
git -C octos-dora-bridge checkout main

python3 -m venv venv && . venv/bin/activate
pip install --upgrade pip
pip install mujoco numpy pyarrow
pip install -e dora-moveit2/dora_moveit -e dora-moveit2/dora-mujoco \
            -e moveit-arm-dora-node -e octos-dora-bridge/bridge
```

> **Gotcha — dora version (UNRESOLVED for fresh boxes).** The reference dataflow
> (`dataflows/so101-mujoco-bridge.yaml`) uses a **flat node format** (`path:`/`args:`/
> `inputs:`) and `dora start --attach`. This runs on **epyc's dora 0.2.1**, which is a
> **custom/non-stock build**. Stock dora releases do **not** reproduce it:
> | dora | result on a fresh box |
> |---|---|
> | 0.2.6 (stock) | yaml rejected: `no variant of enum NodeKind` |
> | 0.2.1 (stock) | no `--attach`; coordinator `Connection refused` |
> | 0.3.x | newer message format; bridge hits `Already borrowed` (background sends) |
> | copy of epyc's 0.2.1 binaries | CLI↔python **message-format mismatch** (v0.6.0 vs v0.2.1) |
>
> **Action needed (project-level):** standardize the dataflow + bridge on a single
> stock dora release — port `so101-mujoco-bridge.yaml` to that version's node schema
> and fix the bridge's background-send pattern for 0.3.x — *then* a fresh box can
> `pip install "dora-rs==<pinned>"` + matching CLI and run unmodified. Until then the
> dataflow only runs on epyc's dora.

Headless MuJoCo on a server: set `MUJOCO_HEADLESS=1` and `MUJOCO_GL=egl` on the
`mujoco_sim` node (EGL libs `libEGL.so.1`/`libGL.so.1` must be present).

---

## 3. The octos skill

The skill package (`octos-dora-bridge/skills/so101/` — `SKILL.md` + `manifest.json` +
`main`) is sideloaded into octos:

```bash
cp -r ~/octos-deploy/octos-dora-bridge/skills/so101 ~/.octos/skills/so101
octos skills list        # -> so101 with its 4 tools
```

`octos serve` must run with the skill's env so `main` can do IK + reach the bridge
(point the skill interpreter at the venv python, which has mujoco):

```
SKILL_PACK=~/octos-deploy/moveit-arm-dora-node/skill_pack
MODEL_NAME=~/octos-deploy/dora-moveit2/examples/move_group_demo/models/so101_pickplace.xml
ROBOT_MANIFEST=$SKILL_PACK/manifests/so101.json
ARM_BRIDGE_URL=http://127.0.0.1:8768   BALL_URL=http://127.0.0.1:8779/ball
```

> **Note — per-tool process:** octos spawns `main <tool>` per call, so the grasp state
> between `pick_at` and `place_at` is persisted to `/tmp/octos_grasp_<skill>.json`
> (handled in `main`). Verified working on epyc: all 4 tools return valid JSON,
> places 0.5 cm from target.

---

## 4. Run

```bash
octos serve            # (with the env above)
octos chat
> pick up the red cube and place it on the green plate
```
octos runs the skill's `init` hook (starts the dataflow → bridge on `:8768`), the LLM
calls `get_object_position → pick_at → get_plate_position → place_at`, and `main`
drives the arm for each.

---

## Validation status (on the fresh Ubuntu 22.04 box)

| Component | Status |
|---|---|
| octos (built from source) | ✅ runs (glibc-native) |
| mujoco venv + 4 repos | ✅ install + import |
| octos skill (`manifest.json`+`main`) | ✅ correct (proven end-to-end on epyc, 0.5 cm) |
| dora dataflow runtime | ⛔ blocked — needs a standardized stock dora (see §2 gotcha) |

**Bottom line:** octos and the robot/skill layers deploy cleanly to a fresh Ubuntu
22.04 box (octos from source). The single remaining blocker is the **dora runtime
version** — it must be standardized on a stock release for the dataflow to run
anywhere but epyc.
