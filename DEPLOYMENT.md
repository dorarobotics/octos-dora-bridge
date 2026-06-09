# Deployment guide — octos + SO-101/reBot on a fresh Linux box

This is the **validated install sequence** for standing up the octos robot demo on a
fresh machine, plus the **environment gotchas** found while validating it on a clean
Ubuntu 22.04 host. The full pipeline (octos build → robot stack → dora dataflow →
pick-and-place) has been **validated end-to-end**, including on a box already running
an unrelated dora daemon (an FF robot) via the isolated-daemon runner (§4).

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

python3 -m venv venv && . venv/bin/activate     # clean venv; do NOT use ~/.local's dora
pip install --upgrade pip
# Pin the dora python runtime to 0.2.1 FIRST (matches the CLI; stock PyPI wheel,
# manylinux_2_34 → needs glibc >= 2.34). Then install the repos with --no-deps so
# nothing silently upgrades dora-rs (dora-mujoco's pyproject pins dora-rs>=0.3.9).
pip install "dora-rs==0.2.1" pyarrow mujoco numpy
pip install --no-deps \
    -e dora-moveit2/dora_moveit -e dora-moveit2/dora-mujoco \
    -e dora-moveit2/examples/move_group_demo \
    -e moveit-arm-dora-node -e octos-dora-bridge/bridge
python -c "import dora,pyarrow,mujoco,dora_moveit,dora_mujoco; print('venv ok, dora', dora.__version__)"
```

### Dora runtime — the working recipe

The reference dataflow (`dataflows/so101-mujoco-bridge.yaml`) uses dora's **flat node
format** (`path:`/`args:`/`inputs:`) and `dora start --attach`. Both the **CLI** and the
**python `dora-rs`** must be **0.2.1**, and the CLI must be the build that supports
`--attach` (stock 0.2.1 CLI lacks it). Three concrete requirements:

1. **CLI 0.2.1 with `--attach`.** On an FF robot box this already exists at
   `/opt/dora/bin/dora`. Otherwise copy the known-good binary from a working box (it's a
   self-contained ELF; epyc and the reference box are both glibc-2.35 x86_64, so the
   binary is portable) and put it on `PATH`. `dora --version` → `dora-cli 0.2.1`.
2. **python `dora-rs==0.2.1`** in the venv (stock PyPI wheel — installed in §2). The CLI
   and python message formats must match, or nodes die with
   `message format v0.6.0 is not compatible with expected message format v0.2.1`.
3. The launchers handle the **three environment fixes** automatically; if you ever run
   the dataflow by hand, replicate them:
   - **`venv-python` must be a wrapper *script*, not a symlink.** dora resolves symlinks
     before `exec`, so a symlink to `venv/bin/python` lands on the resolved base
     interpreter (`/usr/bin/python3`), Python loses venv detection, and nodes import a
     **system/user dora 0.3.x** instead of the venv's 0.2.1 → the v0.6.0 mismatch above.
     Use `#!/bin/bash\nexec "<venv>/bin/python" "$@"`.
   - **`ZENOH_CONFIG`** disabling zenoh multicast+gossip scouting, pinned to loopback.
     dora uses zenoh only for cross-*machine* routing (node↔daemon is TCP), so a
     single-box dataflow needs no discovery. On a multi-interface box (tailscale/docker)
     zenoh otherwise scouts the whole network and panics
     (`PoisonError` in `trajectory_executor`/`gripper_merge`).
   - **`PYTHONPATH=…/examples/move_group_demo`** so the move_group nodes can
     `import move_group_demo.config.<robot>` (that package isn't pip-installed by name).

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

### 4a. Run the demo directly — pick the launcher for your box

Both launchers apply the three env fixes from §2 automatically. Point `PYTHON` at the
0.2.1 venv and put the 0.2.1 `dora` on `PATH`:

```bash
export PATH=/opt/dora/bin:$PATH          # or wherever the 0.2.1 CLI lives
export PYTHON=~/octos-deploy/venv/bin/python
cd ~/octos-deploy/octos-dora-bridge
```

- **Dedicated box** (nothing else uses dora) — `examples/run-so101-demo.sh`. Runs
  `dora up` and, on teardown, kills any dora daemon to free `:8768`. Use a viewer with
  `HEADLESS=0`.
- **Shared / robot box** (a dora daemon is already running — e.g. an FF robot on the
  default coordinator `:6013`) — **`examples/run-so101-isolated.sh`**. Brings up its own
  coordinator+daemon on non-default ports (6113/6114), runs the demo there, and tears
  down only its **own** PIDs. It never runs `dora up`/`dora destroy`, never pkills a
  daemon, and never touches the default ports — the co-resident dataflow keeps running.

```bash
bash examples/run-so101-isolated.sh      # headless by default; AUTO=1
# -> pick_at OK (grasped+lifted) ; place_at OK (~0.9 cm from target)
```

### 4b. Run via octos chat

```bash
octos serve            # (with the env above)
octos chat
> pick up the red cube and place it on the green plate
```
octos runs the skill's `init` hook (starts the dataflow → bridge on `:8768`), the LLM
calls `get_object_position → pick_at → get_plate_position → place_at`, and `main`
drives the arm for each. (For a shared/robot box, point the skill's `init` at the
isolated runner so octos doesn't disturb the existing daemon.)

---

## Validation status (on the fresh Ubuntu 22.04 box)

| Component | Status |
|---|---|
| octos (built from source) | ✅ runs (glibc-native) |
| mujoco venv + 4 repos (dora-rs 0.2.1) | ✅ install + import |
| octos skill (`manifest.json`+`main`) | ✅ proven end-to-end (places ~0.9 cm) |
| dora dataflow runtime | ✅ runs — CLI 0.2.1 + venv dora-rs 0.2.1 + the three §2 fixes |
| isolated run on a live-robot box | ✅ demo ran; FF `ff-a2-bridge` daemon left untouched |

**Bottom line:** the whole pipeline deploys to a fresh Ubuntu 22.04 box and runs
end-to-end. The dora runtime is **not** a blocker — it just needs the matched **0.2.1**
CLI + python pair plus the three environment fixes (venv-python wrapper, `ZENOH_CONFIG`
scouting-off, `PYTHONPATH` for `move_group_demo`), all baked into the launchers. On a
box already running a dora daemon, use `run-so101-isolated.sh` to coexist safely.
