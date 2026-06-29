# dora 1.0-rc.1 (from source) — build + validation

`dora-rs` `v1.0.0-rc.1` is the **Q1 2026 Rust-first rewrite**. Notes:
- It has **no PyPI wheel and no GitHub release binary** — only the git tag. You
  must build the CLI **and** the Python binding from source, version-matched.
- Its internal `[workspace.package] version` is **0.2.1** (the tag is the
  milestone; crate versions are 0.2.x). So CLI and binding both report `0.2.1`,
  and the dependency pin must be **unpinned `dora-rs`** — a `>=0.4` cap excludes it.
- Requires Rust **edition 2024 / rustc >= 1.88** (we used stable 1.96.0).

## Build (asus)

    rustup default stable                      # >= 1.88
    git clone --depth 1 -b v1.0.0-rc.1 https://github.com/dora-rs/dora ~/dora-src
    cargo install --path ~/dora-src/binaries/cli --root ~/dora1 --locked   # -> ~/dora1/bin/dora
    python3.10 -m venv .venv-dora1
    .venv-dora1/bin/pip install ~/dora-src/apis/python/node                # binding (0.2.1)
    .venv-dora1/bin/pip install -e nav-base-dora-node -e octos-dora-bridge/bridge matplotlib

Keep the 0.4.0 CLI (`~/.local/bin/dora`) as a fallback; the 1.0 CLI lives at
`~/dora1/bin/dora` (select via PATH). Harness: `scripts/run-nav-viz-asus-dora1.sh`
+ `dataflows/venv-python-dora1`.

## Validation result (nav-viz, $(date -u +%Y-%m-%d))

PASS — CLI + binding a matched pair (both 0.2.1). All 4 nodes spawn and reach
ready; bridge captures the capabilities advert over the dora 1.0 event channel;
`vendor.dora_nav.base.go_to_pose` returns `{"ok":true,"code":"0"}`. No
`Already borrowed`, no event-API break, no compat shim needed beyond the existing
0.4 one. (Only gotcha: a stale 0.4.0 bridge holding :8769 must be killed first.)
