# BR-DEPLOY — Deploy Lifecycle Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-07-26_

Requirements for deploying images to environments and keeping targets converged.
Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-005`, `ADR-006`, `ADR-010`, `ADR-012`,
`ADR-014`, `ADR-016`, `ADR-017`, `ADR-022`, `ADR-023`, `ADR-024`, `ADR-025`, `ADR-026`,
`ADR-042`, `ADR-043`.

---

## Pull-based reconcile

**`BR-DEPLOY-001`** — The deploy model is **pull-based**: each target runs an idempotent
`cairn reconcile` on a **systemd timer**, converging the running stack to desired state,
**outbound-only** (no inbound connection to the box). A no-change run is a no-op.
*(ADR-005, ADR-006)*

**`BR-DEPLOY-002`** — The **desired-state pointer** is the environment's **moving image tag**
in the registry (`:dev`/`:test`/`:staging`/`:production`). The target polls that tag's
**digest** and converges when it changes. *(ADR-010)*

**`BR-DEPLOY-003`** — On a detected change, `cairn reconcile` MUST: pull the image → set
`CUSTOM_IMAGE`/`CUSTOM_TAG` → `docker compose up -d` → run `bench migrate` → verify health.
cairn performs no volume or SQL writes of its own (`BR-DATA-005`/`006`/`008`).
*(ADR-014, ADR-023)*

**`BR-DEPLOY-003a`** *(cairn never installs an app)* — `cairn reconcile` MUST NOT run
`bench install-app`, under any flag or directive. Installing an app is the **operator's**
act, exactly as site creation is (`BR-DEPLOY-007`). An earlier draft of `BR-DEPLOY-003`
permitted it behind an opt-in directive; that clause was **struck** 2026-07-25 (`ADR-037`).

Three reasons, of which the first is structural:

1. **A convergence loop cannot host a one-shot mutation.** `reconcile` exists to make actual
   state match desired state, repeatedly and idempotently. `install-app` is irreversible and
   must happen exactly once, which would require cairn to remember whether it already had —
   durable state cairn deliberately does not keep (`BR-DEPLOY-019`, `ADR-026`). Without that
   memory it either re-runs on every poll or relies on a flag that goes stale on first use.
2. **It is a second data-plane write.** The sole DB touch cairn is permitted is
   `bench migrate` (`BR-DATA-005`/`006`/`008`, `ADR-022`). `install-app` creates DocTypes and
   inserts records — a materially larger claim on the database.
3. **It breaks rollback.** Install an app, then roll the image back (`BR-DEPLOY-004`): the
   app's schema remains and the code that understands it is gone. `bench migrate` is safe
   after **every** image enable precisely because it reconciles schema to code that *exists*;
   `install-app` would create schema for code that may vanish on the next pointer move.
*(BR-DEPLOY-007, BR-DATA-005/006/008, ADR-022, ADR-023, ADR-037)*

## Pointer operations

**`BR-DEPLOY-004`** — Deploy, promote, and rollback are the **same operation**: point an
environment tag at a chosen **existing** image, with **no rebuild**, via a **server-side
retag** (no local pull). The target converges on its next poll.
- **rollback** = repoint an env tag to a prior image;
- **promote** = repoint a downstream env tag to whatever an upstream env tag points at.
*(ADR-010)*

## Registry introspection

**`BR-DEPLOY-005`** — cairn MUST answer, from the registry, which images/tags exist and what
they point at, reading image **provenance labels remotely (without pulling)** to show, per
tag, the resolved digest and baked provenance. *(BR-BUILD-011, BR-CFG-011)*

## Garbage collection (disk safety)

**`BR-DEPLOY-006`** — A timer-driven GC pass MUST prune old images and stopped containers on
the target, **keeping the last N images** (configurable) for rollback headroom. **GC MUST
NEVER touch volumes** — never `docker volume prune`, never `docker system prune --volumes`.
*(ADR-022)*

## Scope

**`BR-DEPLOY-007`** — cairn deploys to **existing** environments. Initial site/volume/
database creation (`bench new-site`) is the operator's responsibility. *(ADR-022)*

**`BR-DEPLOY-008`** — cairn's reconcile is a purpose-built thin orchestrator over
`docker`/`docker compose`, the registry manifest API, and `systemd`; it does NOT adopt
Watchtower, Flux, or ArgoCD. *(ADR-024)*

## Environment model

**`BR-DEPLOY-009`** — An environment is defined in **two halves joined only by the env tag
name**: a thin **control-side declared environment list** (environment → registry tag) and a
**target-side environment descriptor** on each host. The declared list is the source of
truth for which environments exist and gates `new-tag`/`retag`/`retire` (`BR-CLI-009`).
Control-side commands operate on the **registry only** and MUST NOT require a target host's
address or inbound access. *(ADR-005, ADR-006, ADR-010)*

**`BR-DEPLOY-009a`** *(location of the declared list)* — The declared environment list is an
optional `[cairn.environments]` table in `cairn.toml`, mapping environment name → registry
tag (`ADR-033`). It is discovered with the manifest (`BR-CFG-012`) and requires no flag.
Absent or empty, **no environment exists**: the pointer verbs MUST report that rather than
create one (`BR-CLI-009`). No environment name may reach a build — the table exists to name
registry pointers, and the image stays environment-agnostic (`BR-BUILD-001`). *(ADR-033)*

**`BR-DEPLOY-010`** — The target-side **environment descriptor** declares: image + watched
tag; which frappe_docker overrides to compose (db, redis, proxy, TLS); domain/host and
ports; site name; and a **reference** to secrets. `cairn reconcile` MUST **render** the
final compose stack from it (base + selected overrides, plus `CUSTOM_IMAGE`/`CUSTOM_TAG`/
`PULL_POLICY`). The descriptor lives on the target and MUST NOT contain secrets. *(ADR-017)*

**`BR-DEPLOY-010a`** *(location and form of the descriptor)* — The descriptor is TOML at the
fixed path **`/etc/cairn/environment.toml`**, holding **one** environment per host
(`ADR-034`). Its presence is what identifies a machine as a target, and is the context
`ADR-028` detects the role from. Because `reconcile` runs unattended, the path MUST NOT be
searched for and MUST NOT be supplied by flag in the common case; an override MAY exist for
testing. The descriptor is **host state, not deployment state** — it MUST NOT be committed
with the deployment, and MUST contain no secret values (`BR-DEPLOY-011`). *(ADR-034)*

## Secrets (cairn is secret-agnostic)

**`BR-DEPLOY-011`** — cairn MUST NOT store, generate, persist, prompt for, or handle secret
**values**; it only references and wires secrets the operator provisions. *(ADR-017)*

**`BR-DEPLOY-012`** — A target authenticates to the registry via **Docker's credential
store** (operator runs `docker login ghcr.io` with a read-only pull token at provisioning);
`cairn reconcile` delegates auth to Docker and MUST NOT store registry credentials. *(ADR-017)*

**`BR-DEPLOY-013`** — DB/app secrets are operator-provisioned; cairn wires them via the
mechanism the descriptor names — **Docker secrets** (`compose.mariadb-secrets.yaml`)
recommended, plain `.env` supported. cairn never sees or persists the value; site-level
secrets remain off-limits (`BR-DATA-006`). *(ADR-017)*

## Single-site & Production safeguards

**`BR-DEPLOY-014`** — Each environment runs **one site**; multi-site is deferred (`ADR-016`).
*(ADR-016)*

**`BR-DEPLOY-015`** — Moving a **`:production`** pointer (deploy/promote/rollback) MUST
require **explicit confirmation** (interactive prompt or flag) — never silent. `install-app`
against Production MUST be **doubly** explicit. Non-prod does not require this gate. *(ADR-022)*

## Sequencing, health & failure

**`BR-DEPLOY-016`** — `cairn reconcile` MUST be **single-flight** (locked). The stack is
recreated **in place** (`compose up`). `bench migrate` runs after **every** image enable,
including rollback. *(ADR-014)*

**`BR-DEPLOY-017`** — cairn MUST verify the stack reaches a **healthy** state (frappe_docker
health + the site responds) within a configurable **timeout** before recording success.

**`BR-DEPLOY-018`** *(failure = halt + report)* — On a failed deploy (`migrate` error or
health failure/timeout), cairn MUST **halt and report**; it MUST NOT auto-rollback. *(ADR-025)*

## Observability

**`BR-DEPLOY-019`** — cairn MUST log **only to stdout/stderr** and MUST NOT write custom log
files. This is **absolute** for `reconcile` and for every unattended invocation, where
journald or the CI system already owns and retains the record. The sole exception is the
attended-CLI build transcript (`BR-CLI-016`), where nothing else does. *(ADR-026, ADR-031)*

**`BR-DEPLOY-020`** *(optional failure webhook)* — On any failure, cairn MAY POST to an
**operator-configured** webhook — a best-effort, outbound POST with a structured payload
(environment, failed step, image tag/digest, timestamp, error summary), transport-agnostic.
Opt-in; the URL may be a referenced secret; a webhook error MUST NOT crash cairn or alter
deploy behavior. *(ADR-026)*

---

## Deferred (not blocking; future work)
- **GHCR-side cleanup** — a separate, opt-in command later, never part of automatic VPS GC.
  **Verified GHCR facts (2026-07-24):** deletion is **version-based only**
  (`DELETE /…/packages/container/{package}/versions/{version_id}`); there is **no per-tag
  delete**, deleting a version removes all its tags + the image, and a **public** version
  with **>5,000 downloads cannot be deleted**. Consequence: an env tag cannot be removed
  without destroying the shared image — hence `cairn retire` decommissions at cairn's layer
  only (`BR-CLI-009`).

## Provisioning (the installer)

**`BR-DEPLOY-021`** *(installer contract)* — Provisioning a build machine or a target MAY be
performed by an installer **distributed alongside** the CLI — the same package, a separate
entry point — never by a verb inside `cairn` itself (`ADR-040`). That separation exists to
preserve two boundaries: cairn emits systemd units and never installs them (`ADR-035`), and
cairn writes nothing to a data-plane volume (`ADR-022`, `BR-DATA-006`) — a pre-install `bench
backup` writes into the sites volume and is therefore the operator's act.

Where an installer is provided it MUST:

1. **Be idempotent.** Re-running it MUST converge rather than duplicate or fail. This is what makes
   the second and third machine cheap, which is the reason it exists at all.
2. **Offer a dry run** that prints every action, including every command it would run, and writes
   nothing.
3. **Never silently overwrite.** An existing file it would replace MUST be preserved and named, and
   replacing it MUST require an explicit flag.
4. **Handle no secrets** (`BR-CFG-010`, `BR-DEPLOY-011`). It MUST NOT prompt for, generate, store, or
   log a credential value. Key material it creates for transport security MUST be created with
   owner-only permissions.
5. **Gate before acting.** Host prerequisites — engine, plugins, free disk, available memory — MUST be
   checked and *all* results reported before any change is made, and a failure MUST stop the run.
   The free-disk floor MAY be bypassed by an explicit flag (e.g. `--skip-disk-free`), for an
   operator who has already judged the risk of running short mid-build or mid-migration; no other
   prerequisite has such an override. Bypassing MUST still be reported — as a warning in the run's
   closing summary — never silently. The free-disk check MUST measure the filesystem the engine
   actually stores images and volumes on (the engine's reported data directory), not assume it is
   the root filesystem — a host with a separate mount for Docker data would otherwise have the
   wrong filesystem measured. Reported detail MUST name the path checked, so a mismatch is visible
   rather than silently wrong.
6. **Verify what it claims.** A step reporting success MUST have confirmed its post-condition: a
   backup is confirmed to exist and be non-empty, a registry is confirmed reachable, a written
   descriptor is confirmed to parse. This is `BR-CLI-011`'s rule applied to provisioning.
7. **Not be the only path.** Every action it takes MUST be documented such that an operator can
   perform it by hand. The installer is a convenience, never a dependency.

An installer MUST NOT create sites, volumes, or databases: `BR-DEPLOY-007` keeps that the operator's
responsibility, and provisioning the *plumbing* does not change it.
*(ADR-040, ADR-035, ADR-022, BR-DATA-006, BR-DEPLOY-007, BR-DEPLOY-011, BR-CFG-010, BR-CLI-011)*

**`BR-DEPLOY-022`** *(shared `/etc/cairn` — default, not mandatory)* — Where an installer is
provided (`BR-DEPLOY-021`), it MUST, by default and on every role, ensure `/etc/cairn` is
shared with a group (name configurable, e.g. `--admin-group`, default `cairn-admins`) rather
than left root-only: creating the group if absent, and setting the directory group-owned,
group-writable, and **setgid** so files later created inside inherit the group automatically.
An explicit flag (e.g. `--no-admin-group`) MUST allow skipping this and leaving the directory
exactly as found. This stage is bound by the same seven-point contract as every other
(`BR-DEPLOY-021`) — idempotent, reported in `--dry-run`, no secret material, gated on the same
root check, and its postcondition (the directory's actual group and mode) confirmed rather than
assumed. cairn itself MUST NOT perform this — creating or chowning a group is a host mutation
and stays with the installer (`ADR-040`); `cairn doctor` MAY report the directory's current
group, mode, and the invoking user's membership, but MUST NOT change any of them (`BR-CFG-015`).
*(ADR-042, ADR-043, BR-CFG-015, BR-DEPLOY-021)*
