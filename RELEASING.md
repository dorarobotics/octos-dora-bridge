# Releasing octos-dora-bridge

Releases are cut by **pushing a tag**. Everything after that is automated by
`.github/workflows/release.yml`. This file is the human half.

## The short version

```bash
# 1. Bump the version (this is the source of truth CI checks against)
vim bridge/pyproject.toml            # [project] version = "0.2.0"

# 2. Refresh the changelog. --tag is required: the tag does not exist yet, so
#    without it git-cliff heads the new section "Unreleased" instead of "0.2.0".
git cliff --tag v0.2.0 --output CHANGELOG.md    # or: brew install git-cliff

# 3. Commit, tag, push
git commit -am "chore: release v0.2.0"
git tag -a v0.2.0 -m "v0.2.0"        # -a matters: see the note below
git push origin main --follow-tags
```

> **Use `git tag -a`.** `--follow-tags` pushes *annotated* tags only. A
> lightweight `git tag v0.2.0` is silently left behind — you get a `main` push,
> no tag, no release, and **no error**. If you already made a lightweight tag,
> push it by name: `git push origin v0.2.0`. Either way, confirm it landed
> before walking away:
>
> ```bash
> git ls-remote --tags origin v0.2.0     # must print the tag
> ```

Then watch the **release** workflow. When it goes green the release is live at
`https://github.com/dorarobotics/octos-dora-bridge/releases/tag/v0.2.0`.

## What CI does with the tag

| Job | What it does | Fails when |
|---|---|---|
| `check-version` | Compares the tag against `bridge/pyproject.toml` | tag `v0.2.0` but pyproject says `0.1.0` |
| `test` | Runs the bridge suite on Python 3.11 + 3.12 | any test fails |
| `build` | `python -m build` → wheel + sdist | packaging is broken |
| `github-release` | git-cliff notes + GitHub PR list + attaches the artifacts | any of the above failed |

The version guard exists because dora shipped rc.2 artifacts under an rc.3 tag.
It is the cheapest check in the file — never remove it.

## Version rules

- Tags are `vMAJOR.MINOR.PATCH`, matching `bridge/pyproject.toml` exactly.
- A suffix makes it a **pre-release** on GitHub, automatically:
  `v0.2.0-rc.1` ships as a pre-release, `v0.2.0` as a full release.
- Both tag shapes trigger the workflow. A tag like `0.2.0` (no `v`) triggers
  nothing at all.

## Where the release notes come from

Two halves, stacked in one release body:

1. **git-cliff** (`cliff.toml`) reads commit subjects and produces the grouped
   `### Features` / `### Bug Fixes` / ... changelog. This is the same tool and
   format `dora-rs/dora` uses.
2. **GitHub** appends its own `## What's Changed` list — every merged PR with
   its title, author, and link, plus a full-changelog compare link. This half
   reads PR metadata, so it is right even when commit subjects aren't.

Grouping of the second half is configured by labels in `.github/release.yml`.
Label your PRs (`enhancement`, `bug`, `dora`, `robot`, `documentation`, `ci`)
and they sort themselves; unlabelled PRs land in "Other Changes".

## Commit messages matter

`.github/workflows/pr-title.yml` requires PR titles to be conventional
commits — `feat:`, `fix:`, `perf:`, `refactor:`, `docs:`, `test:`, `ci:`,
`build:`, `chore:`, with an optional lowercase scope like `fix(nav-base):`.

**Turn on squash-merge for this repo** (Settings → General → Pull Requests →
"Allow squash merging", with "Default to pull request title and description").
That is what puts `(#42)` into the commit subject, which `cliff.toml`'s
postprocessor then turns into a PR link in the changelog. Without squash-merge
the git-cliff half shows commit hashes only — still correct, just less useful.

Unlike dora's config, a commit that isn't conventional is **not dropped** — it
lands under `### Other`. Nothing silently disappears from a release.

## Re-running a failed release

The workflow has a `workflow_dispatch` trigger. Run it and select the release
**tag** as the ref — `check-version` refuses a branch. Re-running is safe:
`action-gh-release` updates the existing release rather than duplicating it.

## First release

There are no tags yet, so `git cliff --latest` has no prior tag to diff
against and the first release's notes will cover the entire history. That's
usually what you want for `v0.1.0`. If it isn't, edit the release body by hand
after CI publishes it.
