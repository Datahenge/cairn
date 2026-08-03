---
status: authoritative
owner: technical
purpose: ADR-007 — Vendoring via `ventwig`, committed + drift-checked
---

# ADR-007 — Vendoring via `ventwig`, committed + drift-checked

**Decided:** 2026-07-21 · **Implemented:** 2026-07-21 (pinned to `v3.2.1`)
Vendor `frappe_docker` using [`ventwig`](https://github.com/brian-pond/ventwig)
(Brian's own tool): pin an upstream **release tag** in `pyproject.toml`
(`ref = "v3.2.1"`), sync into the repo as **plain committed files**, with
`.ventwig.lock` (synced commit hash + content-tree hash) enabling **drift detection**.

**Pinning nuance:** ventwig 0.2.0 clones via `git clone --depth 1 --branch <ref>`,
which accepts a branch or **tag** but not a raw commit SHA. We therefore track the
release **tag** `v3.2.1` (immutable, deterministic re-sync) rather than a moving
branch. The true immutability anchor is the **committed tree + `.ventwig.lock`**
(pinned commit `d4a310089f5d`), which holds even if GitHub is unreachable or the tag
were ever moved.

**Rationale:** Committing the pinned tree makes builds reproducible even if GitHub is
down or the SHA is later GC'd — the immutable input lives *in our repo*. Drift
detection enforces "never modify it" (ADR-001) without gitignore-and-regenerate.
Upgrades become deliberate, reviewable acts (`ventwig sync` → diff → test).

**Config notes:** set `create_parent_package_markers = false` (we vendor the whole
`frappe_docker` root, not a Python `src/` subdir — no `__init__.py` in the Docker
build context). ventwig requires the consumer to be a git working tree → see ADR-008.

**Amended 2026-07-25 — `ventwig` is fetch-time only; the tree lives inside the package.**
`local_path` moved from `frappe_docker` (repo root) to `src/cairn/vendored/frappe_docker`
— *inside* the `cairn` package itself, so it ships in the wheel via the existing
`packages = ["src/cairn"]`, no special packaging step (closes the gap `ADR-018` and
`ADR-029` recorded). `.ventwig.lock` still exists — it's ventwig's own bookkeeping,
written next to `pyproject.toml` — but cairn's runtime no longer reads it. `cairn vendor
sync` now also regenerates a companion `src/cairn/vendored/frappe_docker.pin.toml` (ref,
commit, tree hash, synced-at) from the freshly-written lock, and that file — package-
relative, shipped in the wheel — is what `BR-VEND-005`'s drift check and `BR-BUILD-011`'s
provenance labels read from then on. The drift check itself no longer shells out to the
`ventwig` CLI: it recomputes the same git tree-hash ventwig computes (a scratch `git
init`/`add -A`/`write-tree`) and compares it to the pin's `synced_tree`, needing only the
`git` binary cairn already requires unconditionally. The result: `ventwig` is a true
fetch-time-only dependency — touched by nothing except `cairn vendor sync`/`status`, run
deliberately from a checkout — exactly the role vendoring was meant to play, not a
build-time or install-time dependency.
