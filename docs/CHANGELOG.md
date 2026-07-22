# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-07-21

- **`BUILD` drafted (Pass 2).** `BR-BUILD-001`…`013` in `docs/requirements/02-build.md`.
  Verified bench pins by branch/tag only (no raw-SHA); adopted **Option A**
  (resolve-and-record commits, pin tags, warn on branch) — correcting the earlier
  "apps.json accepts commits" claim. Provenance is stamped as **OCI image labels**
  (not stored in the cairn tool repo); optional sidecar lives in the deployment dir.
  One item still open: `BR-BUILD-008` tag composition (pure hash vs. human-legible).
- **Closed `ADR-015`** (manifest `cairn.toml` schema + Option A app-pinning), moved to
  the closed register.
- **Added `ADR-021` (open)** — a deliberate fork of frappe_docker (MIT) as the sanctioned
  escape hatch for control unattainable while vendoring unmodified; deferred, not a
  default.
- **Manifest schema talk-through (pre-`BUILD`).** Settled: standalone `cairn.toml`
  (one file = one image, env-agnostic); `image_name`; special `[cairn.frappe]` section;
  **ordered** `[[cairn.apps]]` list = positional install order (no dependency solver);
  `[cairn.build]` knobs (`python_version`, `node_version`, `install_chromium`) +
  passthrough; no separate lockfile (marker is the record); input-deterministic (not
  hermetic) reproducibility bar. Redis/MariaDB versions are a DEPLOY concern (compose
  image tags), not image/manifest inputs. Documented the ordered-list rule prominently in
  `README.md` (required inline in every shipped template).
- **`VEND` requirements approved.** Brian signed off `BR-VEND-001`…`010` (hard-stop drift
  reasoning accepted; `ADR-020` parked open). Marked the `VEND` row **approved** in the
  requirements overview.
- **Began Phase 2 (requirements co-creation) with `VEND`.** Drafted `BR-VEND-001`…`010`
  in `docs/requirements/01-vendoring.md` (Pass 2): drift is a hard stop with no override;
  pin is immutable-intent and mechanism-agnostic; single vendored source.
- **Added `ADR-020` (open)** — strengthen upstream-pin immutability via a ventwig
  enhancement (SHA pinning and/or sync-time commit verification); non-blocking.
- **Adopted Scribe Coding** (Document-Driven AI Development) as the project methodology;
  added the ground-rules contract at `/CLAUDE.md`. Established the dual identifier
  system: `BR-<AREA>-NNN` (requirements) and `ADR-NNN` (decisions/ADRs).
- **Established the living-documentation infrastructure:** created
  `docs/requirements/` with `00-overview.md` (requirements root + ToC + conventions)
  and this `docs/CHANGELOG.md`.
- Requirements areas defined: `VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`.
  Per-area requirement documents are pending Phase-2 co-creation.
- **Renamed the decision-record prefix `D-NNN` → `ADR-NNN`** across all docs
  (`ADR-001`…`ADR-018`), for an explicit, self-describing identifier that matches
  `cofferdam-app`'s ADR convention. No IDs or numbering changed — prefix only.
- **Set the build PoC target to Frappe v16 + ERPNext + BTU** (`Datahenge/btu@version-16`),
  superseding the earlier ERPNext-only PoC now that a suitable, non-contradictory custom
  app exists. Updated the Phase-1 plan's verification target and illustrative
  `cairn.toml` manifest (the actual `cairn.toml.example` file is deferred to BUILD
  implementation, after Phase-2 `BUILD` requirements exist).
- **Added `ADR-019` — strict decoupling from cofferdam** (docker-cairn and cofferdam are
  mutually unaware). Reframed the Phase-1 plan's Pillar-3 note around a *generic*
  restore-scoping rule (never overwrite local env config on the sites volume) instead of
  cofferdam-specific enforcement; retracted the earlier `cofferdam validate` deploy
  invariant. Genericized the `CFG` area description in `CLAUDE.md` and the requirements
  overview (cofferdam now only a non-normative example).

### Predating this changelog (context)

The following were created before the changelog existed and are its baseline:
`docs/00-project-scope.md`; the decision register `docs/01-decisions-closed.md`
(`ADR-001`…`ADR-008`, `ADR-012`) and `docs/02-decisions-open.md`
(`ADR-009`…`ADR-011`, `ADR-013`…`ADR-018`); `docs/03-discussion-log.md`; and the Phase-1
build plan `docs/plans/phase-1-build.md`. Vendored upstream `frappe_docker` pinned to
`v3.2.1` via ventwig.
