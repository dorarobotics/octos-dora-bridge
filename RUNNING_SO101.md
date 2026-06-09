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
| `EXEC_INTERP_SPEED` | `0.45` | motion speed (higher = faster; `1.0` ≈ 4×) |
| `GRIP_DWELL` | `3.0` | pause (seconds) at the grasp |
| `HEADLESS` | `0` | `1` = no viewer (CI/tuning) |
| `AUTO` | `0` | `1` = skip the ENTER prompt, pick immediately |

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
