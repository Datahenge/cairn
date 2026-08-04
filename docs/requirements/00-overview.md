---
status: authoritative
owner: requirements
purpose: Requirements index, identifiers, and reading conventions.
---

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
  (Architecture Decision Record, "we chose X because…") in `../adr/`, lighter ones in
  `../../decisions/`, and still-open ones in `../../open/OPEN_DECISIONS.md`. Requirements
  cite the decisions that shaped them.
- IDs are stable and never reused. A withdrawn requirement is marked withdrawn, not
  deleted, and keeps its number.

## System purpose (from `../00-project-scope.md`)

cairn wraps the vendored, read-only `frappe_docker` to make a single-VPS custom
ERPNext deployment **reproducible, immutable, and low-thought**, across two pillars —
reproducible image builds and deploy lifecycle (git ref → image tag → running stack) —
with a strict **data-plane boundary** (cairn ships code, not data).

## Three roles, three CLIs, one package

cairn runs in one of three roles, and — since `ADR-046`/`ADR-048` — the role is chosen by
**which binary you invoke**, not detected at runtime:

- **`cairn-build`** (build/control) — runs on the developer's laptop. Builds images from
  a manifest, manages the vendored tree, and pushes tagged images to the registry.
  Covered by `VEND` and `BUILD` below.
- **`cairn-adopt`** (target) — runs on the deployment target. Surveys an existing
  frappe_docker deployment into a descriptor (`examine`), then pulls images and
  reconciles the running compose stack toward the manifest's desired state
  (`reconcile`); never builds. Covered by `DEPLOY` and `DATA` below.
- **`cairn-registry`** (registry host) — provisions and operates a self-hosted OCI
  registry: lifecycle, introspection, retention, and garbage collection. Independent of
  the other two roles — reads no manifest and no `[cairn.declared_environments]` — and is
  sometimes colocated with a builder or target, sometimes not. Covered by `REG` below.

All three remain **one package, one repo** (`ADR-046`/`ADR-048`, superseding `ADR-018`'s
single-binary answer but not its one-package one): the entry points share config models,
registry logic, and compose rendering internally where it makes sense to, though
`cairn-registry` deliberately shares none of `config.py`/`environments.py` (`BR-REG-001`).
Role separation is enforced at two levels — which binary is installed/invoked, and, for
anything registry-side, still by **credentials** (a target's pull-only token means even
`cairn-adopt` cannot push or retag). There is no runtime role-detection (`ADR-028`
retired) and no `--role` flag on any privileged installer (folded into each CLI's own
`setup` subcommand, `BR-CLI-021`) — the common, no-flag case `BR-CLI-014` wants is the
default shape of the command surface itself.

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
| 08 | `REG` | `08-registry.md` | Registry lifecycle: provisioning, retention, garbage collection | **approved** |

## Related documents

- `/CLAUDE.md` — Scribe Coding ground-rules contract (binds the workflow).
- `../../CURRENT_CONTEXT.md` — session router; read first in a fresh session.
- `../technical/25-documentation-authority.md` — which document owns which topic, and reading order.
- `../adr/`, `../../decisions/` — decision register (`ADR-NNN`), split by consequential vs. lightweight.
- `../../open/` — live queues: open questions, pending decisions, outstanding work.
- `../discussions/discussion-log.md` — narrative design record.
- `../technical/04-lessons-learned.md` — durable findings about the tools cairn builds on.
- `../CHANGELOG.md` — living-documentation revision history.
- `../plans/` — implementation plans, downstream of these requirements.
