# Vendored wheels

Prebuilt **aarch64 / CPython 3.10** wheels for the pinned runtime stack. They live
in-tree because neither is installable from PyPI on this target:

- **dora-rs 1.0.1** — upstream publishes only `cp311-abi3` aarch64 wheels for 1.0.x,
  so `pip install dora-rs==1.0.1` cannot work on CPython 3.10.
- **octos 2.0.2** — `octos` is not published on PyPI at all, and the v2.0.2 release
  predates the `octos-pyo3` bindings, so there is no upstream wheel to fetch.

> **Platform:** all three are `aarch64` and need **glibc >= 2.34**. They will not
> install on x86_64 or on musl. CI (x86_64) must not try to use them.

## Contents

| Wheel | Version | Built from |
|---|---|---|
| `dora_rs-1.0.1-cp310-cp310-manylinux_2_34_aarch64.whl` | 1.0.1 | dora `py310/v1.0.1` @ `6fa29f49b` ("build(python): make v1.0.1 installable on CPython 3.10"), based on the `v1.0.1` tag |
| `dora_rs_cli-1.0.1-cp310-cp310-manylinux_2_34_aarch64.whl` | 1.0.1 | same commit; provides the `dora` CLI binary |
| `octos-2.0.2-py3-none-linux_aarch64.whl` | 2.0.2 | octos tag `v2.0.2` @ `b074918a` ("chore(release): v2.0.2 (#1813)") |

```
001f8af08b56b403e8cc70167d84a31c941cf73af1c5bc82e29272baced4c3a3  dora_rs-1.0.1-cp310-cp310-manylinux_2_34_aarch64.whl
772bb688b1bb98863659699176ee457ed109db6ac8f4ba55057a74312fade007  dora_rs_cli-1.0.1-cp310-cp310-manylinux_2_34_aarch64.whl
ae08a8b38e4b503b3ffd6e1375e6293b26e5d667def88d931cc5c9a17500ce7a  octos-2.0.2-py3-none-linux_aarch64.whl
```

## Installing

`setup.sh` does this automatically (`DORA_WHEELS` defaults to this directory):

```bash
pip install           vendor/wheels/dora_rs-1.0.1-*.whl
pip install --no-deps vendor/wheels/dora_rs_cli-1.0.1-*.whl   # --no-deps: re-declares deps that fight the node wheel
pip install           vendor/wheels/octos-2.0.2-*.whl          # puts the `octos` CLI on PATH
```

The dora **CLI and Python package must be the same version** (1.0.1) or nodes die at
registration with `message format vX is not compatible with expected vY`.

Install the wheels *before* the bridge. `dora-rs` is declared as the bridge's
**`runtime` extra** rather than a hard dependency (it is imported lazily and faked in
tests), so `pip install -e "bridge[dev]"` works without dora — which keeps CI green on
x86_64, where these aarch64 wheels cannot be used. `pip install -e "bridge[runtime]"`
then records the 1.0.1 pin against the already-installed wheel.

## Rebuilding

```bash
# dora 1.0.1 cp310 pair
cd <dora checkout>            # branch py310/v1.0.1
./build-py310.sh --verify     # -> dist310/

# octos 2.0.2 CLI
git worktree add --detach <dir> v2.0.2
cd <dir> && cargo build --release -p octos-cli \
    --features "api,telegram,discord,whatsapp,feishu,twilio,wecom,wecom-bot,audio_mp3"
# then wrap target/release/octos into a wheel (.data/scripts/ layout, mode 0755)
```

## A note on `octos-2.0.2`

This wheel ships the **CLI binary**, not an importable module — `import octos` will
fail. The bridge only ever talks to octos over HTTP (`octos_spec_bridge/http_api.py`),
so it needs the `octos serve` binary, not Python bindings. Those bindings
(`crates/octos-pyo3`) first appear in `v2.0.3-rc.1`; no official 2.0.x release has them.
