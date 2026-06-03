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

Supported robots (today):

| Robot | Vendor adapter | Status |
|---|---|---|
| AgiBot A2 | [agibot-a2-dora-node](https://github.com/dorarobotics/agibot-a2-dora-node) | MVP (MuJoCo sim) |

## Install

```bash
git clone https://github.com/dorarobotics/octos-dora-bridge.git
cd octos-dora-bridge/bridge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,robots.agibot-a2]"
```

### Runtime requirements (dora versions must match)

The `dora` CLI/daemon and the Python `dora-rs` package use a wire protocol
that is **not stable across versions**. Both sides must come from the same
minor release — e.g. CLI 0.2.x talks only to Python `dora-rs` 0.2.x.

PyPI no longer ships `dora-rs==0.2.1`; the lowest available 0.2.x Python
package is `dora-rs==0.2.3`. If your local `dora` CLI is older than that,
`pip install` from PyPI will give you an incompatible Python package and
nodes will fail to register with errors like
`unknown variant 'socket_addr', expected 'Shmem' or 'Tcp'` or
`message format v0.5.0 is not compatible with expected message format v0.2.1`.

Verified-compatible combinations:

| `dora` CLI | Python `dora-rs` | Source |
|---|---|---|
| 0.2.6 (any 0.2.3–0.2.6) | 0.2.6 | both from PyPI / matched releases |
| 0.3.x | 0.3.x | both from PyPI (`dora-rs-cli` for the CLI). **Note:** the current bridge is written against the 0.2.x iteration API; running on 0.3.x will hit `RuntimeError: Already borrowed` from background-thread sends. See follow-up in the design doc. |

Recommended for MVP: align both to `0.2.6` from PyPI.

## Known runtime gaps (MVP)

- **dora 0.3.x compatibility** — bridge background sends use the 0.2.x API
  pattern that hit `Already borrowed` on 0.3.x. Filed as v0.2.0 work.
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
