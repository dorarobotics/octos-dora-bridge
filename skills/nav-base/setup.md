# setup.md — Run nav-base as an octos skill, no hardware (sim) + visualization

This stands up the **nav-base** mobile-navigation skill so you can drive a base from
**octos chat** with **no robot, no GPU, no SLAM stack** — fake localization/planner (or a
kinematic toy sim) stand in for [dora-nav](https://github.com/bobdingAI/dora-nav). It also
covers the **live Rerun visualization** (the blue-robot top-down map).

```
You (octos chat):  "go to the kitchen, then come back"
        │  HTTP POST /tools/<verb>
        ▼
octos-dora-bridge        (SPEC ⇄ HTTP, FastAPI on :8769)
        │  dora cmd_request / cmd_response
        ▼
nav-base-dora-node       (SPEC-VENDOR-NODE-V1 adapter)
        │  dora topics: goal / cancel / cmd_vel ↕ pose / status / obstacles
        ▼
fake_localization + fake_planner   (sim)      ──►  optional Rerun viewer
   └─ or dora-nav real binaries (hardware)
```

> This is the **bridge + skill + viz** quick start. For the deep dora-0.2.1 mechanics and
> the hardware swap, see `nav-base-dora-node/deploy.md` and this repo's `DEPLOYMENT.md`.

---

## 0. What you'll build

| Layer | Sim (this doc) | Hardware |
|---|---|---|
| Localization / planning | `examples/fake_localization.py` + `fake_planner.py` (or the toy sim for viz) | dora-nav real binaries |
| Vendor node | `nav-base-dora-node` (SPEC adapter) | same |
| Bridge | `octos_spec_bridge` on `:8769` | same |
| Skill | `skills/nav-base/SKILL.md` (tools auto-discovered from the advert) | same |

Unlike aka00 (pure HTTP, runs anywhere), nav-base runs through a **dora dataflow**, so it
needs the **dora 0.2.1 Linux stack** — realistically Ubuntu 22.04/24.04 or epyc, not a Mac.

---

## 1. Prerequisites

| Need | Notes |
|---|---|
| OS | Linux x86_64/ARM64 (Ubuntu 22.04/24.04 validated) |
| Python | 3.10–3.12 (`venv` or conda) |
| **dora 0.2.1** | CLI **and** python `dora-rs` must both be `0.2.1`, CLI built with `--attach` |
| **octos** CLI | the agent OS (`octos serve` / `octos chat`) |
| LLM backend | `ANTHROPIC_API_KEY` or local Ollama |
| Display + `rerun-sdk` | **only for §6 visualization** |

---

## 2. octos + LLM backend

Build octos from source (prebuilt needs glibc 2.38 — fine on Ubuntu 24.04, build from
source on 22.04). See `DEPLOYMENT.md §1` for the exact `cargo install` recipe.

```bash
export PATH="$HOME/.octos/bin:$PATH"
export ANTHROPIC_API_KEY=sk-ant-...        # or point octos at a local Ollama
```

---

## 3. Repos, venv, install

```bash
mkdir -p ~/octos-deploy && cd ~/octos-deploy
git clone https://github.com/dorarobotics/octos-dora-bridge.git
python3 -m venv venv && . venv/bin/activate
pip install --upgrade pip

# dora python runtime pinned to 0.2.1 FIRST (must match the CLI), then the bridge +
# nav-base node via the extra (pulls nav-base-dora-node from git).
pip install "dora-rs==0.2.1" pyarrow numpy
pip install -e "octos-dora-bridge/bridge[robots.nav-base]"

# For §6 visualization only:
pip install rerun-sdk
```

Put the **0.2.1 `dora` CLI** on `PATH` (`dora --version` → `dora-cli 0.2.1`).

---

## 4. The dora-0.2.1 env fixes (one-time)

A dora dataflow on a multi-NIC box needs two fixes (the third, `move_group` PYTHONPATH, is
arm-only and **not** needed for nav):

1. **`dataflows/venv-python` must point at your venv.** It's already a wrapper *script*
   (not a symlink — dora resolves symlinks and breaks venv detection). Confirm its
   interpreter path matches `~/octos-deploy/venv/bin/python`.
2. **`ZENOH_CONFIG`** disabling zenoh multicast+gossip scouting (loopback only), else a
   multi-interface host scouts the network and panics. See `DEPLOYMENT.md §2`.

---

## 5. Run headless sim as an octos skill (no viz)

**Sideload the skill** (SKILL.md only — nav-base tools are auto-discovered from the
capabilities advert; no `manifest.json`/`main` needed):

```bash
mkdir -p ~/.octos/skills
cp -r ~/octos-deploy/octos-dora-bridge/skills/nav-base ~/.octos/skills/nav-base
octos skills list        # -> nav-base + its verbs
```

**Start the bridge dataflow** (ships with `fake_localization` + `fake_planner` → no robot):

```bash
cd ~/octos-deploy/octos-dora-bridge
export PATH=/opt/dora/bin:$PATH                 # 0.2.1 CLI
export NAV_FAKE_MAP=1                            # satisfies the SKILL.md preflight (see note)
dora up && dora start dataflows/nav-base-bridge.yaml --attach
curl -fsS http://127.0.0.1:8769/healthz         # -> ok
```

> **Maps & waypoints (what the node actually reads).** In sim, **no map file is needed** —
> pose and obstacles arrive from the fake nodes' dora streams, not from disk. The node only
> reads `WAYPOINTS_PATH` (default `load_path.yml`), and **only** when you call
> `go_to_named`. `NAV_FAKE_MAP=1` is just a preflight bypass — it lets octos's `init` hook
> start without a `load_path.yml` present; the node does not consume it. To use named goals,
> drop a small waypoints file next to the dataflow:
> ```yaml
> # load_path.yml
> kitchen: { x: 2.0, y: 1.0, theta: 0.0 }
> dock:    { x: 0.0, y: 0.0, theta: 0.0 }
> ```
> `go_to_pose` / `get_pose` / `set_velocity` / `stop` need no waypoints file.

**Drive it from chat:**

```bash
octos serve        # in another shell, with the env above
octos chat
> where am I?            # -> vendor.dora_nav.localization.get_pose
> go to the kitchen      # -> vendor.dora_nav.base.go_to_named {"name":"kitchen"}
> stop
```

> `go_to_pose`/`go_to_named` return OK once the goal is **queued**, not when the base
> **arrives** — watch the `state` stream for `nav_status` transitions.

---

## 6. Visualization (Rerun top-down map)

The visual demo swaps `fake_localization`+`fake_planner` for a single **kinematic toy sim**
(`examples/nav_toy_sim.py`, a unicycle stand-in — *not* dora-nav) plus a **Rerun viewer**
(`examples/nav_rerun_viz.py`). The viewer subscribes to the same dora streams the node
drives, so **what you see is exactly what the nav verbs did over octos HTTP** — not a replay.

### What's drawn (top-down world frame)

| Element | Meaning |
|---|---|
| **Blue box** + **orange heading arrow** | the robot body & facing |
| **Orange trail** | path travelled (last ~800 poses) |
| **Green cross** | current goal |
| **Grey points** | static obstacles |
| **Text banner** | `nav_status` / estop banner |

### Run it

> **Needs a display.** Rerun's `rr.init(spawn=True)` opens a GUI window, so run this on a
> host with an X display (`DISPLAY=:0`) — an epyc/Ubuntu **remote desktop**, not a headless
> SSH session and not from a Mac. Requires `rerun-sdk` + numpy in the venv (§3).

**Turnkey (epyc):** run from a terminal *inside* the remote desktop —
```bash
bash scripts/run-nav-viz.sh
```
It boots `toy_sim + rerun_viz + nav_base + bridge`, waits for `:8769/healthz`, then runs
`examples/nav_demo_driver.py` — a **scripted skill sequence over octos HTTP**: drive to a
couple of goals, `set_velocity` spin in place (1.0 rad/s, 3 s), `stop`, head back toward the
origin, then `robot.estop` mid-drive (the base halts immediately and an estop event appears
on the banner). Ctrl-C tears down.

**Manual (portable):**
```bash
DISPLAY=:0 dora up
DISPLAY=:0 dora start dataflows/nav-base-viz.yml --attach
# then drive it yourself via octos chat, or:
NAV_BRIDGE_URL=http://127.0.0.1:8769 python examples/nav_demo_driver.py
```

### No display? Render an MP4 (headless)

When there's no X display (CI, plain SSH, a Mac), render the same scene to a video with
`examples/nav_render_mp4.py`. It drives the pure `ToySim` kinematics through the identical
scripted sequence (A→B→C, spin, stop, origin, ESTOP) and pipes frames to ffmpeg — **no
dora, no rerun, no display**. This is the same offline fallback used for the LeKiwi sim.

```bash
pip install pillow            # ffmpeg must be on PATH
python3 examples/nav_render_mp4.py skills/nav-base/nav_base_demo.mp4
# -> 720x720 h264, ~33s @ 20fps; blue robot + heading, orange trail, green goal,
#    grey obstacles, status banner (red on ESTOP)
```

A pre-rendered copy lives at `skills/nav-base/nav_base_demo.mp4`.

### Caveats
- The plain `nav-base-bridge.yaml` (§5, what octos normally uses) is **headless — no viz**;
  `nav-base-viz.yml` / `run-nav-viz.sh` add the toy sim + viewer purely for inspection.
- **Live-render stalls:** for the LeKiwi sim a live Rerun render blocked the dora loop (we
  fell back to an offline MP4). The nav viewer runs as its own dora node to avoid blocking
  the nav loop, but on a loaded box watch for stutter — if it stalls, render to file instead
  of `spawn=True`.

---

## 7. Real hardware

Swap the two fake nodes for dora-nav's real binaries in the dataflow, and set
`WAYPOINTS_PATH` to your site's waypoints. The **map is consumed by dora-nav**, not by this
node — `nav-base-dora-node` just relays goals/velocity downstream and reads the
pose/status/obstacle streams back, so its tools and the skill are identical between sim and
hardware; only the localization/planning source changes. See `nav-base-dora-node/deploy.md`
Milestone B.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| nodes die: `message format v0.6.0 not compatible with v0.2.1` | CLI and python `dora-rs` aren't both 0.2.1, or `venv-python` resolved to the base interpreter (it must be a wrapper script). |
| `PoisonError` in a node on startup | `ZENOH_CONFIG` scouting-off not set on a multi-NIC box (§4). |
| `preflight` fails | provide `load_path.yml` (copy `examples/waypoints.yaml`) or set `NAV_FAKE_MAP=1`. |
| Rerun viewer never opens | not on a display host — set `DISPLAY=:0` inside a desktop session; confirm `rerun-sdk` is installed. |
| `go_to_named` → INVALID_PARAMS | waypoint name not in the `WAYPOINTS_PATH` YAML. |
| octos chat works but base doesn't move | check the bridge dataflow is up (`curl :8769/healthz`) and `octos serve` inherited the env. |

---

## Why heavier than aka00

aka00 talks plain HTTP to its board — pure-Python, runs anywhere, fake = a 40-line server.
nav-base runs a **dora dataflow** (vendor node + planner/localization + bridge), so it
needs the version-pinned dora-0.2.1 Linux stack. The payoff: it rides the same
SPEC-VENDOR-NODE-V1 bridge as every other robot, and gets the Rerun visualization for free.
