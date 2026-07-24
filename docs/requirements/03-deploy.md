# BR-DEPLOY — Deploy Lifecycle Requirements

_Status: living · drafted (Pass 1 — partial; open items listed) · Last updated: 2026-07-24_

Requirements for deploying images to environments and keeping targets converged.
Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-002`, `ADR-005`, `ADR-006`,
`ADR-009`, `ADR-010`, `ADR-014`, `ADR-022`, `ADR-023`, `ADR-024`.

---

## Pull-based reconcile

**`BR-DEPLOY-001`** — The deploy model is **pull-based**. Each target runs an idempotent
`cairn reconcile` on a **systemd timer**; it converges the running stack to desired state
and is **outbound-only** (no inbound connection to the box). Running it when nothing
changed is a no-op. *(ADR-005, ADR-006)*

**`BR-DEPLOY-002`** — The **desired-state pointer** is the environment's **moving image
tag** in the registry (`:dev` / `:test` / `:staging` / `:production`). The target polls
that tag's **digest** (a cheap registry request) and converges when it changes. Immutable
input-hash tags remain the durable image identities; the env tag is the movable pointer.
*(ADR-010)*

**`BR-DEPLOY-003`** — On a detected change, `cairn reconcile` MUST: pull the image →
set `CUSTOM_IMAGE`/`CUSTOM_TAG` → `docker compose up -d` (letting frappe_docker's
`configurator`/entrypoint reconcile the volume) → run `bench migrate` → run
`bench install-app` **only if** an opt-in directive is present → verify health. cairn
performs no volume or SQL writes of its own (`BR-DATA-005`/`006`/`008`). *(ADR-014,
ADR-022, ADR-023)*

## Pointer operations (deploy / promote / rollback are one primitive)

**`BR-DEPLOY-004`** — Deploy, promote, and rollback are the **same operation**: point an
environment tag at a chosen **existing** image — **no rebuild**. cairn MUST perform this
as a **server-side retag** (no local image pull), e.g. via `docker buildx imagetools
create` (or `crane`/`skopeo`). The target converges on its next poll.
- **rollback** = repoint an env tag to a *prior* immutable tag;
- **promote** = repoint a downstream env tag (e.g. `:staging`) to whatever an upstream env
  tag (`:test`) currently points at — shipping the identical, already-tested bits.
*(ADR-010)*

## Registry introspection

**`BR-DEPLOY-005`** — cairn MUST answer, from the registry, "what images/tags exist and
what do they point at?" It MUST read image **provenance labels remotely without pulling**
(`docker buildx imagetools inspect` / `crane config`) so it can show, per tag, the
resolved digest and the baked provenance (Frappe + app commits, build time). The registry
is the image-and-metadata store; no separate marker database is required. *(BR-BUILD-011,
BR-CFG-011)*

## Garbage collection (disk safety)

**`BR-DEPLOY-006`** — A timer-driven GC pass (the reconcile timer or a companion) MUST
prune old images and stopped containers on the target, **keeping the last N images**
(configurable) for instant rollback; a pruned older image is simply re-pulled from the
registry on rollback (slower, not broken). **GC MUST NEVER touch volumes** — it MUST NOT
run `docker volume prune`, and MUST NOT run `docker system prune --volumes`. Images and
stopped containers are disposable; volumes are data (`ADR-022`). *(ADR-022)*

## Scope

**`BR-DEPLOY-007`** — cairn deploys to **existing** environments. Initial site/volume/
database creation (`bench new-site`) is the operator's responsibility, not cairn's — it
writes a DB + config, which `ADR-022` forbids cairn from doing. *(ADR-022)*

**`BR-DEPLOY-008`** — cairn's reconcile is a **purpose-built thin orchestrator** over
`docker`/`docker compose`, the registry manifest API, and `systemd` — it does NOT adopt
Watchtower, Flux, or ArgoCD. *(ADR-024)*

## Environment model (two halves, joined by the tag)

**`BR-DEPLOY-009`** — An environment is defined in **two disconnected halves joined only by
the env tag name**: a thin **control-side** (laptop) mapping of environment → registry tag
(mostly convention, e.g. `test` → `:test`), and a substantial **target-side environment
descriptor** on each target host. cairn's control-side commands operate on the **registry
only** and MUST NOT require the target host's address or any inbound access — the laptop
never talks to the environments. *(ADR-005, ADR-006, ADR-010)*

**`BR-DEPLOY-010`** — The target-side **environment descriptor** declares high-level intent:
image + watched tag; which frappe_docker **overrides** to compose (db, redis, proxy, TLS);
domain/host and ports; site name; and a **reference** to secrets (not the secrets
themselves). `cairn reconcile` MUST **render** the final compose stack from it — composing
frappe_docker's base + selected overrides and setting the env vars
(`CUSTOM_IMAGE`/`CUSTOM_TAG`/`PULL_POLICY`, …) — so the operator declares intent, not
compose YAML. The descriptor lives on the target (operator's initial setup) and MUST NOT
contain secrets (`ADR-017`). *(ADR-017)*

---

## Open within DEPLOY (to work through before approval)
- **Sequencing/health detail** — health-gating, failure handling, migrate on rollback.
- **Prod safeguards** — confirmation on prod pointer moves; `install-app`-to-prod gate.
- **Secrets/env on the target** (`ADR-017`).
- **Multi-site** (`ADR-016` — single-site assumed for now).
- **GHCR-side cleanup** — deleting old package versions is destructive (erases rollback
  targets); a *separate, opt-in* command later, never part of automatic VPS GC.
