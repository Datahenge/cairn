# BR-CFG — Configuration Requirements

_Status: **approved** 2026-07-23 (living — may be revised via CHANGELOG) · Last updated: 2026-07-23_

Requirements for configuration. Two orthogonal sub-domains:
- **Target configuration** — runtime, per-environment, lives on the sites volume.
- **Build configuration** — build-time only, local to the build machine.

Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-009`, `ADR-015`, `ADR-017`, `ADR-019`.

---

## A. Target configuration (runtime, on the sites volume) — approved

**`BR-CFG-001`** — Environment-specific configuration MUST NOT be baked into the image
(the image is environment-agnostic); it lives on the persistent **sites volume**.
*(ADR-015, ADR-019)*

**`BR-CFG-002`** — cairn MUST NOT overwrite or destroy environment-specific config on the
sites volume during any operation (image swap, rebuild, redeploy, restore). *(ADR-019)*

**`BR-CFG-003`** — cairn understands **Frappe framework** config (`site_config.json`
incl. `encryption_key`/db credentials; `common_site_config.json`) but MUST treat
**app-specific** config files (e.g. a cofferdam policy file) **opaquely** — never parsing
or validating them. `ADR-019`'s "not app-aware" applies to apps, not to Frappe itself.
*(ADR-019)*

**`BR-CFG-004`** — cairn MUST NOT overwrite Frappe-managed `site_config.json`, preserving
`encryption_key` and db credentials. *(data-safety)*

**`BR-CFG-005`** — Two classes of on-volume config are recognized, with opposite restore
behavior:
- **data-bound** config that MUST travel with its data — e.g. `encryption_key`; a restore
  is useless (encrypted fields unrecoverable) without the matching key;
- **env-authority** config that MUST NOT travel with restored data — e.g. an app policy
  file whose *target* copy stays authoritative (`ADR-019`).

This distinction drives the `DATA` restore requirements (esp. carrying `encryption_key`
with a backup). *(ADR-019; forward to `DATA`)*

**`BR-CFG-006`** *(provisioning — preserve-first + additive-seed)* — cairn MUST never
clobber volume config; it MAY **additively** seed *additional* local config files onto a
**fresh** volume from a deployment-owned source; it MUST NOT overwrite Frappe-managed
files. *(ADR-019)*

**`BR-CFG-007`** *(boundary)* — `common_site_config.json` lives on the volume but
**derives from the compose environment** (the `configurator` service) — its source of
truth is `DEPLOY`/`ADR-017`, not `CFG`. Compose-level `.env`, DB root password, registry
credentials, and Docker secrets are `ADR-017`/`DEPLOY`, not `CFG`. *(ADR-017)*

---

## B. Build configuration (build-time, local to the build machine) — approved

**`BR-CFG-008`** — Build configuration (registry/namespace target, buildx builder, cache
settings, local image base) is build-time-only and machine/user-specific. It MUST live in
a local file **separate from the portable `cairn.toml` manifest** (e.g. user-level
`~/.config/cairn/config.toml`, with an optional per-deployment `cairn.local.toml`
override) and MUST NOT be committed with a shareable deployment. The manifest MUST remain
free of local/build/registry settings so it stays portable. *(ADR-015, ADR-009)*

**`BR-CFG-009`** — cairn MUST be **registry-agnostic**: the image registry + namespace is
a build-config value (any OCI registry — GHCR, self-hosted, GitLab, ECR, …), never
hardcoded to Docker Hub. *(ADR-009)*

**`BR-CFG-010`** — cairn MUST NOT store, persist, or write registry credentials;
authentication is Docker's responsibility (`docker login` / `~/.docker/config.json`). For
convenience, cairn MAY read a registry token from an **environment variable or a local
env file** at invocation and use it to perform a **transient** `docker login` (e.g.
`printf %s "$TOKEN" | docker login ghcr.io -u <user> --password-stdin`), but MUST NOT
persist it beyond the process. Build config itself carries only the non-secret registry
namespace. *(security)*

**`BR-CFG-011`** — With a registry configured, cairn pushes images to
`<registry>/<namespace>/<image_name>:<tag>`, and the provenance **labels** (`BR-BUILD-011`)
ride with the pushed image — the registry is the image-and-metadata store. Absent a
registry, images remain local (`cairn/<image_name>`, `PULL_POLICY=missing`). *(ADR-009;
cites BUILD)*

---

## Cross-references
- `DATA` restore cites `BR-CFG-002`/`004`/`005` (never clobber config; carry
  `encryption_key`).
- `DEPLOY`/`ADR-017` owns `common_site_config.json`, `.env`, and secrets.
- `BUILD` (`BR-BUILD-008`/`011`) consumes the registry/namespace from build config.
- **Follow-up (user docs):** a **GHCR setup runbook** is needed (`ADR-009`) — PAT
  creation, `docker login ghcr.io`, package visibility, and a read-only VPS pull token.
  Deferred to Phase-6 user documentation; can be drafted on request.
