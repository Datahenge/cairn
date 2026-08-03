---
status: authoritative
owner: requirements
purpose: BR-CFG requirements — target and build-machine configuration.
---

# BR-CFG — Configuration Requirements

_Status: **approved** 2026-07-23 (living) · revised 2026-07-26 · Last updated: 2026-08-03_

Configuration, in two orthogonal sub-domains: **target** (runtime, per-environment, on the
sites volume) and **build** (build-time only, local to the build machine). Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-009`, `ADR-015`, `ADR-017`, `ADR-019`, `ADR-022`,
`ADR-042`, `ADR-043`.

---

## A. Target configuration (on the sites volume)

**`BR-CFG-001`** — Environment-specific configuration MUST NOT be baked into the image; it
lives on the persistent **sites volume**. *(ADR-015, ADR-019)*

**`BR-CFG-002`** — cairn MUST NOT overwrite or destroy environment-specific config on the
sites volume during any operation. *(ADR-019)*

**`BR-CFG-003`** — cairn understands **Frappe framework** config (`site_config.json`,
`common_site_config.json`) but MUST treat **app-specific** config files (e.g. a cofferdam
policy file) **opaquely** — never parsing or validating them. *(ADR-019)*

**`BR-CFG-004`** — cairn MUST NOT overwrite Frappe-managed `site_config.json` (preserving
`encryption_key` and db credentials). *(ADR-022)*

**`BR-CFG-005`** — cairn performs no restore, data movement, or `encryption_key` handling on
volume config. *(ADR-019, ADR-022)*

**`BR-CFG-006`** — cairn MUST NOT write to, seed, provision, or modify persistent data-plane
volumes or their config; provisioning environment config is the operator's responsibility.
(Supersedes an earlier additive-seed allowance; see `BR-DATA-006`.) *(ADR-022)*

**`BR-CFG-007`** *(boundary)* — `common_site_config.json` lives on the volume but derives
from the compose environment (the `configurator` service); its source of truth is
`DEPLOY`/`ADR-017`, not `CFG`. Compose-level `.env`, DB root password, registry credentials,
and Docker secrets are `ADR-017`/`DEPLOY`. *(ADR-017)*

---

## B. Build configuration (local to the build machine)

**`BR-CFG-008`** — **Machine** configuration — the **build engine** (`ADR-027`),
builder/cache settings, local image base, **`transcript_dir`** (`BR-CLI-016`) — MUST live in a
file separate from the portable `cairn.toml` manifest (`/etc/cairn/builder.toml`, optionally
overridden per key by `CAIRN_*` environment variables) and MUST NOT be committed with a
shareable deployment. The manifest MUST remain free of these.

**Amended 2026-07-26 (`ADR-041`):** the file is named `builder.toml`, not `config.toml` —
one word apart from the manifest `cairn.toml` gave no reader a way to tell the two apart on
sight. `builder.toml` instead names the **role** (`Builder`, as opposed to `Target`) that
reads it — only builder-side commands and `doctor` ever do (`BR-CLI-014`). No key or
precedence rule changed; this amendment was the filename only.

**Amended 2026-07-26 (`ADR-042`):** the file moves to `/etc/cairn/builder.toml` — no
`$XDG_CONFIG_HOME`, no per-user home directory, no `cairn.local.toml`. A per-user config tier
is wrong for a multi-operator VPS (several human logins sharing one deployment): it is
invisible-until-it-bites, not a convenience. Every operator on the host now reads the identical
file; who may *write* it is left to ordinary filesystem permissions, which `setup`
can share with a group by default (`BR-CFG-015`, `ADR-043`, `ADR-046`) but cairn itself neither
assumes nor enforces. `cairn.local.toml`'s job — a personal, no-root, per-checkout override — is fully
absorbed by the `CAIRN_*` environment-variable layer once every invocation already carries an
explicit manifest reference (`BR-CFG-012`); it is not relocated, it is removed.

**Amended 2026-07-25 (`ADR-039`):** the registry **host** and **namespace** are excepted and
belong in the manifest (`BR-CFG-014`). They are not secrets and not machine facts — under
`BR-CFG-013` they usually name the *client's* registry, which is a property of the deployment.
The original wording lumped them in with machine settings on the assumption that one manifest
might target many registries; with client-owned registries one manifest means one owner, and
the reasoning inverts. *(ADR-015, ADR-009, ADR-031, ADR-039)*

**`BR-CFG-009`** — cairn MUST be **registry-agnostic**: the image registry + namespace is a
build-config value (any OCI registry), never hardcoded to Docker Hub. *(ADR-009)*

**`BR-CFG-010`** — cairn MUST NOT store, persist, or write registry credentials;
authentication is the **container engine's** responsibility (`docker login` /
`podman login`, `ADR-027`). cairn MAY read a registry token from an environment variable or
a local env file at invocation to perform a **transient** login, but MUST NOT persist it.
Build config carries only the non-secret registry namespace. *(ADR-017, ADR-027)*

**`BR-CFG-011`** — With a registry configured, cairn pushes images to
`<registry>/<namespace>/<image_name>:<tag>`, and the provenance labels (`BR-BUILD-011`) ride
with the pushed image. Absent a registry, images remain local (`cairn/<image_name>`,
`PULL_POLICY=missing`). *(ADR-009)*

**`BR-CFG-012`** *(discovery & precedence)* — cairn MUST discover configuration by the
following precedence, and it MUST perform **no filesystem search of any kind** — not the
working directory, not any ancestor of it, not a fixed system path guessed at (`ADR-042`,
superseding this requirement's former "the common case MUST require no flags" clause,
confirmed as a deliberate reversal, and superseding `ADR-029`'s directory walk):

- **Manifest** — `--manifest <path>` when given, else `$CAIRN_MANIFEST`. Neither given is an
  error naming both options; there is no third, implicit option. Every invocation states
  which deployment it targets. The manifest root remains resolved independently of cairn's
  own project root (`ADR-029`) — this requirement governs the *deployment* manifest only, not
  cairn's own vendoring project-root discovery (`src/cairn/project.py`), which is a genuinely
  different question cwd still legitimately answers.
- **Build config**, three layers, each overriding the previous **key-by-key**:
  1. `/etc/cairn/builder.toml` — the machine-wide base, shared by every login on the host
     (`BR-CFG-008`);
  2. the manifest's `[cairn.registry]` — where *this deployment's* images belong
     (`BR-CFG-014`);
  3. `CAIRN_ENGINE` / `CAIRN_REGISTRY` / `CAIRN_NAMESPACE` / `CAIRN_IMAGE_BASE` /
     `CAIRN_TRANSCRIPT_DIR` — the deliberate override, one environment variable per
     `BUILD_CONFIG_KEYS` entry (`ADR-042`).

  No other override path exists: layer 1 is not itself overridable by a same-named file in
  the working directory (the sole per-checkout override, `cairn.local.toml`, is removed
  entirely — its job is now layer 3's), nor by any CLI flag (the sole adjacent exception is
  `--transcript <path>` on `cairn-build build`, which replaces the destination outright rather than
  overriding `transcript_dir`; `BR-CLI-016`). All three are optional; absent all, the
  documented defaults apply (`BR-CFG-011`). Layer 2 is deliberately below layer 3 so an
  override remains possible without editing — and committing — a client's manifest.
- **Machine** settings MUST NOT be read from the manifest, and the manifest MUST remain free
  of them (`BR-CFG-008`). Layer 2 MUST accept only `host` and `namespace`; anything else in
  `[cairn.registry]` MUST be rejected as an unknown key. *(ADR-029, ADR-039, ADR-042,
  BR-CLI-014)*

**`BR-CFG-013`** *(image ownership — the operator is never the sole owner of a client's image)*
— cairn MUST support publishing to a registry namespace the operator **does not own**, and MUST
NOT assume the operator's own. Absent any configured registry the image MUST stay local
(`BR-CFG-011`); cairn MUST NOT infer a default namespace from anything — not the machine, not
the git remote, not the operator's other deployments.

**Why this is a requirement and not a preference.** The registry that holds a client's image
MUST be capable of being an account the client controls, so that revoking the operator's
access leaves the client whole. Full rationale: `ADR-038`,
`docs/technical/ABOUT_REGISTRIES.md`.

Three consequences that follow, and that cairn MUST NOT make awkward:
- **One operator identity, many owners.** The operator MUST NOT need a separate login, account,
  or credential store per client. Registry authorization is the registry's to resolve — the
  operator holds one credential per registry *host*, and access to each namespace is granted
  server-side.
- **Least privilege, scoped to the engagement.** A documented pattern MUST permit the operator's
  push credential to be scoped to **the images of that engagement and nothing else** —
  per-repository, not per-account. This is *liability containment for the operator* before it is
  a security control: a credential that can write exactly one repository cannot be the cause of a
  catastrophe, and the operator is far likelier to make a costly mistake than to act in bad
  faith. A registry whose write credentials are irreducibly account-wide is therefore **weaker
  for this purpose**, and that MUST be documented as a selection criterion rather than left for
  the operator to discover.
- **Costs follow ownership.** Storage and egress for a client's images accrue to the client's
  account, sized to their needs, and are not a cost the operator absorbs or a quota the
  operator's other clients compete for. *(ADR-038, BR-CFG-009, BR-CFG-011, BR-CFG-014)*

**`BR-CFG-014`** *(registry coordinates live in the manifest)* — The manifest MAY declare
`[cairn.registry]` with a required `host` and an optional `namespace`. This is the deployment's
statement of **where its images belong**, and it is committed with the deployment so that the
image location is reproducible without the operator's machine — and so the client can take the
deployment over and keep publishing to their own registry. It MUST contain no credentials
(`BR-CFG-010`). *(ADR-038, ADR-039, BR-CFG-008, BR-CFG-012)*

**`BR-CFG-015`** *(a shared `/etc/cairn`, not a per-user one)* — `/etc/cairn` MUST remain a
single, host-wide directory whose write access is governed by ordinary filesystem
permissions — cairn MUST NOT assume, require, or check for any particular owner, group, or
mode. `setup`, the privileged subcommand nested in each CLI (`cairn-build setup` /
`cairn-adopt setup`, `BR-DEPLOY-021`, `ADR-046`) MAY share the directory with a group by
default so multiple operators can edit `builder.toml` without root; doing so or skipping it
are both conforming. `cairn-build doctor` / `cairn-adopt doctor` MAY report the directory's
current group, permissions, and the invoking user's membership, but MUST NOT mutate any of
them — diagnostic only, matching every other doctor check. *(ADR-042, ADR-043, ADR-046,
BR-DEPLOY-021)*

---

## Cross-references
- `DEPLOY`/`ADR-017` owns `common_site_config.json`, `.env`, and secrets.
- `BUILD` (`BR-BUILD-008`/`011`) consumes the registry/namespace from build config.
- `DEPLOY`/`BR-DEPLOY-021` owns the `setup` installer contract that `BR-CFG-015`'s
  default group-sharing stage must satisfy.
- **Follow-up (user docs):** a GHCR setup runbook (`ADR-009`) is deferred to Phase-6.
