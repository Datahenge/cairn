# cairn — Requirements Overview

_Status: living document · Last updated: 2026-08-03_

This directory is the **authoritative requirements root** for cairn, per the
Scribe Coding working agreement (`/CLAUDE.md`). Code and tests reference the
business-rule identifiers defined here; when a design changes, these documents are
updated in the same change so they remain the single source of truth.

## How to read these documents

- Each requirement is tagged **`BR-<AREA>-NNN`** and stated as an obligation using
  **MUST / MUST NOT / SHOULD / MAY** (RFC-2119 sense).
- `BR` = *requirement* ("the system MUST…"). Separate from `ADR-NNN` = *decision*
  (Architecture Decision Record, "we chose X because…") in `../01-decisions-closed.md`
  / `../02-decisions-open.md`. Requirements cite the decisions that shaped them.
- IDs are stable and never reused. A withdrawn requirement is marked withdrawn, not
  deleted, and keeps its number.

## System purpose (from `../00-project-scope.md`)

cairn wraps the vendored, read-only `frappe_docker` to make a single-VPS custom
ERPNext deployment **reproducible, immutable, and low-thought**, across two pillars —
reproducible image builds and deploy lifecycle (git ref → image tag → running stack) —
with a strict **data-plane boundary** (cairn ships code, not data).

## Two roles, one tool

cairn runs in one of two roles, detected from context rather than chosen with a flag:

- **Build/control** — runs on the developer's laptop. Builds images from a manifest,
  manages the vendored tree, and pushes tagged images to the registry. Covered by
  `VEND` and `BUILD` below.
- **Reconcile** — runs on the deployment target. Pulls images and reconciles the
  running compose stack toward the manifest's desired state; never builds. Covered
  by `DEPLOY` and `DATA` below.

This is **one package, one repo, not two programs** (`ADR-018`): both roles share the
same config models, registry logic, and compose rendering. The separation is enforced
by **credentials**, not code — a target holds only a read-only pull token, so even the
full CLI there cannot build, push, or retag. Commands that are role-aware detect their
role from context (e.g. `cairn doctor`, `ADR-028`); the common case takes no flag, per
`BR-CLI-014`'s minimal-typing goal.

## Table of contents (BR areas)

Per-area requirement documents are co-created through dialogue (Scribe Phase 2) and
added below as they are drafted.

| # | Area | File | Scope | Status |
| --- | --- | --- | --- | --- |
| 00 | — | `00-overview.md` | This index + conventions | living |
| 01 | `VEND` | `01-vendoring.md` | Vendoring upstream frappe_docker (ventwig, pin, drift) | **approved** |
| 02 | `BUILD` | `02-build.md` | Custom image build: manifest → apps.json → tagged image + marker | **approved** |
| 03 | `DEPLOY` | `03-deploy.md` | Reconcile/lifecycle: desired-state, pull loop, migration, rollback | **approved** |
| 04 | `DATA` | `04-data.md` | Data-plane **boundary** (off-limits; `migrate` auto, `install-app` opt-in) | **approved** |
| 05 | `CFG` | `05-config.md` | Configuration: target (on the sites volume) + build (local: registry, engine) | **approved** |
| 06 | `CLI` | `06-cli.md` | Command surface and UX | **approved** |
| 07 | `DOCS` | `07-docs.md` | Published documentation (GitHub Pages site) | **approved** |

## Related documents

- `/CLAUDE.md` — Scribe Coding ground-rules contract (binds the workflow).
- `../01-decisions-closed.md`, `../02-decisions-open.md` — decision register (`ADR-NNN`).
- `../03-discussion-log.md` — narrative design record.
- `../04-lessons-learned.md` — durable findings about the tools cairn builds on.
- `../CHANGELOG.md` — living-documentation revision history.
- `../plans/` — implementation plans, downstream of these requirements.
