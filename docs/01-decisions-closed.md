# Closed Decisions

Stable IDs (`ADR-00N`) persist even if a decision reopens. When an open decision
closes, it moves here keeping its ID and gains a **Decided** date.

_Last updated: 2026-07-21_

---

### ADR-001 — Wrap `frappe_docker`, never modify it
**Decided:** 2026-07-21
Treat upstream `frappe/frappe_docker` as an untouched dependency. All new
capability is bolted on *around* it; we never fork or patch upstream files.

---

### ADR-002 — Target: single-host VPS with Docker Compose
**Decided:** 2026-07-21
One Docker host, `docker compose` v2. **Kubernetes and Docker Swarm are out of
scope** — no interest in that operational complexity.

---

### ADR-003 — CLI substrate: Python (Click/Typer)
**Decided:** 2026-07-21
Phase 1 is a Python CLI using Click or Typer, shelling out to `docker`/`buildx`/
`compose`/`bench`. Thin bash only where unavoidable. A TUI may come much later;
not Phase 1.

---

### ADR-004 — Image build strategy: `custom`, not `layered`
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

### ADR-005 — No GitHub → VPS SSH access
**Decided:** 2026-07-21
We will **not** give GitHub Actions an SSH key that can reach the VPS. Too risky:
it is an inbound credential into the box, and a CI compromise would reach the server.

---

### ADR-006 — Deploy trigger model: idempotent reconcile + pull loop
**Decided:** 2026-07-21
The deploy unit is a single **idempotent, state-driven verb** (`cairn reconcile` /
`cairn deploy`): read desired ref → compare to running → converge only if different;
running it twice is a no-op. Triggers are pluggable pokes at that verb.

**Default trigger:** a **pull-based loop** (systemd timer) on the VPS that reads a
desired-state pointer and converges. Reaches only *outward*; no inbound ports; self-
heals across missed events.

**Deferred:** a bespoke webhook daemon is a later luxury, not Phase 1. Because the
verb is idempotent, adding a webhook receiver later just calls the same verb.
(CI-over-SSH push is rejected per ADR-005.)

---

### ADR-007 — Vendoring via `ventwig`, committed + drift-checked
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

---

### ADR-008 — `docker-cairn` is itself a git repository
**Decided:** 2026-07-21
The project is version-controlled (required by ventwig, and desirable regardless).
Our scaffolding, CLI, config, and the vendored `frappe_docker` tree are all tracked.

---

### ADR-012 — Rollback does NOT restore the database
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

**Consequence:** we still snapshot **before** a forward deploy's migration (ADR-014) so
a manual restore is *available* if an operator chooses it — but the snapshot is never
applied automatically.

---

### ADR-019 — docker-cairn and cofferdam are mutually unaware (strict decoupling)
**Decided:** 2026-07-21
docker-cairn MUST NOT rely on, leverage, or have awareness of `cofferdam` /
`cofferdam-app`, and nothing in cofferdam should be aware of Docker. If cofferdam is
installed and configured, it works; otherwise it does not — that is cofferdam's own
self-contained, fail-closed contract, needing no external orchestrator. cofferdam-app,
if used, is treated as an ordinary `[[cairn.apps]]` entry with zero special-casing.

**Rationale:** Separation of concerns — docker-cairn is a build/deploy/data tool;
cofferdam is a runtime outbound guard at the Frappe app layer. Coupling would bloat
docker-cairn and amputate cofferdam's bare-metal / non-Docker audience. The tools
compose as *independent* defense-in-depth layers, not as a dependency.

**Consequence (correct-by-construction):** the one scenario that seemed to need
cofferdam-awareness — restoring a Production DB into a non-prod stack — is instead met
by a **generic** rule that names no app: *a restore replaces the database (and optionally
file attachments) and MUST NOT overwrite local environment configuration on the sites
volume.* That generic rule protects `site_config.json`, local secrets, and any local
policy files (e.g. a cofferdam `environment_policy.toml`) as a side effect, without the
tool knowing their meaning. It becomes a normative `BR-DATA-###` / `BR-CFG-###`
requirement in Phase-2. docker-cairn's restore-safety contribution stays generic (narrow
scope, environment labeling, prod→non-prod confirmation).

**Retracts:** an earlier proposal that docker-cairn enforce cofferdam policy presence /
run `cofferdam validate` as a deploy invariant — that coupling is withdrawn.

---

### ADR-015 — Manifest (`cairn.toml`) and app-pinning model
**Decided:** 2026-07-21
cairn owns a human-friendly **standalone `cairn.toml`** manifest that declares **one
image** (environment-agnostic) and compiles into the build inputs. Structure:
`[cairn] image_name`; a special `[cairn.frappe]` (`url`, `ref`) driving `FRAPPE_PATH`/
`FRAPPE_BRANCH`; an **ordered** `[[cairn.apps]]` list (`name`, `url`, `ref`) for ERPNext
+ custom apps → `apps.json`; and `[cairn.build]` version knobs + passthrough.

**App/Frappe pinning — Option A (resolve-and-record), superseding the original
"pin by commit":** verified from bench source (`bench/app.py`) that both `FRAPPE_BRANCH`
and `apps.json` clone via `git clone --branch <ref>` (no post-clone checkout; `.git` is
then stripped inside the same Containerfile `RUN`), so a **raw commit SHA is not
supported** — refs must be a branch or tag. Therefore cairn **resolves every ref to its
commit at build time (`git ls-remote`) and records it** in provenance (driving
`CACHE_BUST`, the image tag, and labels), but does **not** freeze commits into the build.
The manifest SHOULD pin to **tags** for reproducibility; cairn SHOULD warn on a moving
branch. True commit-pinning would require editing the vendored tree (forbidden,
`ADR-001`) or Option C's build-time git-mirror machinery (rejected as too heavy); the
sanctioned path if it ever becomes essential is a deliberate fork (`ADR-021`).

**Ordered list:** `[[cairn.apps]]` order is significant (install order); documented
prominently in `README.md` and MUST appear inline in every shipped template
(`BR-BUILD-003`). Requirements: `docs/requirements/02-build.md`.

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
