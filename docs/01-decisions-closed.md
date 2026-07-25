# Closed Decisions

Stable IDs (`ADR-00N`) persist even if a decision reopens. When an open decision
closes, it moves here keeping its ID and gains a **Decided** date.

_Last updated: 2026-07-25_

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

**Amended 2026-07-24 (`ADR-027`):** the *build* engine is pluggable — `docker build` or
`podman build`, selected per build machine. `compose`/`bench` remain Docker-side on the
target, unchanged.

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

**Superseded in part by `ADR-022`:** an earlier version of this consequence had cairn
snapshot before a forward migration. `ADR-022` (data-plane boundary) removed that — cairn
performs **no** snapshot or any data handling. The core decision (rollback reverts the image
only, never the database) stands, and is stronger under `ADR-022`.

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
requirement in Phase-2.

**Superseded in part by `ADR-022`:** this consequence assumed cairn might perform restores.
Under `ADR-022`, cairn performs **no** restore or data movement at all, so the generic
restore rule is moot as a cairn *feature* — its never-clobber-config principle survives only
as `BR-CFG`/`BR-DATA` prohibitions. The decoupling decision itself stands unchanged.

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

**Amended 2026-07-25 (`ADR-031`):** as written, this was absolute — no log files, ever —
and that over-reached. Its rationale is *"something else already owns the record"*
(journald on a target), which is true for the daemon and for CI, but false for a human at
a keyboard. `ADR-031` splits the three contexts and permits a **build transcript** in
attended CLI use only. The rule above stands unchanged for `reconcile` and for every
unattended invocation.

---

### ADR-027 — Build engine is pluggable (`docker` | `podman`); deploy engine stays Docker
**Decided:** 2026-07-24
The build machine and the target are **different machines** (`ADR-018` already splits the
roles), and the artifact that crosses between them is an **OCI image in a registry** — not
a build engine. buildah produces OCI images; Docker 23+ consumes them. So the build engine
is a property of the build machine only.

**Decision:** `BUILD` may use `docker build` **or** `podman build`, auto-detected (prefer
`docker` when present, else `podman`) and overridable via `engine =` in **local build
config** (`ADR-015`, `BR-CFG-008`) — never in the portable `cairn.toml`, which must stay
free of build-machine settings. `DEPLOY` is **unchanged**: Docker + Docker Compose on the
target, per `ADR-002`. `BR-DEPLOY-005` already reads provenance over the **registry
manifest API** (HTTP), so introspection is engine-independent.

**Rationale:** the author's build machine runs rootless, daemonless podman. Installing
`dockerd` beside it puts a second engine on the host managing its own nftables chains
(`DOCKER`, `DOCKER-USER`, `DOCKER-FORWARD`) and rewriting the `FORWARD` policy — a real,
recurring cost on a machine that only *builds* and needs none of Docker's networking. The
client's TEST VPS ships Docker, and `DEPLOY` is untouched by this decision.

**Evidence (measured 2026-07-24, podman 5.4.2 / buildah 1.39.3):** the secret mount at
`Containerfile:128` works with `uid=`/`gid=` honoured (mode `0400`, owned `1000:1000`);
the secret leaks into neither the filesystem nor image history; `CACHE_BUST` keys the
layer cache in both directions. Full result in `04-lessons-learned.md` §4.

**Engine floors:** Docker Engine **v23+** (BuildKit is the default builder from 23.0).
Podman **v4.0+** — the documented floor for `--mount=type=secret`; only 5.4.2 is measured,
so the floor is conservative-by-documentation rather than by test.

**Accepted risks, to confirm against a real registry:** buildah defaults to OCI manifest
format where Docker historically preferred v2s2 (`--format docker` is the fallback); and
provenance **labels** must read back identically via `docker inspect .Config.Labels`
regardless of which engine stamped them — load-bearing for `retag`/rollback. Also assumes
build-host architecture matches the target (both amd64 today).

**Amended 2026-07-25 — the engines are equivalent in *output*, not in *residue*.** This
decision rests on the artifact crossing between machines being an OCI image, which remains
true. But the two engines leave different things behind on the build machine, and one
behaviour cannot be written for both:

| | podman / buildah | docker / BuildKit |
| --- | --- | --- |
| Build cache lives as | **untagged images** in local storage | a separate cache store |
| Multi-stage `builder` stage | exists as an image (measured: 4.63 GB) | does not exist as an image |
| Naming it with `--target` | free — tags what is already there | **materializes** several GB |

So `BR-BUILD-015` (naming the cache stage so an administrator does not delete it) is
**podman-only** — not a preference but a correctness constraint: doing it under Docker would
create the very disk consumption it exists to protect. `BR-CLI-018`'s label-scoped prune is
unaffected and remains engine-neutral, because it works from cairn's own labels rather than
from anything the engine leaves behind.

The general rule this establishes: **behaviour that touches an engine's local storage must
be decided per engine; behaviour that touches the image must not.** *(BR-BUILD-015,
lessons §12)*
*(BR-CLI-007, BR-BUILD-006/011/012, BR-CFG-008/010; amends `ADR-003`)*

---

### ADR-028 — `cairn doctor` is role-aware, detected from context
**Decided:** 2026-07-24
`ADR-018` establishes that one package serves two roles — build/control on the laptop,
`reconcile` on targets. A single fixed preflight therefore reports irrelevant failures:
a target has no vendored tree and no build engine; a build machine has no compose stack.

**Decision:** `cairn doctor` **detects its role from context** and checks accordingly —
build/control (build engine, vendored-tree integrity, config) versus target (Docker +
Compose, systemd, registry reachability). No flag in the common case, per `BR-CLI-014`'s
minimal-typing goal. The target-role branch lands with `DEPLOY`.
*(BR-CLI-007, BR-CLI-014, ADR-018, ADR-027)*

---

### ADR-029 — The manifest root and cairn's own project root are independent
**Decided:** 2026-07-24
`cairn.toml` describes a **deployment**; cairn's project root (the `pyproject.toml`
carrying `[tool.ventwig]`, and the vendored `frappe_docker/` beside it) describes the
**tool**. `BR-BUILD-011` already separates them — markers may go to the "deployment
working directory" but never into cairn's "own installation or source tree".

**Decision:** the two are resolved by independent searches. The manifest is `--manifest`
if given, else the nearest `cairn.toml` walking **up from the working directory**. The
vendored tree stays anchored to cairn's own root. They coincide today (development from
the repo) and stop coinciding the moment cairn is `pip install`-ed and run against a
deployment directory elsewhere — which requires no code change under this decision.

**Build config layers** in the same spirit: `~/.config/cairn/config.toml` holds
machine-wide defaults (e.g. `engine`, `ADR-027`), and an optional `cairn.local.toml`
**beside the manifest** overrides it key-by-key, so per-deployment settings travel with
the deployment while the portable `cairn.toml` stays free of them (`BR-CFG-008`).

**Known gap, deferred:** the wheel currently packages only `src/cairn`, so a
`pip install`-ed cairn has no vendored tree to build from. Packaging `frappe_docker/`
into the distribution is a `BUILD`-phase concern, not blocked by this decision.
*(BR-CFG-012, BR-CLI-014, BR-BUILD-011)*

---

### ADR-030 — Provenance label schema: `com.datahenge.cairn.*` + standard OCI keys
**Decided:** 2026-07-24
`BR-BUILD-011` says *what* provenance to stamp but not under which keys. The keys are an
interface, not a detail: `BR-DEPLOY-005` reads them remotely, and `retag`/rollback depend
on them. Renaming them after images are published means older images become unreadable to
`cairn images`, so this is settled before the first push.

**What the sources actually say.** The OCI image-spec is terse: keys **SHOULD** use
reverse domain notation, `org.opencontainers` is reserved, "Consumers MUST NOT generate an
error if they encounter an unknown annotation key" — and it gives **no rationale** and
**no ownership rule**. Both of those live in Docker's label documentation instead:
"Authors of third-party tools should prefix each label key with the reverse DNS notation
of a domain **they own**"; "**Don't use a domain in your label key without the domain
owner's permission**"; the purpose being to "prevent inadvertent duplication of labels
across objects, especially if you plan to use labels as a mechanism for automation."

**Decision:** cairn-specific keys use **`com.datahenge.cairn.*`** — the only reverse-DNS
namespace the author is entitled to use. `io.cairn` / `dev.cairn` were **rejected**: they
are real domains owned by others, which the ownership norm forbids. Bare `cairn.*` was
considered — it claims nothing and the spec tolerates it — but forfeits exactly the
collision protection the convention exists for, and cairn *does* key behavior off these
labels.

**The business name is not branding here.** Toolchain provenance labels are routine: an
image built through podman already carries `io.buildah.version` (Buildah owns
`buildah.io`). cairn deliberately does **not** set `org.opencontainers.image.vendor` — the
distributing entity of a client's image is the client's to declare, not cairn's.

**Schema.** Standard keys where one already fits; cairn's namespace for the rest:

| Key | Value |
| --- | --- |
| `org.opencontainers.image.created` | RFC 3339 build timestamp |
| `org.opencontainers.image.title` | manifest `image_name` |
| `org.opencontainers.image.version` | the immutable primary tag |
| `org.opencontainers.image.revision` | resolved Frappe commit |
| `com.datahenge.cairn.version` | the cairn that built it |
| `com.datahenge.cairn.input-hash` | `BR-BUILD-008` input hash |
| `com.datahenge.cairn.tag.primary` / `.tag.moving` | both applied tags |
| `com.datahenge.cairn.frappe.url` / `.ref` / `.commit` | Frappe source, declared ref, resolved commit |
| `com.datahenge.cairn.apps` | JSON array of `{name, url, ref, commit}`, **manifest order** |
| `com.datahenge.cairn.build-args` | JSON object of **effective** build args (`BR-BUILD-010`) |
| `com.datahenge.cairn.frappe-docker.ref` / `.commit` | the vendored upstream pin, from `.ventwig.lock` |

Apps and build args are single JSON labels because their cardinality varies; everything
else is scalar so it can be read without parsing.

**Rejected: a per-deployment namespace** (`com.microsoft.cairn.*` for a client Microsoft,
`shop.foobarbaz.cairn.*` for foobarbaz.shop). Attractive, because it keeps the builder's
name off a client's image — but it breaks on the fact that **cairn reads these labels, it
does not merely write them**:

- A configurable prefix must be known to the *reader*. `cairn images` reads provenance
  remotely (`BR-DEPLOY-005`) and `reconcile` runs on a target that has an environment
  descriptor, **not** the build manifest — so the target cannot know which prefix its own
  images used.
- The bootstrap does not close: discovering a configured namespace from the image requires
  a **fixed** key to look it up under. Configurability therefore buys an alias, never an
  escape from having one fixed namespace.
- A typo is silent. `com.microsft.cairn.apps` is a perfectly valid label; nothing
  validates it, and the failure surfaces much later as absent provenance — at rollback,
  which is the worst moment to discover it.
- It misattributes the schema. A namespace says *who defines these keys' meaning*, not who
  owns the image. Microsoft does not define `.input-hash`; cairn does.

The legitimate need underneath — recording **whose** image this is — is what the standard
OCI fields exist for: `org.opencontainers.image.vendor`, `.title`, `.url`. If a client
engagement ever calls for it, the answer is to make *those* settable per deployment, never
to make cairn's own key namespace variable. Not built now (no such need yet); recorded so
the option is not re-litigated from scratch.

Note the blast radius is narrower than it first appears: a wrong namespace does not make
an image or container **incompatible** — the image builds, pushes, pulls, and runs
normally. What breaks is cairn's own introspection, promotion, and rollback.
*(BR-BUILD-008/010/011, BR-DEPLOY-005)*

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

### ADR-031 — Three execution contexts; a build transcript only when nobody else owns the record
**Decided:** 2026-07-25
`ADR-026` forbade custom log files outright. Brian's first real `cairn build` showed the
cost: minutes of engine output in a terminal emulator, unscrollable, and gone forever on
a stray `clear` unless he had thought to `tee` it. The fix is not to weaken the rule but
to notice that "target vs. not" was the wrong axis. There are **three** contexts, and the
question that separates them is **does something else already own and retain the record?**

| Context | Owner of the record | Behavior |
| --- | --- | --- |
| Target daemon (systemd unit/timer) | journald | stdout/stderr only |
| Unattended CLI (CI — e.g. GitHub Actions) | the CI system's log viewer | stdout/stderr only |
| **Attended CLI** (human at a terminal) | **nobody** | terminal **and** a transcript file |

The CI row is the one that proves the principle. A GitHub Actions runner *does* have a
writable filesystem, so "we cannot write" would be a false rationale. The real reason is
that the runner is ephemeral — a file evaporates at job end unless explicitly uploaded —
while Actions already provides search, permalinks and retention over the captured stream.
A transcript there is redundant at best, and an uncollected file at worst.

Consequences:
- **One test resolves all three.** Neither journald nor a CI runner allocates a TTY, so a
  single `isatty()` check on stderr lands correctly in every context. Explicit
  `--transcript <path>` / `--no-transcript` remain, for when the proxy is wrong (a piped
  attended run, `script`, or a CI job that genuinely wants an artifact to upload).
- **Attended builds force `--progress=plain`.** BuildKit's default TTY display redraws
  lines in place with ANSI escapes — which is *why* scrollback was useless, and would
  make a teed file unreadable. Plain progress is append-only. Nothing changes in the
  other two contexts: BuildKit already defaults to plain with no TTY.
- **Transcripts are disposable diagnostics, not project artifacts.** They default under
  `/tmp/cairn-<uid>/` — self-cleaning, and outside any source tree, consistent with
  `BR-BUILD-011`'s refusal to write markers into cairn's own tree. A `last-build.log`
  symlink and printing the path at **both** start and end solve discoverability without
  requiring anyone to memorise a path; printing at the start also means the path survives
  a Ctrl-C or a lost terminal. `transcript_dir` in build config (`BR-CFG-008`) buys
  durability for anyone who wants history beyond a reboot.

*(BR-CLI-016, BR-CLI-017, BR-CFG-008, BR-DEPLOY-019, amends ADR-026)*

---

### ADR-032 — One image per input hash; prune only what cairn labelled
**Decided:** 2026-07-25
Four consecutive `cairn build` runs against an unchanged manifest produced four different
image IDs, five nameless multi-gigabyte images, and roughly 14 GB of orphans — while the
primary tag never changed. Three symptoms, one cause, and the diagnosis turned on
separating two things the docs had been treating as one.

**Declared inputs** are what `cairn.toml` says (`version-16`); **resolved inputs** are the
commits those symbols pointed at. Image content is a function of the *resolved* inputs
alone. That collapses the whole matrix of confusing cases: identical declared inputs can
yield different images (a branch moved between two builds), and different declared inputs
can yield identical images (a branch and a tag naming one commit). `BR-BUILD-005`'s
resolve-and-record is therefore load-bearing, not a convenience.

But the mapping is **one-to-many in the other direction too**: identical resolved inputs
still yield different *digests*, because the image config carries a build-time clock. No
amount of hashing fixes that — it has to be decided.

Decided: **cairn does not rebuild an input hash it already holds.** An existing primary tag
proves the inputs are unchanged; rebuilding can only mint a second digest, move the tag onto
it, and orphan the first. Refusing is what makes a deterministic *name* behave like one.
`--rebuild` overrides for a suspected-corrupt image. *(BR-BUILD-014)*

Also decided, and the sharper half:
- **"Immutable primary tag" was the wrong words** and caused the wrong inference. Corrected
  to **deterministic** throughout, with the three tiers — address (digest, immutable),
  deterministic name (cairn's tag, re-pointable), moving pointer (`latest`) — stated in
  `BR-BUILD-008` so the distinction survives this conversation.
- **Prune scopes by cairn's labels, never by danglingness.** Brian observed that clearing
  dangling images made the next build enormously slower: on podman an untagged image may be
  a build-cache **stage**, not a former build. cairn's `--label`s land only at the final
  commit, so a stage image never carries them, and a label-scoped prune is structurally
  incapable of eating the cache. The safety property and the performance property turn out
  to be the same property. *(BR-CLI-018, lessons §12)*
- **The engine's own image listing cannot answer "why does this exist"** — it knows
  repository, tag, id, age, size. Every fact needed is already stamped on the image by
  `BR-BUILD-011`; `cairn images --local` reads them back and groups by input hash, making
  supersession visible rather than inferred. *(BR-CLI-005)*

**Deferred, not decided:** whether the tag's `<legible>` half should keep deriving from the
*declared* Frappe ref. It currently does, which means one commit reached by a branch and by
a tag yields two tag names for one image, and taking `BR-BUILD-005`'s own advice to pin to
tags renames every image for no change in content. Options are on the table (declare a
series in the manifest; read the version at the resolved commit; drop the half). Open.

*(BR-BUILD-008, BR-BUILD-014, BR-CLI-005, BR-CLI-018, ADR-011, ADR-015)*

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
