# Closed Decisions

Stable IDs (`D-00N`) persist even if a decision reopens. When an open decision
closes, it moves here keeping its ID and gains a **Decided** date.

_Last updated: 2026-07-21_

---

### D-001 — Wrap `frappe_docker`, never modify it
**Decided:** 2026-07-21
Treat upstream `frappe/frappe_docker` as an untouched dependency. All new
capability is bolted on *around* it; we never fork or patch upstream files.

---

### D-002 — Target: single-host VPS with Docker Compose
**Decided:** 2026-07-21
One Docker host, `docker compose` v2. **Kubernetes and Docker Swarm are out of
scope** — no interest in that operational complexity.

---

### D-003 — CLI substrate: Python (Click/Typer)
**Decided:** 2026-07-21
Phase 1 is a Python CLI using Click or Typer, shelling out to `docker`/`buildx`/
`compose`/`bench`. Thin bash only where unavoidable. A TUI may come much later;
not Phase 1.

---

### D-004 — Image build strategy: `custom`, not `layered`
**Decided:** 2026-07-21
Use `images/custom/Containerfile` (self-contained, `FROM python:*-slim`, builds
the entire base itself), **not** `images/layered/Containerfile`.

**Rationale:** `layered` builds `FROM frappe/base:version-16` / `frappe/build:*`,
which are **mutable tags** Frappe re-pushes over time. The same docker-cairn commit
could then produce a *different* image later, and a rollback could rebuild against a
base that has changed underneath us — fatal to reproducibility/rollback. `custom`
pins Python/Node/wkhtmltopdf ourselves and is deterministic. Its only cost (slower
first build) is absorbed by the buildx layer cache, since the base stage only
rebuilds when base args change, not when apps change.

---

### D-005 — No GitHub → VPS SSH access
**Decided:** 2026-07-21
We will **not** give GitHub Actions an SSH key that can reach the VPS. Too risky:
it is an inbound credential into the box, and a CI compromise would reach the server.

---

### D-006 — Deploy trigger model: idempotent reconcile + pull loop
**Decided:** 2026-07-21
The deploy unit is a single **idempotent, state-driven verb** (`cairn reconcile` /
`cairn deploy`): read desired ref → compare to running → converge only if different;
running it twice is a no-op. Triggers are pluggable pokes at that verb.

**Default trigger:** a **pull-based loop** (systemd timer) on the VPS that reads a
desired-state pointer and converges. Reaches only *outward*; no inbound ports; self-
heals across missed events.

**Deferred:** a bespoke webhook daemon is a later luxury, not Phase 1. Because the
verb is idempotent, adding a webhook receiver later just calls the same verb.
(CI-over-SSH push is rejected per D-005.)

---

### D-007 — Vendoring via `ventwig`, committed + drift-checked
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
detection enforces "never modify it" (D-001) without gitignore-and-regenerate.
Upgrades become deliberate, reviewable acts (`ventwig sync` → diff → test).

**Config notes:** set `create_parent_package_markers = false` (we vendor the whole
`frappe_docker` root, not a Python `src/` subdir — no `__init__.py` in the Docker
build context). ventwig requires the consumer to be a git working tree → see D-008.

---

### D-008 — `docker-cairn` is itself a git repository
**Decided:** 2026-07-21
The project is version-controlled (required by ventwig, and desirable regardless).
Our scaffolding, CLI, config, and the vendored `frappe_docker` tree are all tracked.

---

### D-012 — Rollback does NOT restore the database
**Decided:** 2026-07-21
`cairn rollback` reverts the **image** (and restarts/re-points the stack) only. It
does **not** restore a DB snapshot. Image rollback and DB restore are separate,
deliberate verbs the operator composes explicitly.

**Rationale:** Production data is fast-moving; auto-restoring a SQL backup on rollback
would silently discard live transactions. Restoring SQL must be a deliberate,
manual last resort — never a side effect of flipping images.

Harm from an image/schema mismatch is bounded by Frappe/ERPNext behavior: a normal
`bench migrate` does **not** drop SQL tables or columns. So even when a rolled-back
image's DocType/DocField JSON no longer matches the live MariaDB schema, the extra
columns/tables simply sit unused rather than causing data loss — making image-only
rollback safe by default.

**Consequence:** we still snapshot **before** a forward deploy's migration (D-014) so
a manual restore is *available* if an operator chooses it — but the snapshot is never
applied automatically.

---

## First-class concepts established (design vocabulary)

These aren't standalone decisions but are settled framing the design depends on:

- **Cairn marker** — a durable deploy record binding **git ref → image tag → DB
  snapshot**, so any deployed state can be navigated back to.
- **Desired-state pointer** — the "newest stone": a small artifact CI advances that
  says which ref the VPS should converge to. CI's job ends at *build image + advance
  pointer*; the VPS's job is *converge to pointer*.
- **Trigger on _image-ready_, not on commit** — a raw commit can't deploy (no image
  yet); the real event is "a new image is built & pushed."
