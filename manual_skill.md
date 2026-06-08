# Manual: octos LLM agent driving a UR5e pick-and-place (clean-PC setup)

This runbook takes a **clean Linux PC that can run a local LLM** and gets you to:
the octos agent reads one English sentence — *"Pick up the red ball and place it
on the green plate"* — and drives a UR5e + gripper in MuJoCo to do it.

The robot is exposed to octos as **HTTP tools** by the `octos-dora-bridge` over a
dora-rs dataflow; the arm itself is the `moveit-arm-dora-node` vendor adapter
running `dora-moveit2`'s MoveGroup + MuJoCo sim. A small **skill layer**
(`arm_skills.py`) gives the LLM reliable `pick_at` / `place_at` actions.

```
"pick up the red ball and place it on the green plate"
        │
        ▼
  octos agent (octos_py SDK)  ──reasons with──►  local LLM (Ollama qwen3:8b)
        │  calls skill tools: get_ball_position / get_plate_position / pick_at / place_at
        ▼
  arm_skills.py  ──on-demand MuJoCo IK──►  joint waypoints
        │  HTTP POST /tools/<verb>  (move_to_joint_state, gripper.set, …)
        ▼
  octos-dora-bridge  ──cmd_request(dora)──►  moveit-arm-dora-node ──► dora-moveit2 (planner/IK/exec) ──► MuJoCo (UR5e + ball + green plate)
```

> **Note on "skill".** Two senses of skill are involved: (1) the **robot skill** =
> the `moveit-arm` vendor adapter exposed by the bridge as HTTP tools; (2) the
> **agent skill tools** (`arm_skills.py`) the LLM actually calls. This demo uses
> the **octos_py Python SDK** to run the agent (not the Rust `octos` CLI), because
> we register custom skill-level tools rather than the raw SPEC verbs.

---

## 0. Prerequisites

- **OS:** Ubuntu 22.04 / 24.04 (Linux). A real display (X11) on `:0` to *see* the
  MuJoCo viewer — a desktop session or VNC/remote-desktop. Headless works too
  (set `MUJOCO_HEADLESS=1`), you just won't see the window.
- **LLM host:** the PC must run **Ollama** with a tool-calling model. We use
  `qwen3:8b` (≈5 GB; runs on CPU, faster on a GPU). Any Ollama model with
  OpenAI-style tool-calling works.
- **Python:** 3.10 (conda/miniforge recommended).
- **Tools:** `git`, `curl`, `fuser` (psmisc), a C toolchain for some wheels.

---

## 1. Install the local LLM (Ollama + qwen3:8b)

```bash
curl -fsSL https://ollama.com/install.sh | sh     # installs + starts `ollama serve`
ollama pull qwen3:8b
# sanity: OpenAI-compatible endpoint is at http://127.0.0.1:11434/v1
curl -s http://127.0.0.1:11434/api/tags | grep qwen3:8b
```

---

## 2. Install the dora-rs CLI (version-matched!)

The dora **CLI** and the Python **`dora-rs`** package share a wire protocol that
is **not stable across minor versions** — both must be the same minor (use
**0.2.6**). Mismatch → nodes fail to register (`message format ... not compatible`).

```bash
# CLI (Rust) — pick ONE matching 0.2.6:
cargo install dora-cli --locked --version 0.2.6     # or download the 0.2.6 release binary
dora --version                                       # must report 0.2.6
```

> The Python `dora-rs==0.2.6` is installed by pip in step 4. Keep both at 0.2.6.
> (The bridge is written against the dora 0.2.x iteration API; 0.3.x is not
> supported — it hits `Already borrowed` on background sends.)

---

## 3. Clone the repos

```bash
export WORK=$HOME/octos-demo && mkdir -p "$WORK" && cd "$WORK"
git clone https://github.com/dorarobotics/octos-dora-bridge.git
git clone https://github.com/dorarobotics/moveit-arm-dora-node.git
git clone https://github.com/bobdingAI/dora-moveit2.git
git clone https://github.com/dorarobotics/octos-tutorial.git    # provides the octos_py/ SDK
```

**IMPORTANT — pin the feature branches.** The working code lives on branches that
are **not merged to main/master yet**, and the repos' git "extras" point at
main/master (which lack the fixes). Check out the branches and install from these
local checkouts (do **not** rely on the `[robots.moveit-arm]` / `[runtime]` git
extras, which would pull the unfixed default branches):

```bash
cd "$WORK/moveit-arm-dora-node" && git checkout feat/nonblocking-motion   # deferred-response motion + seq
cd "$WORK/dora-moveit2"         && git checkout feat/injectable-node       # ARM_QPOS_START=7, idle-hold,
                                                                            # firm gripper force, green plate@(0.25,0),
                                                                            # EXEC_INTERP_SPEED, injectable Node
cd "$WORK"
```

> Why these matter: `feat/nonblocking-motion` makes `move_to_joint_state` **block
> until the motion completes** (the skills depend on that to sequence moves);
> `feat/injectable-node` carries every sim fix that makes the arm actually track
> targets and hold the grasp through the carry.

---

## 4. Python env + install

Install everything from the **local branch checkouts** (not git extras), so the
pinned branches are what actually run:

```bash
conda create -n octos-arm python=3.10 -y && conda activate octos-arm

# --- the bridge (no robots extra — we install the vendor node from local below) ---
pip install -e "$WORK/octos-dora-bridge/bridge"

# --- moveit-arm vendor adapter, from the feat/nonblocking-motion checkout ---
pip install -e "$WORK/moveit-arm-dora-node" --no-deps      # avoid its @master runtime extra
pip install httpx                                          # (its only extra runtime dep not already present)

# --- dora-moveit2 (MoveGroup library + sim nodes), from the feat/injectable-node checkout ---
pip install -e "$WORK/dora-moveit2/dora_moveit"            # the `dora_moveit` MoveGroup package
pip install -e "$WORK/dora-moveit2/dora-mujoco"            # the MuJoCo sim node
pip install -e "$WORK/dora-moveit2/examples/move_group_demo"   # planner/ik/exec/scene nodes + ur5e config

# --- pin matched dora-rs + sim/agent deps ---
pip install "dora-rs==0.2.6" mujoco numpy openai

# --- octos_py SDK: pure-python, no install — just importable via OCTOS_PY_DIR at run time ---
```

Sanity-check the imports:

```bash
python - <<'PY'
import mujoco, numpy, openai, dora            # core
import moveit_arm_node, octos_spec_bridge      # vendor node + bridge
import dora_moveit                             # MoveGroup library
import sys; sys.path.insert(0, "$WORK/octos-tutorial")
import octos_py.agent                          # agent SDK
print("all imports OK")
PY
```

---

## 5. The skill + agent files (already in octos-dora-bridge)

Cloning `octos-dora-bridge` gives you everything for the agent demo under
`examples/` and `scripts/`:

| File | Role |
|---|---|
| `examples/arm_skills.py` | 4 skill tools — `get_ball_position`, `get_plate_position`, `pick_at(x,y)`, `place_at(x,y)`; on-demand MuJoCo IK + bridge verbs |
| `examples/arm_agent.py` | octos `Agent` + `OpenAIProvider`→Ollama; registers the 4 skills; `process_message(sentence)` |
| `examples/ball_state.py` | side HTTP server (:8779) publishing the ball's live position from sim qpos |
| `examples/gripper_merge.py` | folds the gripper width into MuJoCo's control vector |
| `scripts/run-arm-agent.sh` | turnkey launcher (preflight, dataflow boot, hands the sentence to the agent) |
| `dataflows/ur5e-mujoco-bridge.yaml` | canonical dataflow wiring (sim + moveit_arm + bridge) |

---

## 6. Wire the dataflow for your machine

The launcher boots a dataflow that runs, as dora nodes: `mujoco_sim`,
`planning_scene`, `planner`, `ik_solver`, `trajectory_executor`, `gripper_merge`,
`moveit_arm` (the SPEC adapter), `bridge` (HTTP :8768), and `ball_state` (:8779).

Two options:

**(a) Adapt the turnkey launcher** — edit the path variables at the top of
`scripts/run-arm-agent.sh` for your machine:

```bash
PY=$HOME/miniforge3/envs/octos-arm/bin/python          # your env's python
ROOT=$HOME/octos-demo                                   # your $WORK
BR=$ROOT/octos-dora-bridge
SRC=$ROOT/ur5e-mujoco-live.yml                          # the dataflow (see below)
MODEL=$ROOT/dora-moveit2/examples/move_group_demo/models/ur5e.xml
```

and create `ur5e-mujoco-live.yml` from the repo's
`dataflows/ur5e-mujoco-bridge.yaml`, replacing `${DORA_MOVEIT2}` with
`$WORK/dora-moveit2` and `./venv-python` with your env's python path. (dora cannot
interpolate env vars inside `path:`/`args:`, so paths must be concrete.) The
launcher then appends the `ball_state` node and flips the MuJoCo viewer on.

**(b) Run the steps manually** (what the launcher automates):

```bash
cd "$WORK/octos-dora-bridge"
dora up
dora start ur5e-mujoco-live.yml --attach &        # boots sim + bridge (+ ball_state if wired)
# wait until the bridge answers:
until curl -fsS http://127.0.0.1:8768/healthz >/dev/null; do sleep 1; done
```

---

## 7. Run it — the agent drives from a sentence

With the launcher (recommended), from a terminal **on the desktop** (so the viewer shows):

```bash
bash scripts/run-arm-agent.sh                                   # default sentence
bash scripts/run-arm-agent.sh "Move the red ball onto the green target."
HEADLESS=1 bash scripts/run-arm-agent.sh                        # no window, logs only
```

Or drive the agent directly against an already-running dataflow:

```bash
ARM_BRIDGE_URL=http://127.0.0.1:8768 \
BALL_URL=http://127.0.0.1:8779/ball \
MODEL_NAME=$WORK/dora-moveit2/examples/move_group_demo/models/ur5e.xml \
PLATE_X=0.25 PLATE_Y=0.0 \
OCTOS_PY_DIR=$WORK/octos-tutorial \
OLLAMA_BASE=http://127.0.0.1:11434/v1 OLLAMA_MODEL=qwen3:8b \
python octos-dora-bridge/examples/arm_agent.py "Pick up the red ball and place it on the green plate"
```

**Expected output:** the agent runs ~5 LLM iterations
(`get_ball_position` → `get_plate_position` → `pick_at` → `place_at` → done), the
UR5e picks the ball and places it on the green plate, and it reports the ball
landed ~1 cm from target.

---

## 8. How it works (so you can extend it)

- The LLM never touches the unreliable Cartesian `move_to_pose` — the skill tools
  solve **joint-space** IK against the MuJoCo `pinch` site and call the verified
  `move_to_joint_state` verb.
- `pick_at`/`place_at` bake in the reliability tricks: wait for the ball to
  settle, full-orientation grasp hold, staged lift, ~3 s grip dwell, **radial**
  carry (place at (0.25,0), directly in front — a sideways carry can roll the ball
  out of the grasp).
- To control a different robot, point the bridge at that robot's SPEC vendor
  adapter (`pip install octos-spec-bridge[robots.<name>]`) and write its skill
  tools; the agent layer is unchanged.

---

## 9. Troubleshooting (every issue we actually hit)

| Symptom | Cause / fix |
|---|---|
| Nodes fail to register; `message format vX not compatible` | dora CLI vs python `dora-rs` minor mismatch — make both **0.2.6**. |
| `address already in use ('127.0.0.1', 8768)`; bridge exits code 1; agent gets "connection refused" | A **stale bridge** holds the port (often a prior run not torn down). `fuser -k 8768/tcp 8779/tcp` before booting. The launcher does this. |
| `cannot connect to coordinator` / `WS session closed`; bridge **crash-loops** (re-binds every ~30s) | **Wedged dora daemon** carrying leftover dataflows. Hard reset: `dora destroy; pkill -9 -f "dora-coordinator|dora-daemon|octos_spec_bridge|dora_mujoco|ball_state"; fuser -k 8768/tcp 8779/tcp 6012/tcp 6013/tcp`, then `dora up`. Never run two dataflows at once. |
| Arm moves but never tracks targets / arm reads gripper joints as arm | `dora-moveit2` not on `feat/injectable-node` (missing `ARM_QPOS_START=7`). Check out the branch. |
| Arm snaps back to home after every move | Missing the executor idle-hold fix (same branch). |
| Ball is grasped + lifted but rolls out during the carry | Gripper force too low (default was 5 N) — needs the firm clamp (`fingers_actuator forcerange -150..150` in `ur5e.xml`, on the branch). |
| Agent replies but calls no tools | The registry must pin tools: `registry.set_base_tools([...])` (done in `arm_agent.py`); confirm Ollama model supports tool-calling. |
| MuJoCo viewer doesn't appear | No display — run on the desktop session with `DISPLAY=:0`, or accept `HEADLESS=1`. |
| `move_to_pose` misses targets badly | Known: the numpy DE Cartesian IK is unreliable — that's why the skills use joint-space IK. Don't drive grasps with `move_to_pose`. |

---

## 10. Component versions (verified working)

| Component | Version / source |
|---|---|
| dora CLI + `dora-rs` (py) | 0.2.6 (matched) |
| Python | 3.10 |
| LLM | Ollama `qwen3:8b` (OpenAI-compat at :11434/v1) |
| `octos-dora-bridge` | dorarobotics/octos-dora-bridge @ main |
| `moveit-arm-dora-node` | dorarobotics/moveit-arm-dora-node @ feat/nonblocking-motion |
| `dora-moveit2` | bobdingAI/dora-moveit2 @ **feat/injectable-node** |
| `octos_py` SDK | dorarobotics/octos-tutorial `octos_py/` |
| mujoco, numpy, openai | latest from PyPI |
