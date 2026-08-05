---
status: authoritative
owner: requirements
purpose: BR-DEPLOY requirements — deploying images to environments and keeping targets converged.
---

# BR-DEPLOY — Deploy Lifecycle Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-08-05_

Requirements for deploying images to environments and keeping targets converged.
Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-005`, `ADR-006`, `ADR-010`, `ADR-012`,
`ADR-014`, `ADR-016`, `ADR-017`, `ADR-022`, `ADR-023`, `ADR-024`, `ADR-025`, `ADR-026`,
`ADR-042`, `ADR-043`, `ADR-046`, `ADR-052`.

---

## Pull-based reconcile

**`BR-DEPLOY-001`** — The deploy model is **pull-based**: each target runs an idempotent
`cairn-adopt reconcile` on a **systemd timer**, converging the running stack to desired state,
**outbound-only** (no inbound connection to the box). A no-change run is a no-op.
*(ADR-005, ADR-006)*

**`BR-DEPLOY-002`** — The **desired-state pointer** is the environment's **moving image tag**
in the registry (`:dev`/`:test`/`:staging`/`:production`). The target polls that tag's
**digest** and converges when it changes. *(ADR-010)*

**`BR-DEPLOY-003`** — On a detected change, `cairn-adopt reconcile` MUST: pull the image → set
`CUSTOM_IMAGE`/`CUSTOM_TAG` → `docker compose up -d` → run `bench migrate` → verify health.
cairn performs no volume or SQL writes of its own (`BR-DATA-005`/`006`/`008`).
*(ADR-014, ADR-023)*

**`BR-DEPLOY-003a`** *(cairn never installs a Frappe App)* — `cairn-adopt reconcile` MUST NOT run
`bench install-app`, under any flag or directive. Installing a Frappe App is the **operator's**
act, exactly as site creation is (`BR-DEPLOY-007`). An earlier draft of `BR-DEPLOY-003`
permitted it behind an opt-in directive; that clause was **struck** 2026-07-25 (`ADR-037`).

Three reasons, of which the first is structural:

1. **A convergence loop cannot host a one-shot mutation.** `reconcile` exists to make actual
   state match desired state, repeatedly and idempotently. Installing a Frappe App is irreversible and
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

**`BR-DEPLOY-003b`** *(convergence is verified against the running container, not the local
image store)* — After `compose up -d`, cairn MUST determine "converged" by reading the digest
of the image the **running** `backend` container was actually started from, not merely
whether an image with the desired digest exists somewhere in the local store. `docker compose
up` only recreates a container when its rendered service definition changes; a compose file
that hardcodes `image:` per service, rather than parameterizing it with
`${CUSTOM_IMAGE}`/`${CUSTOM_TAG}`, never reacts to those variables at all — the desired image
can be pulled and sitting in the local store while the running container stays untouched. A
mismatch here MUST be treated the same as any other convergence failure (`BR-DEPLOY-018`): a
loud halt and report, never a false `Converged`. *(found live 2026-08-05, ADR-021 fork-pressure
register item 4)*

## Pointer operations

**`BR-DEPLOY-004`** *(promotion is proof, not assertion, `ADR-052`)* — Deploy, promote, and
rollback are the **same operation**: resolve one environment's own manifest to its **current**
resolved refs, and if an image already exists in the registry under that exact deterministic
tag (`BR-BUILD-008`), point the environment's tag at it — a **server-side retag** (no rebuild,
no local pull). If no such image exists yet, there is nothing to point at; only `build` creates
one. The target converges on its next poll.
- **rollback** = reset the environment's tracked ref to an earlier commit (outside cairn), then
  resolve again — if that commit's image still exists in the registry (not yet GC'd), it retags
  instantly with no rebuild.
- **promote** = a downstream environment's own resolve-and-check happens to match an image an
  upstream environment already built. Nothing asserts this is a promotion; the registry match is
  the proof. There is no cross-environment reference of any kind — one environment's pointer
  operation never reads another environment's manifest or tag. *(ADR-010, ADR-052)*

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

**`BR-DEPLOY-009`** *(1:1, `ADR-052`)* — An environment is defined in **two halves joined only
by the env tag name**: a **control-side declared environment**, at most one per manifest, and a
**target-side environment descriptor** on each host. The manifest's declared environment (if
any) is what gates `assign-tag`/`retire` for that manifest (`BR-CLI-009`). Control-side
commands operate on the **registry only** and MUST NOT require a target host's address or
inbound access. There is no shared, cross-manifest environment list — each manifest is
authoritative only for its own environment. *(ADR-005, ADR-006, ADR-010, ADR-052)*

**`BR-DEPLOY-009a`** *(location and uniqueness of the declared environment, `ADR-052`)* — The
declared environment is an optional `[cairn] environment` string in `cairn.toml` — a manifest
declares **at most one**. It is discovered with the manifest (`BR-CFG-012`) and requires no
flag; no command takes an environment name as an argument — every environment-targeting command
takes `--manifest <path>` instead (`BR-CLI-004`). Absent, the manifest declares no environment
and `assign-tag`/`retire` against it MUST report that (`BR-CLI-009`). No environment name may
reach a build by default — the image stays environment-agnostic (`BR-BUILD-001`) unless
`build --assign-tag` is explicitly given (`BR-CLI-002a`).

**Uniqueness key: (client, image_name, environment), not environment alone.** The same
environment name MAY legitimately repeat across different `image_name`s within one client —
this mirrors the registry's own tag scoping, since an environment name is nothing but a
registry tag, and a tag's uniqueness is already scoped to one repository
(`<registry>/<namespace>/<image_name>`). Two manifests sharing both the same `image_name` and
the same `environment` within one client is a conflict `cairn-build doctor` MUST detect and
report, case-insensitively (`BR-CLI-007`). *(ADR-033, ADR-049, ADR-052)*

**`BR-DEPLOY-010`** — The target-side **environment descriptor** declares: image + watched
tag; which frappe_docker overrides to compose (db, redis, proxy, TLS); domain/host and
ports; site name; and a **reference** to secrets. `cairn-adopt reconcile` MUST **render** the
final compose stack from it (base + selected overrides, plus `CUSTOM_IMAGE`/`CUSTOM_TAG`/
`PULL_POLICY`). The descriptor lives on the target and MUST NOT contain secrets. *(ADR-017)*

**`BR-DEPLOY-010a`** *(location and form of the descriptor)* — The descriptor is TOML at the
fixed path **`/etc/cairn/adopt.toml`**, holding **one** environment per host
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
`cairn-adopt reconcile` delegates auth to Docker and MUST NOT store registry credentials. *(ADR-017)*

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

**`BR-DEPLOY-016`** — `cairn-adopt reconcile` MUST be **single-flight** (locked). The stack is
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
  without destroying the shared image — hence `cairn-build retire` decommissions at cairn's
  layer only (`BR-CLI-009`).

## Provisioning (`setup`)

**`BR-DEPLOY-021`** *(installer contract)* — Provisioning a build machine or a target is
performed by `setup`, a subcommand nested in each role's own CLI (`cairn-build setup`,
`cairn-adopt setup`, `BR-CLI-021`, `ADR-046`) — never by any other, ordinary subcommand. That
separation exists to preserve two boundaries: cairn emits systemd units and never installs them
except via this explicit, privilege-gated path (`ADR-035`), and cairn writes nothing to a
data-plane volume (`ADR-022`, `BR-DATA-006`) — a pre-install `bench backup` writes into the
sites volume and is therefore the operator's act, performed only when the operator explicitly
invokes `setup`.

`setup` MUST:

1. **Be idempotent.** Re-running it MUST converge rather than duplicate or fail. This is what makes
   the second and third machine cheap, which is the reason it exists at all. Convergence covers a
   file's **mode**, not only its content — a file whose content already matches MUST still have
   its mode corrected if it drifted, since matching content is otherwise a permanent excuse to
   never look at it again. Where a stage regenerates identity material a running container
   already loaded into memory (e.g. the registry's TLS certificate), convergence MUST recreate
   that container — a file changing underneath an already-running process is invisible both to
   the process and to `docker compose up -d`'s own change detection, so nothing else would make
   it pick up the new file.
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
   the root filesystem — a host with a separate mount for engine data would otherwise have the
   wrong filesystem measured. On a build machine "the engine" MUST mean whichever one `setup`
   actually selected — docker or podman (`ADR-027`) — never assumed to be docker; a deploy target
   or the local registry, both fixed to Docker (`ADR-002`), have only the one engine to measure.
   Reported detail MUST name the path checked, so a mismatch is visible rather than silently wrong.
6. **Verify what it claims.** A step reporting success MUST have confirmed its post-condition: a
   backup is confirmed to exist and be non-empty, a registry is confirmed reachable, a written
   descriptor is confirmed to parse. This is `BR-CLI-011`'s rule applied to provisioning.
7. **Not be the only path.** Every action it takes MUST be documented such that an operator can
   perform it by hand. The installer is a convenience, never a dependency.

`setup` MUST NOT create sites, volumes, or databases: `BR-DEPLOY-007` keeps that the operator's
responsibility, and provisioning the *plumbing* does not change it.
*(ADR-046, ADR-040, ADR-035, ADR-022, BR-DATA-006, BR-DEPLOY-007, BR-DEPLOY-011, BR-CFG-010,
BR-CLI-011, BR-CLI-021)*

**`BR-DEPLOY-022`** *(shared `/etc/cairn` — default, not mandatory)* — `setup`
(`BR-DEPLOY-021`) MUST, by default and on every role, ensure `/etc/cairn` is
shared with a group (name configurable, e.g. `--admin-group`, default `cairn-admins`) rather
than left root-only: creating the group if absent, and setting the directory group-owned,
group-writable, and **setgid** so files later created inside inherit the group automatically.
An explicit flag (e.g. `--no-admin-group`) MUST allow skipping this and leaving the directory
exactly as found. This stage is bound by the same seven-point contract as every other
(`BR-DEPLOY-021`) — idempotent, reported in `--dry-run`, no secret material, gated on the same
root check, and its postcondition (the directory's actual group and mode) confirmed rather than
assumed. No other subcommand on either CLI MUST perform this — creating or chowning a group is a
host mutation and stays with `setup` (`ADR-046`, `ADR-040`); `cairn-build doctor` /
`cairn-adopt doctor` MAY report the directory's current group, mode, and the invoking user's
membership, but MUST NOT change any of them (`BR-CFG-015`).

Sharing the directory is not enough on its own: the setgid bit propagates *group ownership* to a
file created later, but never its permission bits — a file `setup` writes still gets
whatever mode its own umask leaves it, which is commonly group-**readable** only. Any file under
`/etc/cairn` that `setup` writes and an operator is meant to edit without `sudo` (the
descriptor; `builder.toml` is operator-authored, not `setup`-written) MUST therefore be written
group-**writable** explicitly, not left to inheritance. Key material stays the documented
exception — owner-only regardless (rule 4).
*(ADR-042, ADR-043, BR-CFG-015, BR-DEPLOY-021)*
