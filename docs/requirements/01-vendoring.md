---
status: authoritative
owner: requirements
purpose: BR-VEND requirements — vendoring the upstream frappe_docker tooling.
---

# BR-VEND — Vendoring Requirements

_Status: **approved** 2026-07-21 (living — may be revised via CHANGELOG) · Last updated: 2026-08-03_

Requirements for how cairn vendors the upstream `frappe_docker` tooling. Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-001`, `ADR-004`, `ADR-007`, `ADR-008`, `ADR-020`.
Scope: `frappe_docker` is the single vendored source.

---

**`BR-VEND-001` — Vendoring mechanism.** The upstream `frappe_docker` tooling MUST be
vendored into the cairn repository as plain, committed files via `ventwig` — never as a git
submodule, subtree, or runtime package dependency. *(ADR-007)*

**`BR-VEND-002` — Immutable-intent pin.** The vendored copy MUST be pinned to an
immutable-intent upstream `ref` (a release tag) in `pyproject.toml`, and MUST NOT track a
moving branch. *(ADR-007, ADR-020)*

**`BR-VEND-003` — Lock is the anchor.** The synced upstream commit and content-tree hash
MUST be recorded in a committed `.ventwig.lock`, and mirrored into a package-relative
companion (`src/cairn/vendored/frappe_docker.pin.toml`) that build-time code reads instead
— so the anchor travels inside the wheel rather than requiring a checkout. Builds MUST
reproduce without network access to the upstream host. *(ADR-007)*

**`BR-VEND-004` — Read-only.** No cairn operation may create, modify, or delete any file
within the vendored `frappe_docker/` tree. *(ADR-001)*

**`BR-VEND-005` — Drift is a hard stop.** Before producing an image, cairn MUST verify the
vendored tree matches the content-tree hash recorded in its pin (`BR-VEND-003`). On any
drift the operation MUST abort; there is no override. This check MUST NOT require the
`ventwig` package to be installed — it is a build-time precondition, not a vendoring
operation, and recomputes the same tree-hash algorithm using only `git` (`ADR-007`).
*(ADR-001, ADR-007)*

**`BR-VEND-006` — Build-input completeness.** Before producing an image, cairn MUST verify
the vendored tree contains the required build inputs (at minimum `images/custom/Containerfile`
and the `resources/` it references), and MUST abort with a clear error if any are absent.
*(ADR-004)*

**`BR-VEND-007` — No upstream git history.** The vendored tree MUST NOT contain upstream
version-control metadata (no nested `.git`). *(ADR-007)*

**`BR-VEND-008` — No package-marker pollution.** ventwig MUST be configured with
`create_parent_package_markers = false`. *(ADR-007)*

**`BR-VEND-009` — Deliberate upgrades only.** Upgrading the vendored upstream MUST be an
explicit, reviewable act (bump `ref` → `ventwig sync` → review → commit tree + lock). cairn
MUST NOT upgrade or re-sync the pin automatically as a side effect of any other operation.
*(ADR-007, ADR-020)*

**`BR-VEND-010` — Git working tree.** The cairn project MUST be a git working tree.
*(ADR-008)*

---

## Cross-references
- `BR-VEND-005` / `BR-VEND-006` are enforced at build time; `BUILD` cites them.
- The `cairn-build vendor status | sync` command surface is specified under `BR-CLI`.
