# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-07-24

- **`DATA` approved** (`BR-DATA-001`…`008`) — the data-plane boundary area is settled.
- **Opt-in `bench install-app` (`ADR-023`).** A concrete case (deploying a 5-app image to
  a 2-app TEST site) showed `bench migrate` does *not* install newly-added apps. Decision:
  a default deploy is code-swap + `migrate` only (never changes a site's app set — least
  surprise); `bench install-app` is a second sanctioned Frappe command, **opt-in only**,
  delivered via the target's reconcile (no SSH). Added `BR-DATA-008`; amended `ADR-014`
  ("sole automatic" + install-app) and `ADR-022`.
- **Refined `BR-DATA-006` for accuracy:** cairn does not *itself* write to volumes, but the
  stack's own `configurator`/entrypoint reconcile the volume at every `compose up`
  (`ls -1 apps > sites/apps.txt`, `bench set-config -g …`, relink `sites/assets`) — Frappe's
  machinery, not cairn.
- **Established the data-plane boundary (`ADR-022`).** cairn ships code, not data: no SQL
  connection, no `bench execute`/`frappe` code, no DB movement; altering a target DB
  directly is impossible by construction. Sole exception: `bench migrate` after an image
  swap. Volumes/site-configs/`encryption_key` are aware-but-untouched.
- **Closed `ADR-014`** — `bench migrate` is the sole sanctioned (indirect) DB interaction;
  mandatory post-deploy, opaque, non-destructive. **Closed `ADR-013`** — backup / restore
  / DB-movement are out of scope.
- **Wrote `DATA` as a boundary area** (`docs/requirements/04-data.md`, `BR-DATA-001`…`007`,
  drafted). Reframed **Pillar 3** in the project scope; **revised approved `BR-CFG-005`/
  `006`** (no two-classes action; no volume seeding — `BR-DATA-006` supersedes); dropped
  "DB snapshot" from the cairn-marker concept.

## 2026-07-23

- **`CFG` fully approved** (build config signed off). `BR-CFG-010` refined: cairn may read
  a registry token from env / a local env file to perform a *transient* `docker login`,
  but still never stores credentials.
- **Closed `ADR-009`** — cairn is registry-agnostic; **GHCR is the recommended default**
  (ERPNext/GitHub ubiquity; fits the pull-only model). Follow-up: a GHCR setup runbook is
  needed (deferred to Phase-6 user docs).
- **`CFG` target config approved; build config drafted (Pass 1).** Added
  `docs/requirements/05-config.md`. Target (`BR-CFG-001`…`007`): env config lives on the
  sites volume and is never clobbered; opacity line (Frappe framework config understood,
  app config opaque); never overwrite Frappe-managed `site_config.json`; two config
  classes (data-bound `encryption_key` must travel vs env-authority must not);
  preserve-first + additive-seed provisioning. Build config (`BR-CFG-008`…`011`, drafted):
  build-time settings live in a local file separate from the portable `cairn.toml`;
  registry-agnostic; auth delegated to `docker login`; provenance labels ride with the
  pushed image (registry = image-and-metadata store).
- **Narrowed `ADR-009`** to "recommended default registry only" (cairn is now
  registry-agnostic via build config).

## 2026-07-21

- **`BUILD` requirements approved.** `BR-BUILD-008` tag composition settled as option (b)
  — human-legible slug + input-hash (`v16-a1b2c3d4`) + moving `latest`. Marked the
  `BUILD` row **approved**.
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
