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
which are **mutable tags** Frappe re-pushes over time. The same cairn commit
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

### ADR-008 — `cairn` is itself a git repository
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

### ADR-019 — cairn and cofferdam are mutually unaware (strict decoupling)
**Decided:** 2026-07-21
cairn MUST NOT rely on, leverage, or have awareness of `cofferdam` /
`cofferdam-app`, and nothing in cofferdam should be aware of Docker. If cofferdam is
installed and configured, it works; otherwise it does not — that is cofferdam's own
self-contained, fail-closed contract, needing no external orchestrator. cofferdam-app,
if used, is treated as an ordinary `[[cairn.apps]]` entry with zero special-casing.

**Rationale:** Separation of concerns — cairn is a build/deploy/data tool;
cofferdam is a runtime outbound guard at the Frappe app layer. Coupling would bloat
cairn and amputate cofferdam's bare-metal / non-Docker audience. The tools
compose as *independent* defense-in-depth layers, not as a dependency.

**Consequence (correct-by-construction):** the one scenario that seemed to need
cofferdam-awareness — restoring a Production DB into a non-prod stack — is instead met
by a **generic** rule that names no app: *a restore replaces the database (and optionally
file attachments) and MUST NOT overwrite local environment configuration on the sites
volume.* That generic rule protects `site_config.json`, local secrets, and any local
policy files (e.g. a cofferdam `environment_policy.toml`) as a side effect, without the
tool knowing their meaning. It becomes a normative `BR-DATA-###` / `BR-CFG-###`
requirement in Phase-2. cairn's restore-safety contribution stays generic (narrow
scope, environment labeling, prod→non-prod confirmation).

**Retracts:** an earlier proposal that cairn enforce cofferdam policy presence /
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

### ADR-009 — Container registry: registry-agnostic; GHCR recommended default
**Decided:** 2026-07-23
cairn is **registry-agnostic** — the registry + namespace is a local build-config value
(`BR-CFG-009`), with auth delegated to `docker login` (`BR-CFG-010`), so any OCI registry
works and nothing is hardcoded to Docker Hub. The **recommended default is GHCR** (GitHub
Container Registry): ERPNext clients/developers already use GitHub heavily; GHCR's auth
fits the pull-only model (`ADR-005`/`ADR-006` — a read-only pull token for the VPS); and
it co-locates images with source.

**Follow-up:** a GHCR setup runbook is needed (PAT creation, `docker login ghcr.io`,
package visibility, VPS pull token) — Brian is only lightly familiar with GHCR. Deferred
to Phase-6 user documentation.

---

### ADR-022 — cairn operates on the code/image plane; the data plane is off-limits
**Decided:** 2026-07-24
cairn's responsibility is **shipping code** — building immutable images (apps + commits)
and deploying them to environments. The **data plane is off-limits**: cairn MUST NOT
connect to any SQL database, MUST NOT run `bench execute` or any `frappe` library code,
and MUST NOT export, import, restore, or move SQL data between environments. **Moving a
database between environments is out of scope** — that is cofferdam's / the operator's
domain, not cairn's.

**Prime Directive:** cairn MUST NOT *directly* alter any target database, and this must be
**impossible by construction** — no code path, no SQL client, no data-manipulation
capability exists in cairn. This holds for **all** environments; Production is not
special-cased because the capability simply does not exist.

**The sanctioned exceptions** are invoking Frappe's own `bench migrate` (automatic,
`ADR-014`) and, **opt-in only**, `bench install-app` (`ADR-023`) — cairn is a *caller*,
not a mutator: "cairn doesn't alter SQL; Frappe does."

**Feature 3 corollary — volumes/configs untouched:** cairn is *aware* that persistent
Docker volumes, `site_config.json`, and `encryption_key` exist, solely so it **never
touches them**. It MUST NOT read, write, seed, provision, or migrate them; an image swap
leaves the data-plane volume entirely intact.

**Rationale:** the safest data-handling code is no data-handling code. A tool that
*cannot* touch data can't be misused, social-engineered, or bugged into touching it —
defense by architecture, not by prompt. This also sharpens cairn's identity (a build +
deploy tool) and is `ADR-019` taken to its logical end (the whole data domain is
cofferdam's/the operator's).

Requirements: `docs/requirements/04-data.md`.

---

### ADR-013 — Backup / restore / DB movement: OUT OF SCOPE
**Decided:** 2026-07-24 (was: backup storage/retention/restic)
Backup, restore, and database movement are **out of scope** for cairn per `ADR-022`.
cairn does not create, store, retain, encrypt, restore, or relocate SQL backups. Any such
work belongs to the operator or to cofferdam. (Frappe's own `bench backup`/`restore`
remain available to operators independently of cairn.)

---

### ADR-014 — `bench migrate` is the sole sanctioned DB interaction
**Decided:** 2026-07-24
After enabling a new image + containers on a target environment, cairn **MUST** run
`bench migrate` in a subprocess. This is the sole **automatic** DB interaction; the only
other sanctioned interaction is **opt-in** `bench install-app` (`ADR-023`). Both are
*indirect* — Frappe performs the work.

**Why it is required and safe:**
1. **Required** — Frappe demands it after any app change; skipping it leaves code assuming
   a schema that doesn't exist (a *worse*, broken state).
2. **Sanctioned** — it is a normal Frappe command runnable anytime from a terminal; *what*
   it does and *how* are Frappe's business, not cairn's. cairn's only job is to call it.
3. **Non-destructive** — `bench migrate` never drops columns, tables, or indexes (dropping
   requires explicit opt-in). It creates new SQL objects and leaves the rest intact, so it
   is safe to run in Production. Patches run because Frappe says they should.

cairn treats `bench migrate` as opaque: it invokes it and observes success/failure, but
never inspects or influences what it does. Sequencing (incl. on rollback) is a `DEPLOY`
concern. Supersedes the earlier "orchestrate with pre-migrate snapshot" lean (no snapshot
— that would be data handling, forbidden by `ADR-022`).

---

### ADR-023 — Opt-in `bench install-app`; never automatic
**Decided:** 2026-07-24
Adding an app that is present in the image but not yet installed on a target **site**
requires `bench install-app` — which `bench migrate` does not do (migrate only patches
already-installed apps). To let an operator activate such apps **without SSHing into the
box**, cairn provides an **explicit opt-in** path to run `bench install-app <apps>` on the
target.

**Rules:**
- It MUST **never** run automatically. A default deploy is code-swap + `migrate` only and
  MUST NOT change a site's installed-app set (least surprise — Brian's directive).
- Like `migrate`, `install-app` is a sanctioned Frappe command cairn invokes **opaquely**
  (Frappe does the work; the "how" is none of cairn's business).
- The opt-in is delivered through the target's own reconcile/one-shot tooling (not the
  laptop reaching in), preserving the pull model (`ADR-005`/`ADR-006`). The exact delivery
  mechanism and any prod-specific confirmation are `DEPLOY` concerns.

**Motivating case:** deploying a 5-app image (frappe, erpnext, btu, life_scientific,
life_scientific_migration) to a TEST site that currently has only frappe + erpnext
installed — the three new apps' *code* ships in the image and `apps.txt` updates, but they
remain inert until `install-app` runs.

---

### ADR-010 — Desired-state pointer = the environment's moving registry tag
**Decided:** 2026-07-24
The desired-state pointer is the environment's **moving image tag** in the registry
(`:dev`/`:test`/`:staging`/`:production`). The target's `cairn reconcile` **polls the tag's
digest** (outbound, cheap) and converges when it changes; nothing is pushed into the box.
The laptop advances the pointer by a **server-side retag** (no image pull) — the registry
is the bulletin board both sides touch outbound. Immutable input-hash tags are the durable
identities; the env tag is the movable pointer. Rollback/promote = repoint the tag
(`BR-DEPLOY-004`).

**Why (vs a git state-repo or object/file):** reuses GHCR (no extra infra or inbound),
fits "the registry is the image-and-metadata store" (`BR-CFG-011`), and keeps everything
outbound-only (`ADR-005`/`ADR-006`). Cost: convergence latency = the poll interval;
sub-minute pushes remain the deferred option from `ADR-006`.

---

### ADR-024 — Reconcile is a purpose-built thin orchestrator (not Watchtower/Flux/Argo)
**Decided:** 2026-07-24
cairn's `reconcile` is built as thin glue over primitives we already stand on:
`docker`/`docker compose`, the **registry manifest API** (the digest poll — ~10 lines),
and **systemd timers**. cairn does **not** adopt an off-the-shelf updater.

**Evaluated and rejected:**
- **Flux / ArgoCD** — Kubernetes-native GitOps controllers; adopting them means adopting
  k8s, rejected by `ADR-002` (single-host Compose).
- **Watchtower** — solves only the trivial part (poll a tag's digest, pull, recreate a
  container) and *fights* the valuable part: it is **per-container**, not per-stack, so a
  post-update `bench migrate` hook would fire once per service (5×) with no coordination;
  it recreates containers outside `docker compose`'s knowledge; and it has no concept of
  environments, `CUSTOM_IMAGE`/`CUSTOM_TAG` composition, `install-app` opt-in, or
  health-gated sequencing.

The polling *pattern* is proven (Watchtower's existence), but the digit-check is trivial
to implement, and the **single-host Frappe orchestration** (pull → `compose up` → `migrate`
once → optional `install-app` → health → rollback-by-repoint) has no off-the-shelf
solution — it is precisely the connective tissue cairn exists to provide.

---

### ADR-016 — Single site per environment; multi-site deferred
**Decided:** 2026-07-24
Each environment runs **one site** (the environment descriptor names one site;
`FRAPPE_SITE_NAME_HEADER` resolves to it). Multi-site on one bench is **deferred** — not a
Phase-1 concern; revisit if a real need arises. *(BR-DEPLOY-014)*

---

### ADR-017 — Secrets are operator-provisioned; cairn is secret-agnostic
**Decided:** 2026-07-24
cairn MUST NOT store, generate, persist, prompt for, or handle secret **values** — it only
**references and wires** secrets the operator provisions. Registry pull auth on a target is
delegated to Docker's credential store (`docker login ghcr.io` / read-only pull token, set
at provisioning), mirroring the build side (`BR-CFG-010`). DB/app secrets are
operator-provisioned and wired by cairn via the mechanism the environment descriptor
names: **Docker secrets** (`overrides/compose.mariadb-secrets.yaml`) **recommended** (esp.
Production), with plain **`.env`** supported for simple/dev setups. Site-level secrets
(`site_config.json`) remain off-limits (`ADR-022`/`BR-DATA-006`). *(BR-DEPLOY-011..013)*

---

### ADR-011 — Image tagging scheme (settled by `BR-BUILD-008`)
**Decided:** 2026-07-24
Settled by `BR-BUILD-008`: an immutable primary tag `<legible>-<inputhash>` (legible Frappe
slug + input hash) plus the moving environment tags (`:dev`/`:test`/`:staging`/
`:production`) that serve as desired-state pointers (`ADR-010`). No separate decision
remains. *(BR-BUILD-008, ADR-010)*

---

### ADR-025 — Deploy failure = halt + report; rollback stays manual
**Decided:** 2026-07-24
On a failed deploy (`migrate` error, or health failure/timeout after the swap), cairn
**halts and reports**; it does **not** auto-rollback. Rollback remains a deliberate,
one-command pointer move (`ADR-012`).
**Rationale:** least surprise — cairn never autonomously changes what's deployed; an
auto-rollback would be cairn making a deploy decision on its own and could mask/flap over a
real fault. Cost: a failed environment may be degraded until the operator acts, but rollback
is fast. *(BR-DEPLOY-018)*

---

### ADR-026 — Observability: stdout/stderr + optional failure webhook; host owns monitoring
**Decided:** 2026-07-24
cairn (especially the remote reconcile) logs **only to stdout/stderr** — never custom log
files. On a target the systemd timer routes output to journald; the **host's owners** own
professional monitoring/alerting/logging. cairn does not reinvent logging. Additionally,
cairn MAY POST to an **optional, operator-configured failure webhook** — a best-effort,
outbound, transport-agnostic POST with a structured payload — so a tech team learns of
failures without writing a journald-parsing cron, while cairn owns none of the delivery
(SMTP/Slack/PagerDuty is the endpoint's job). *(BR-DEPLOY-019/020)*

---

### ADR-018 — One package `datahenge-cairn`; command `cairn`; split deferred
**Decided:** 2026-07-24
**Single package, one repo.** cairn's two roles (build/control on the laptop; reconcile on
targets) are modes of one cohesive tool that shares config models, registry logic, and
compose rendering — not two programs. The role separation is enforced by **credentials** (a
target holds only a read-only pull token, so even the full CLI there cannot build/push/
retag), not by splitting code or dependencies (the Python footprint is tiny and identical;
build heaviness lives in external `docker`/`buildx` binaries).

**Names:**
- **PyPI distribution + repo:** `datahenge-cairn`. `cairn` is taken; `docker-cairn` /
  `frappe-cairn` would falsely imply Docker/Frappe ownership. `datahenge-cairn` truthfully
  signals Datahenge and doubles the stone motif (Datahenge = stone circle, cairn = stacked
  stones).
- **Import package:** `cairn`. **Console command:** `cairn` (primary) + a `datahenge-cairn`
  alias as a collision fallback.

**Distribution:** a pip-installable wheel; on a target, `cairn reconcile` runs under a
systemd service + timer (`BR-DEPLOY-001`).

**Split deferred (trigger recorded):** revisit a separate minimal agent only if a genuinely
heavy *build-only* dependency appears, or a hard requirement emerges that target code be
*physically incapable* of build/push logic (beyond credential-gating). Neither holds today.
*(BR-DEPLOY-001)*

---

## First-class concepts established (design vocabulary)

These aren't standalone decisions but are settled framing the design depends on:

- **Cairn marker** — a durable record binding **git ref → resolved commits → image tag
  → digest** (provenance), so any built/deployed image can be identified and navigated
  back to. *(No DB snapshot — the data plane is off-limits, `ADR-022`.)*
- **Desired-state pointer** — the "newest stone": a small artifact CI advances that
  says which ref the VPS should converge to. CI's job ends at *build image + advance
  pointer*; the VPS's job is *converge to pointer*.
- **Trigger on _image-ready_, not on commit** — a raw commit can't deploy (no image
  yet); the real event is "a new image is built & pushed."
