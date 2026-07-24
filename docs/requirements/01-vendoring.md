# BR-VEND — Vendoring Requirements

_Status: **approved** 2026-07-21 (living — may be revised via CHANGELOG) · Last updated: 2026-07-21_

Requirements for how cairn vendors the upstream `frappe_docker` tooling.
Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-001`, `ADR-004`, `ADR-007`,
`ADR-008`, `ADR-020`.

**Scope note:** `frappe_docker` is the **single** vendored source; additional ventwig
sources are not anticipated. If one is ever introduced, these requirements generalize.

---

**`BR-VEND-001` — Vendoring mechanism.**
The upstream `frappe_docker` tooling MUST be vendored into the cairn repository as
plain, committed files via `ventwig` — never as a git submodule, subtree, or runtime
package dependency. *(ADR-007)*

**`BR-VEND-002` — Immutable-intent pin.**
The vendored copy MUST be pinned to an immutable-intent upstream ref, recorded as the
ventwig source `ref` in `pyproject.toml`. It MUST NOT track a moving branch. Under
ventwig 0.2.0 this is a **release tag**; pinning by immutable commit SHA is tracked in
`ADR-020`. *(ADR-007, ADR-020)*

**`BR-VEND-003` — The lock is the anchor.**
The synced upstream commit and content-tree hash MUST be recorded in a committed
`.ventwig.lock`. The committed tree + lock — **not** the ref — is the authoritative
immutability anchor, and MUST permit builds to reproduce **without network access** to
the upstream host. *(ADR-007)*

**`BR-VEND-004` — Read-only.**
No cairn operation may create, modify, or delete any file within the vendored
`frappe_docker/` tree. *(ADR-001)*

**`BR-VEND-005` — Drift is a hard stop.**
Before producing an image, cairn MUST verify the vendored tree matches the
content-tree hash in `.ventwig.lock`. On any drift the operation MUST abort. **There is
no override.** The remedy is to restore the tree (`ventwig sync`) or to record a
deliberate upgrade (`BR-VEND-009`); intentional edits to the vendored tree are prohibited
by `BR-VEND-004`. *(ADR-001, ADR-007)*

**`BR-VEND-006` — Build-input completeness.**
Before producing an image, cairn MUST verify the vendored tree contains the
required build inputs — at minimum `images/custom/Containerfile` and the `resources/` it
references — and MUST abort with a clear error if any are absent. *(ADR-004)*

**`BR-VEND-007` — No upstream git history.**
The vendored tree MUST NOT contain upstream version-control metadata (no nested `.git`).
*(ADR-007)*

**`BR-VEND-008` — No package-marker pollution.**
ventwig MUST be configured with `create_parent_package_markers = false`, so that no
`__init__.py` files are injected into the vendored Docker build context. *(ADR-007)*

**`BR-VEND-009` — Deliberate upgrades only.**
Upgrading the vendored upstream MUST be an explicit, reviewable act (bump `ref` →
`ventwig sync` → review diff → commit the updated tree + lock). cairn MUST NOT
upgrade or re-sync the pin automatically as a side effect of any other operation. Where
ventwig supports it (`ADR-020`), sync SHOULD verify the ref still resolves to a reviewed
commit. *(ADR-007, ADR-020)*

**`BR-VEND-010` — Git working tree prerequisite.**
The cairn project MUST be a git working tree (required for ventwig-managed
vendoring and drift detection). *(ADR-008)*

---

## Cross-references

- `BR-VEND-005` and `BR-VEND-006` are **checked at build time**; the `BUILD` requirements
  cite them rather than restating them.
- The `cairn vendor status` / `cairn vendor sync` command surface is specified under
  `BR-CLI` (it wraps ventwig); those commands enforce the obligations above.
