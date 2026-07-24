# BR-CFG — Configuration Requirements

_Status: **approved** 2026-07-23 (living) · revised 2026-07-24 · Last updated: 2026-07-24_

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

**`BR-CFG-008`** — Build configuration (registry/namespace target, buildx builder, cache
settings, local image base) MUST live in a local file **separate from the portable
`cairn.toml` manifest** (e.g. `~/.config/cairn/config.toml`, with an optional
`cairn.local.toml` override) and MUST NOT be committed with a shareable deployment. The
manifest MUST remain free of local/build/registry settings. *(ADR-015, ADR-009)*

**`BR-CFG-009`** — cairn MUST be **registry-agnostic**: the image registry + namespace is a
build-config value (any OCI registry), never hardcoded to Docker Hub. *(ADR-009)*

**`BR-CFG-010`** — cairn MUST NOT store, persist, or write registry credentials;
authentication is Docker's responsibility (`docker login`). cairn MAY read a registry token
from an environment variable or a local env file at invocation to perform a **transient**
`docker login`, but MUST NOT persist it. Build config carries only the non-secret registry
namespace. *(ADR-017)*

**`BR-CFG-011`** — With a registry configured, cairn pushes images to
`<registry>/<namespace>/<image_name>:<tag>`, and the provenance labels (`BR-BUILD-011`) ride
with the pushed image. Absent a registry, images remain local (`cairn/<image_name>`,
`PULL_POLICY=missing`). *(ADR-009)*

---

## Cross-references
- `DEPLOY`/`ADR-017` owns `common_site_config.json`, `.env`, and secrets.
- `BUILD` (`BR-BUILD-008`/`011`) consumes the registry/namespace from build config.
- **Follow-up (user docs):** a GHCR setup runbook (`ADR-009`) is deferred to Phase-6.
