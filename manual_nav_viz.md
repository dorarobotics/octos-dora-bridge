# Manual: nav-base visual demo (asus / GPU-less remote-desktop box)

Complete copy-paste commands to bring up the **visual nav-base patrol demo** by
hand — the same thing `scripts/run-nav-viz-asus.sh` does, broken into steps you
can run and debug one at a time.

Boots: toy sim + **matplotlib viewer** + `nav_base` node + octos bridge on
`DISPLAY :0`, waits for the bridge on `:8769`, then runs a continuous patrol loop.

```
nav_demo_loop.py ──HTTP POST /tools/<verb> :8769──► octos bridge
        │                                               │ cmd_request (dora)
        ▼                                               ▼
   (waypoints)                                      nav_base node ──goal/cmd_vel──► toy_sim
                                                        ▲ pose/status/obstacles ──┘
   nav_mpl_viz.py (matplotlib window on :0) ◄── pose/obstacles/status/goal/safety
```

> **Why matplotlib, not rerun:** rerun's GL viewer renders via software
> Vulkan/llvmpipe on a GPU-less host and shows **black** over RustDesk/NoMachine.
> The matplotlib (TkAgg) window is a plain raster window remote desktop captures.

---

## If you hit `No such file or directory` on `nav-base-viz-live.yml`

```
./run-nav-viz.sh: line 25: /home/demo/dorarobotics-test/nav-base-viz-live.yml: No such file or directory
```

You ran **`run-nav-viz.sh`** — the generic/epyc launcher, which writes to
`~/dorarobotics-test/` (that path doesn't exist on asus). On the asus box use the
asus launcher, or the manual steps below:

```bash
cd ~/octos-deploy/octos-dora-bridge
bash scripts/run-nav-viz-asus.sh        # asus paths: ~/octos-deploy/...
```

---

## 0. Prerequisites (asus box)

- Repos under `~/octos-deploy/{octos-dora-bridge,nav-base-dora-node}`
- Bridge venv at `octos-dora-bridge/bridge/.venv` with: this bridge (editable),
  `nav-base-dora-node` (editable), **`dora-rs==0.4.0`**, `matplotlib` (tkinter present)
- **Official dora 0.4.0** CLI on PATH (here `~/.local/bin/dora`) — *not* 0.2.x
- An X session on `DISPLAY :0` that the remote-desktop tool mirrors

SSH in: `ssh demo@100.86.247.4` (passwordless).

---

## 1. Environment

```bash
export DISPLAY=":0"
export XAUTHORITY="$HOME/.Xauthority"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

ROOT=$HOME/octos-deploy
BR=$ROOT/octos-dora-bridge
WAYPOINTS=$ROOT/nav-base-dora-node/examples/waypoints.yaml
BRIDGE_URL="http://127.0.0.1:8769"
```

## 2. Preflight checks

```bash
dora --version                                   # expect 0.4.0
ls -l "$BR/dataflows/venv-python"                # wrapper must exist + be executable
ls "$WAYPOINTS"                                  # waypoints present
"$BR/bridge/.venv/bin/python" - <<'PY'
import dora, matplotlib, nav_base_node, octos_spec_bridge
print("venv OK — dora", dora.__version__)
PY
```

All four must pass. If `dora --version` isn't 0.4.0, fix PATH first (stock 0.2.x
will fail with `unknown variant 'socket_addr'` / "message format not compatible").

## 3. Write the dataflow

`run-nav-viz-asus.sh` generates this each run; create it once manually. It must
live in `dataflows/` because nodes use a **relative** `./venv-python` and dora
sets each node's CWD to the dataflow file's directory.

```bash
cat > "$BR/dataflows/nav-base-viz-live.yml" <<YAML
nodes:
  - id: toy_sim
    path: ./venv-python
    args: ../examples/nav_toy_sim.py
    env: { TOY_SIM_DT: "0.05", DISPLAY: ":0" }
    inputs:
      tick: dora/timer/millis/50
      goal: nav_base/dora_nav_goal
      cancel: nav_base/dora_nav_cancel
      cmd_vel: nav_base/dora_nav_cmd_vel
    outputs: [pose, status, obstacles]

  - id: nav_base
    path: ./venv-python
    args: -m nav_base_node
    env:
      ROBOT_ID: nav-base-001
      WAYPOINTS_PATH: $WAYPOINTS
      HEARTBEAT_TIMEOUT_MS: "0"
      LOG_LEVEL: INFO
    inputs:
      cmd_request: bridge/cmd_request
      dora_nav_pose: toy_sim/pose
      dora_nav_status: toy_sim/status
      dora_nav_obstacles: toy_sim/obstacles
    outputs: [cmd_response, capabilities, state, safety_event, dora_nav_goal, dora_nav_cancel, dora_nav_cmd_vel]

  - id: rerun_viz
    path: ./venv-python
    args: ../examples/nav_mpl_viz.py
    env: { DISPLAY: ":0" }
    inputs:
      pose: toy_sim/pose
      obstacles: toy_sim/obstacles
      status: toy_sim/status
      goal: nav_base/dora_nav_goal
      safety_event: nav_base/safety_event
    outputs: [ready]

  - id: bridge
    path: ./venv-python
    args: -m octos_spec_bridge
    env:
      ROBOT_ID: nav-base-001
      HTTP_HOST: "127.0.0.1"
      HTTP_PORT: "8769"
      CMD_TIMEOUT_S: "30"
      LOG_LEVEL: INFO
    inputs:
      cmd_response: nav_base/cmd_response
      capabilities: nav_base/capabilities
      state: nav_base/state
      safety_event: nav_base/safety_event
    outputs: [cmd_request]
YAML
```

## 4. Clean up any prior run

Kill stale daemons first, then leftover node processes (they hold `:8769` and the
display):

```bash
for i in $(seq 1 8); do
  pkill -9 -f dora-coordinator 2>/dev/null
  pkill -9 -f dora-daemon 2>/dev/null
  pkill -9 -f "dora up" 2>/dev/null
  sleep 1
  [ "$(pgrep -cf 'dora-coordinator|dora-daemon')" = "0" ] && break
done
pkill -9 -f "bridge/.venv/bin/python" 2>/dev/null
sleep 2
```

## 5. Start dora + the dataflow

```bash
cd "$BR"                                          # MUST cd here first
dora up
sleep 8                                           # let the coordinator/daemon settle
dora start dataflows/nav-base-viz-live.yml --attach
```

> **Use the RELATIVE path** `dataflows/nav-base-viz-live.yml` from `$BR`. An
> absolute path makes dora 0.4.0 pick a node CWD that breaks `./venv-python`.

Leave this attached (it prints node logs). The matplotlib window should appear on
`DISPLAY :0` (your RustDesk/NoMachine view). To run it in the background instead:

```bash
dora start dataflows/nav-base-viz-live.yml --attach > "$ROOT/nav-viz-dataflow.log" 2>&1 &
```

## 6. Verify the bridge, then start the patrol loop

In a **second terminal** (re-export the env from step 1, or `ssh` again):

```bash
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
BR=$HOME/octos-deploy/octos-dora-bridge
BRIDGE_URL="http://127.0.0.1:8769"

# wait for the bridge to answer
until curl -fsS -m2 "$BRIDGE_URL/healthz" >/dev/null 2>&1; do sleep 1; done
echo "bridge up"

# continuous patrol — runs until you Ctrl-C (no estop, so it never latches)
NAV_BRIDGE_URL="$BRIDGE_URL" "$BR/bridge/.venv/bin/python" "$BR/examples/nav_demo_loop.py"
```

The robot now drives between waypoints in the matplotlib viewer. Background it with
`setsid nohup … &` if you want it to keep running after the terminal closes.

## 7. Tear down

```bash
dora stop 2>/dev/null; dora destroy 2>/dev/null
pkill -9 -f dora-coordinator; pkill -9 -f dora-daemon
pkill -9 -f "bridge/.venv/bin/python"
```

---

## Verb reference (drive it by hand instead of the loop)

The bridge exposes nav verbs at `POST $BRIDGE_URL/tools/<verb>`. **Params go
inside an `{"args": {...}}` wrapper** (that's what the bridge parses; an empty call
is `{"args":{}}`). List the catalog with `GET /tools`. Verbs are those
`nav_base_node` registers (`nav_base_node/node.py`); the pose shape is the SPEC
`position`/`orientation` form (xyz + xyzw quaternion), same as the loop uses.

```bash
# list available verbs
curl -s "$BRIDGE_URL/tools" | jq '.tools[].name'

# go to a pose (x, y in metres; z=0, identity orientation for a planar base)
curl -s -X POST "$BRIDGE_URL/tools/vendor.dora_nav.base.go_to_pose" \
     -H 'content-type: application/json' \
     -d '{"args":{"pose":{"position":[2.0,1.0,0.0],"orientation":[0.0,0.0,0.0,1.0]},"control_source":"manual"}}'

# go to a named waypoint (names come from waypoints.yaml)
curl -s -X POST "$BRIDGE_URL/tools/vendor.dora_nav.base.go_to_named" \
     -H 'content-type: application/json' -d '{"args":{"name":"P1","control_source":"manual"}}'

# stop (privileged — works even during estop, ignores the controller lock)
curl -s -X POST "$BRIDGE_URL/tools/vendor.dora_nav.base.stop" \
     -H 'content-type: application/json' -d '{"args":{}}'

# read current pose / obstacles
curl -s -X POST "$BRIDGE_URL/tools/vendor.dora_nav.localization.get_pose" \
     -H 'content-type: application/json' -d '{"args":{}}'
curl -s -X POST "$BRIDGE_URL/tools/vendor.dora_nav.map.get_obstacles" \
     -H 'content-type: application/json' -d '{"args":{}}'
```

Full verb set: `vendor.dora_nav.base.{go_to_pose, go_to_named, set_velocity, stop}`,
`vendor.dora_nav.localization.get_pose`, `vendor.dora_nav.map.get_obstacles`, plus
the common `robot.{heartbeat, estop, release_control, get_capabilities}`.

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `…/dorarobotics-test/nav-base-viz-live.yml: No such file` | ran `run-nav-viz.sh` (epyc paths) on asus — use `run-nav-viz-asus.sh` or these manual steps |
| `./venv-python: No such file or directory` | started the dataflow with an **absolute** path, or not from `$BR`; `cd "$BR"` and use the relative `dataflows/…` path; ensure `dataflows/venv-python` is executable |
| matplotlib window is black / absent | check `DISPLAY=:0` and `XAUTHORITY`; confirm the remote-desktop tool mirrors `:0`; rerun's GL viewer is black on GPU-less hosts — this demo already uses matplotlib |
| `unknown variant 'socket_addr'` / "message format not compatible" | dora version mismatch — CLI **and** venv `dora-rs` must both be 0.4.0 |
| bridge `/healthz` never comes up | read `$ROOT/nav-viz-dataflow.log`; usually a node crashed on import (missing dep in the venv) or `:8769` still held by a prior run (redo step 4) |
| two viewers / port clash | a second `dora up` spawned a second daemon — kill all daemons (step 4) and start once |

---

## One-shot: just use the launcher

Everything above is automated and idempotent in:

```bash
cd ~/octos-deploy/octos-dora-bridge
bash scripts/run-nav-viz-asus.sh
```

The manual steps are for debugging or running on a box whose paths differ from
the asus `~/octos-deploy` layout.
