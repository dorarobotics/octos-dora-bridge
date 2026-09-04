# dora 1.0 — the runtime this repo targets

`dora-rs` **1.0.1** is the formal 1.0 release and is what the bridge now pins
(`dora-rs>=1.0.1,<1.1` in `bridge/pyproject.toml`).

## Install

Both halves of the runtime ship wheels on PyPI, so the whole thing is pip-only:

    python3.11 -m venv .venv && source .venv/bin/activate
    pip install "dora-rs==1.0.1" "dora-rs-cli==1.0.1"
    pip install -e bridge          # plus the vendor adapter(s) you need

Put the venv's `bin/` first on `PATH`. Installing the CLI *into the same venv*
as the binding is the one reliable way to keep the pair matched — the
CLI/daemon wire protocol is not stable across minor releases, and a stray
`~/.local/bin/dora` or `~/.cargo/bin/dora` from an older install will shadow it
and fail at node registration.

    which dora        # -> <venv>/bin/dora
    dora --version    # -> dora-cli 1.0.1

## What changed vs. the rc.1 era

The previous commit on this branch targeted `v1.0.0-rc.1`, which had **no PyPI
wheel and no release binary** — the CLI and the Python binding both had to be
built from source with cargo, and both reported an internal version of `0.2.1`,
so `dora-rs` had to be left unpinned. That is all obsolete:

| | v1.0.0-rc.1 | **1.0.1** |
|---|---|---|
| Python binding | build from `apis/python/node` | `pip install dora-rs==1.0.1` |
| CLI | `cargo install --path binaries/cli` | `pip install dora-rs-cli==1.0.1` |
| Reported version | `0.2.1` (internal) | `1.0.1` |
| Dependency pin | unpinned (a `>=0.4` cap excluded it) | `>=1.0.1,<1.1` |
| Rust toolchain | edition 2024 / rustc >= 1.88 | not needed |

The from-source harness that existed only for rc.1
(`scripts/run-nav-viz-asus-dora1.sh`, `dataflows/venv-python-dora1`) has been
deleted; `scripts/run-nav-viz-asus.sh` runs on 1.0.1 directly.

## Python floor moved to 3.11

`dora-rs` 1.0.x publishes **cp311-abi3 wheels only** and declares
`requires-python >=3.11`. On Python 3.10 pip does not error — it quietly
resolves back to a 0.5.x `dora-rs`, and the nodes then fail the handshake with
a message-format mismatch. So:

- `bridge/pyproject.toml` → `requires-python = ">=3.11"` (ruff/mypy target 3.11)
- CI matrix dropped 3.10; now `["3.11", "3.12"]`
- `setup.sh` hard-fails with a clear message if `python3` is < 3.11
  (override with `PY_BOOTSTRAP=python3.12`)

## Python API compatibility

No bridge code changes were needed. On 1.0.1 the API the bridge depends on is
unchanged:

- `dora.Node` still implements `__iter__`/`__next__`, so `for event in node:`
  in `bridge/octos_spec_bridge/dora_loop.py` works as-is.
- Events are still subscript-accessible (`event["type"]`, `event["id"]`,
  `event["value"]`), so the `_as_event_dict` normalizer still covers both the
  dict-yielding fork and stock `dora-rs`.
- `send_output(output_id, pyarrow.Array, metadata=None)` is unchanged.
- `Node` still has no `close()`, so `DoraLoop.stop()` keeps its
  `hasattr(..., "close")` guard and the zombie-thread warning.

No `RuntimeError: Already borrowed` from background-thread sends — the 0.3.x
problem noted in older revisions of the README does not reproduce on 1.0.x.

## Validation

- **Bridge suite on 1.0.1** — all 62 tests in `bridge/` pass with
  `dora-rs==1.0.1` installed (Python 3.12); `dora --version` reports
  `dora-cli 1.0.1`.
- **nav-viz end-to-end** — validated on the immediate predecessor
  (`v1.0.0-rc.1`, built from source): all four nodes spawn and reach ready, the
  bridge captures the capabilities advert over the dora event channel, and
  `vendor.dora_nav.base.go_to_pose` returns `{"ok":true,"code":"0"}`. Not yet
  re-run against the 1.0.1 wheels on the asus box.
  - Gotcha carried over: a stale bridge holding `:8769` must be killed first.
