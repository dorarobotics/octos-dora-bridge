# octos-dora-bridge

Drop-in skills that let [octos](https://github.com/octos-org/octos) control
real robots via [dora-rs](https://github.com/dora-rs/dora) vendor adapters
that speak `SPEC-VENDOR-NODE-V1`.

octos doesn't have to know anything about dora or any specific robot — it
just calls HTTP tools. The bridge in this repo is the only piece that
translates between octos and the vendor wire format.

## What's in here

- **`bridge/octos_spec_bridge/`** — the SPEC-aware bridge: a dora node + FastAPI
  HTTP server. One bridge speaks to any spec-conforming vendor adapter.
- **`skills/<vendor>-<model>/SKILL.md`** — per-robot skills (lifecycle, safety tier,
  workspace, known quirks). Loaded by octos.
- **`dataflows/<robot>-bridge.yaml`** — wires the bridge to a specific vendor adapter.
- **`manual_nav_viz.md`** — step-by-step manual commands for the nav-base visual
  patrol demo on the asus / GPU-less remote-desktop box (the hand-run equivalent
  of `scripts/run-nav-viz-asus.sh`).

Supported robots (today):

| Robot | Vendor adapter | Status |
|---|---|---|
| AgiBot A2 | [agibot-a2-dora-node](https://github.com/dorarobotics/agibot-a2-dora-node) | MVP (MuJoCo sim) |

## Install

```bash
git clone https://github.com/dorarobotics/octos-dora-bridge.git
cd octos-dora-bridge/bridge
python3.11 -m venv .venv && source .venv/bin/activate   # 3.11+ required
pip install -e ".[dev,robots.agibot-a2]"
pip install "dora-rs-cli==1.0.1"    # the matched CLI/daemon, into the same venv
```

### Runtime requirements (dora versions must match)

The bridge targets **dora 1.0.1** — the formal 1.0 release. Both the Python
binding (`dora-rs`) and the CLI/daemon (`dora-rs-cli`) ship wheels on PyPI, so
the whole runtime installs with pip; no cargo build is needed.

```bash
pip install "dora-rs==1.0.1" "dora-rs-cli==1.0.1"
```

The `dora` CLI/daemon and the Python `dora-rs` package share a wire protocol
that is **not stable across versions**. Both sides must come from the same
minor release. The simplest way to guarantee that is to install the CLI **into
the same venv** as the bridge and put that venv's `bin/` first on `PATH` — then
`dora` and `import dora` can never drift apart.

`dora-rs` 1.0.x publishes **cp311-abi3 wheels only** and declares
`requires-python >=3.11`. On Python 3.10 pip quietly resolves back to a 0.5.x
`dora-rs` and the nodes then fail the handshake, so the bridge's floor is now
**Python 3.11**.

Verified-compatible combinations:

| `dora` CLI | Python `dora-rs` | Python | Source |
|---|---|---|---|
| **1.0.1** | **1.0.1** | 3.11+ | both from PyPI (`dora-rs-cli` for the CLI). **Recommended.** |
| 0.4.0 | 0.4.0 | 3.10+ | both from PyPI. Previous target; see `manual_nav_viz.md`. |
| 0.2.6 (any 0.2.3–0.2.6) | 0.2.6 | 3.10+ | matched releases. Legacy — the 0.2.x records in `DEPLOYMENT.md` / `manual_skill.md` describe this pair. |

Symptoms of a mismatched pair: `unknown variant 'socket_addr', expected 'Shmem'
or 'Tcp'`, or `message format vX is not compatible with expected message format
vY` at node registration.

See [`DORA_1.0.md`](DORA_1.0.md) for what changed in 1.0 and the validation
record.

## Known runtime gaps (MVP)

- **`BRIDGE_DOWN` error code** — when the dora-loop thread dies, in-flight
  calls hit `BRIDGE_TIMEOUT` (30s) instead of the spec's intended fast-fail.
- **Background heartbeat timer** — for adverts with non-zero
  `heartbeat_timeout_ms` (i.e. real hardware), the operator/LLM must send
  heartbeats manually. The bridge does not yet pulse them automatically.

## Quick start (A2 MuJoCo sim)

```bash
cd /path/to/octos-dora-bridge
dora up
dora start dataflows/a2-bridge.yaml --attach
```

In another terminal:

```bash
curl http://127.0.0.1:8765/healthz
curl http://127.0.0.1:8765/tools | jq '.tools[].name'
curl -X POST http://127.0.0.1:8765/tools/robot.heartbeat -H "Content-Type: application/json" -d '{"args":{}}'
```

## Adding a new robot

Once the robot has a SPEC-VENDOR-NODE-V1-conforming dora adapter (e.g. `unitree-g1-dora-node`):

1. `pip install unitree-g1-dora-node` into the same venv.
2. `mkdir -p skills/unitree-g1` and create a `SKILL.md` with the robot's
   lifecycle, safety tier, workspace, and any known quirks. Look at
   `skills/agibot-a2/SKILL.md` as a template.
3. Create `dataflows/g1-bridge.yaml` — copy `a2-bridge.yaml` and change the
   first node's `args:` to `python -m unitree_g1_node` plus the relevant env vars.
4. **Zero bridge code changes. Zero octos changes.**

If your vendor adapter speaks the spec correctly, that's it.

## How it works

```
┌─────────────┐  HTTP /tools/<name>   ┌─────────────────────┐
│   octos     │ ─────────────────────>│  octos-spec-bridge  │
│  (Rust)     │ <──────────────────── │  (dora node + HTTP) │
└─────────────┘                       └──────────┬──────────┘
                                                 │ dora cmd_request
                                                 ▼
                                      ┌─────────────────────┐
                                      │  vendor adapter     │
                                      │  (per-robot dora    │
                                      │   node, SPEC-V1)    │
                                      └──────────┬──────────┘
                                                 │ vendor-specific RPC
                                                 ▼
                                              robot
```

## License

Apache-2.0.
