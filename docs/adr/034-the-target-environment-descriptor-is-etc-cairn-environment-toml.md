---
status: authoritative
owner: technical
purpose: ADR-034 — The target environment descriptor is `/etc/cairn/adopt.toml`, one per host
---

# ADR-034 — The target environment descriptor is `/etc/cairn/adopt.toml`, one per host

**Decided:** 2026-07-25 · **Amended:** 2026-08-03 (filename only — see below)

`BR-DEPLOY-010` specifies the descriptor's **contents** — image and watched tag, which
frappe_docker overrides to compose, domain and ports, site name, a *reference* to secrets —
and `ADR-017` makes it the thing that names the secret mechanism. Neither says what the file
is called or where it sits, and `cairn reconcile` cannot find it without that.

**Decision:** TOML at a fixed path, `/etc/cairn/adopt.toml`, holding **one**
environment per host.

**Amended 2026-08-03 — renamed from `environment.toml` to `adopt.toml`.** Explicit
ownership, matching `builder.toml`: each machine-local file is now named for the one CLI
that reads it (`cairn-adopt` ↔ `adopt.toml`, `cairn-build` ↔ `builder.toml`), so which role
owns which file is legible from the filename alone rather than requiring the reader to
already know the descriptor is "the environment one." Every property below this line —
fixed path, TOML, one per host — is unchanged; only the token changed.

**Why a fixed path.** `reconcile` runs unattended under a timer, where a flag is a thing
nobody is present to pass and a search path is a thing that can silently find the wrong file.
A fixed location also gives `ADR-028` the role signal it needs: the presence of this file
*is* what makes a machine a target, so `cairn doctor` can pick its branch from context
without a flag.

**Why TOML.** cairn is TOML throughout (`cairn.toml`, build config, `pyproject.toml`), and
`tomllib` is in the standard library. YAML beside the compose files would read more naturally
next to what it renders, but it buys a dependency to express a flat table of scalars.

**Why one environment per host.** `BR-DEPLOY-014` already gives each environment one site,
and `ADR-002` scopes cairn to a single-host VPS with Compose. One environment per host keeps
`reconcile` argument-free — it converges *the* environment, not *an* environment — and keeps
the lock in `BR-DEPLOY-016` a single global one. Several environments on one host would need
`reconcile <env>`, a lock per environment, and a rendered stack per environment; if that need
arrives, `/etc/cairn/<env>.toml` extends this cleanly and `reconcile` gains an argument.

**The file holds no secret values** (`BR-DEPLOY-011`) — only the name of the mechanism and
the references the operator provisioned. It is host state, not deployment state: it is *not*
committed to the deployment repository, because it describes this box.
*(BR-DEPLOY-010, BR-DEPLOY-011, BR-DEPLOY-014, BR-DEPLOY-016, BR-CLI-008, ADR-002, ADR-016, ADR-017, ADR-028)*
