---
status: authoritative
owner: project
purpose: Project purpose, pillars, and what cairn is/isn't — read before requirements.
---

# cairn — Project Scope

_Last updated: 2026-08-03_

## Purpose

`cairn` wraps the upstream [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker)
tooling and bolts on the ergonomics it lacks, so that operating a custom ERPNext
deployment (Frappe + ERPNext + one or more custom apps) on a single VPS is
**frictionless, reproducible, and low-thought**.

We never modify `frappe_docker`. We vendor it read-only and build *on top* of it.

## Two pillars, and a strict boundary

1. **Reproducible custom image builds**
   Frappe + ERPNext + N custom apps → one deterministic, immutable image, from a
   single command — instead of hand-editing `apps.json`, remembering the BuildKit
   secret + `CACHE_BUST` incantation, and choosing a Containerfile.

2. **Deployment lifecycle**
   Build an image for a given git commit/tag/branch, tag it coherently, and make
   the running stack converge to the *correct current image* for that ref —
   including `bench migrate` and container restart. The hard part is keeping
   **git ref → image tag → running stack** consistent so you always know exactly
   what is deployed.

**The data-plane boundary** *(`ADR-022`).* cairn ships **code, not data**. The data plane —
SQL, persistent volumes, site configs, `encryption_key` — is **off-limits**: cairn cannot
connect to SQL, run `bench execute`/`frappe` code, or move databases between environments;
altering a target DB directly is impossible by construction. The only DB interaction is
invoking Frappe's own non-destructive `bench migrate` after an image swap — cairn never
installs a Frappe App (`ADR-037`). Rollback is **image-only**. Backup/restore/DB-movement are
out of scope — the operator's / cofferdam's domain.

The through-line: **minimal typing, minimal thinking** — a small, opinionated CLI
over the tedious, error-prone parts.

## What it is / is not

**Is:**
- A Python package, **`datahenge-cairn`**, providing two role-specific CLIs —
  `cairn-build` (build/control) and `cairn-adopt` (target) — that orchestrate `docker`,
  `buildx`, `docker compose`, and `bench` against a vendored, pinned copy of
  `frappe_docker` (`ADR-046`).
- Opinionated toward one common case: a single Docker host, done well.
- A place where the *connective tissue* upstream omits (ref↔image records,
  desired-state, drift detection) becomes first-class.

**Is not:**
- A fork or patch of `frappe_docker`. Upstream stays pristine and pinned.
- A Kubernetes / Docker Swarm orchestrator. Explicitly out of scope.
- A general-purpose multi-tenant PaaS.

## Target environment

- **Single host / VPS**, Docker Engine v23+ (BuildKit default), `docker compose` v2.
- Image family: the **`custom`** Containerfile (self-contained, from `python-slim`)
  — chosen for immutability/reproducibility. See closed decisions.
- MariaDB as the database.

## Guiding principles

- **Immutable & reproducible.** Same inputs → same image, forever. No mutable base tags.
- **Never own what we don't own.** `frappe_docker` is a pinned external dependency,
  vendored and drift-checked, never edited.
- **Idempotent, state-driven deploys.** One converging verb; triggers are pluggable.
- **Pull, don't push.** The VPS reaches outward; nothing gets a key *into* the box.
- **The Cairn metaphor.** Each build/deploy drops a durable marker (ref → resolved
  commits → image tag → digest) you can navigate back to. (Also: stones ↔ "Datahenge".)

## Naming

`cairn` — a trail marker of stacked stones. Connotes durable, followable markers
left along a path; synergizes with the "Datahenge" (stone circle) company name.
