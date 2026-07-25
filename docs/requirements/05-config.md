# BR-CFG — Configuration Requirements

_Status: **approved** 2026-07-23 (living) · revised 2026-07-25 · Last updated: 2026-07-25_

Configuration, in two orthogonal sub-domains: **target** (runtime, per-environment, on the
sites volume) and **build** (build-time only, local to the build machine). Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-009`, `ADR-015`, `ADR-017`, `ADR-019`, `ADR-022`.

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
local file separate from the portable `cairn.toml` manifest (e.g.
`~/.config/cairn/config.toml`, with an optional `cairn.local.toml` override) and MUST NOT be
committed with a shareable deployment. The manifest MUST remain free of these.

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
following precedence, and the common case MUST require no flags:
- **Manifest** — `--manifest <path>` when given; otherwise the nearest `cairn.toml`
  searching **upward from the working directory**. The manifest root is resolved
  independently of cairn's own project root (`ADR-029`).
- **Build config**, three layers, each overriding the previous **key-by-key**:
  1. `~/.config/cairn/config.toml` — the machine-wide base;
  2. the manifest's `[cairn.registry]` — where *this deployment's* images belong
     (`BR-CFG-014`);
  3. an optional `cairn.local.toml` **beside the manifest** — the deliberate local override.

  All three are optional; absent all, the documented defaults apply (`BR-CFG-011`). Layer 2
  is deliberately below layer 3 so a local override remains possible without editing — and
  committing — a client's manifest.
- **Machine** settings MUST NOT be read from the manifest, and the manifest MUST remain free
  of them (`BR-CFG-008`). Layer 2 MUST accept only `host` and `namespace`; anything else in
  `[cairn.registry]` MUST be rejected as an unknown key. *(ADR-029, ADR-039, BR-CLI-014)*

**`BR-CFG-013`** *(image ownership — the operator is never the sole owner of a client's image)*
— cairn MUST support publishing to a registry namespace the operator **does not own**, and MUST
NOT assume the operator's own. Absent any configured registry the image MUST stay local
(`BR-CFG-011`); cairn MUST NOT infer a default namespace from anything — not the machine, not
the git remote, not the operator's other deployments.

**Why this is a requirement and not a preference.** A consultant who is the only owner of a
client's built image holds that client's operations hostage: if the relationship ends badly the
client cannot deploy or roll back software **they own**. The registry that holds a client's
image MUST therefore be capable of being an account the client controls, so that revoking the
operator's access leaves the client whole and costs the operator nothing but access.

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

---

## Cross-references
- `DEPLOY`/`ADR-017` owns `common_site_config.json`, `.env`, and secrets.
- `BUILD` (`BR-BUILD-008`/`011`) consumes the registry/namespace from build config.
- **Follow-up (user docs):** a GHCR setup runbook (`ADR-009`) is deferred to Phase-6.
