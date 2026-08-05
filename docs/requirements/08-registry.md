---
status: authoritative
owner: requirements
purpose: BR-REG requirements — provisioning, lifecycle, retention, and garbage collection for the local registry role.
---

# BR-REG — Registry Lifecycle Requirements

_Status: **approved** 2026-08-03 · Last updated: 2026-08-04_

Requirements for `cairn-registry`, the third CLI role: provisioning and operating a
self-hosted OCI registry, and keeping its disk use bounded. Conventions: see `/CLAUDE.md`.
Decisions cited: `ADR-009`, `ADR-035`, `ADR-036`, `ADR-038`, `ADR-039`, `ADR-046`, `ADR-048`,
`ADR-053`.

---

## Role and scope

**`BR-REG-001`** — `cairn-registry` is a third role, independent of `cairn-build` and
`cairn-adopt` (`ADR-048`). It MUST NOT read a manifest (`cairn.toml`),
`[cairn.declared_environments]`, or any build-config file — every decision it makes is derived
from the registry's own state (its config file and the registry's own tag/manifest API) or from
operator-supplied flags.
This is what keeps a registry host provisionable independently of which machines build or
adopt, and is verified in code by `registry_config.py`/`registry_provision.py`/
`registry_retention.py` importing neither `config.py` nor `environments.py`.

## Configuration

**`BR-REG-002`** *(config file)* — Machine-local settings live at `/etc/cairn/registry.toml`,
read from that fixed path only — no directory search, matching the discovery model
`BR-CFG-012`/`ADR-042` already established for `builder.toml`. Absent entirely, `cairn-registry
setup` still runs, against documented built-in defaults (`port = 5000`,
`bind_address = "127.0.0.1"`, `data_dir = "/var/lib/cairn-registry"`, retention disabled).
Recognized keys:

```toml
[registry]
port = 5000
bind_address = "127.0.0.1"
data_dir = "/var/lib/cairn-registry"

[registry.retention]
enabled = false
keep_last = 10
max_age_days = 90

[registry.gc]
schedule = "weekly"
```

An unknown key MUST be rejected at parse time, naming the key, matching the strictness
`config.py` already applies to every manifest table but `[cairn.build]`.

**`BR-REG-002a`** *(discoverability)* — The first time this path has no file, `cairn-registry
setup` MUST create one there, fully commented, containing exactly the built-in defaults above.
This is a courtesy, not a requirement to hand-author one from nothing — an operator who never
opens it gets the identical defaults either way. Like `cairn-build setup`'s starter manifest
(`BR-CLI-022`), an existing file at this path MUST NOT be modified again by any later `setup`
run, `--force` included: once it exists it is the operator's own config, not cairn's to manage.

## Provisioning

**`BR-REG-003`** *(setup)* — `cairn-registry setup` provisions a self-signed TLS registry:
generates (or reuses) a certificate trusted both system-wide and by Docker's per-registry
store, writes a `docker compose` file binding `<bind_address>:<port>` and bind-mounting
`data_dir` (an operator-chosen path, never an anonymous Docker volume — the concrete fix for
the original complaint that image storage had no configurable home), brings the registry up,
and health-checks it over HTTPS. This is `stage_registry`'s prior behavior (`provision.py`),
migrated wholesale and made config-driven; `cairn-build setup` no longer has a `"registry"`
stage. Same seven-point installer contract as every other `setup` (`BR-DEPLOY-021`):
idempotent, `--dry-run` prints and writes nothing, never silently overwrites, handles no
secrets, gates before acting, verifies what it claims, and is never the only path to the same
result. Unlike `cairn-build`/`cairn-adopt setup`, it takes no `--workdir` — none of its three
stages resolve a manifest relative to one (`BR-REG-001`), so the flag would promise a relevance
it doesn't have.

**`BR-REG-003a`** *(setup verifies itself with doctor)* — A real (non-`--dry-run`) run that
actually brought the registry container up — the full stage set, or `--only registry` alone —
MUST finish by running the same checks as `doctor` (`BR-REG-011`) and exit with its code. The
installer's own summary is a log of actions taken, not a health verdict; `doctor` additionally
checks certificate validity and disk headroom, neither of which `setup`'s own reachability
check covers. Skipped for `--dry-run` (nothing was started to check) and for `--only
preflight`/`--only admin-group` (the registry container was never touched by either).

**`BR-REG-004`** *(lifecycle)* — `status`, `start`, `stop`, `restart` are thin `docker compose`
wrappers over the compose project `setup` wrote (`ADR-024`'s "thin orchestration" precedent) —
cairn does not reimplement container lifecycle management.

## Introspection

**`BR-REG-005`** *(images)* — `cairn-registry images [--json]` lists repositories, tags, and
the digest each resolves to, reading the registry's own API remotely — no pull, mirroring
`BR-DEPLOY-005`'s existing no-pull introspection for the same reason. Output MUST be **grouped
by digest**, not listed one row per tag: a deterministic content-hash tag, `latest`, and any
moving tag an operator assigned (an environment pointer, or anything else) can all name the
same build, and a reader — deciding, for instance, what to write into a target descriptor's
`tag` — needs to see every name for one build together, not cross-reference repeated digests
by eye. Labels are explicit throughout (a repository line reads as a repository, not a bare
name; columns are headed) — nothing is left for the reader to infer.

## Retention

**`BR-REG-006`** *(retention algorithm)* — With `[registry.retention] enabled = true`,
`cairn-registry prune` MUST, per repository:

1. List every tag and resolve each to a digest, building a digest → tag-names map.
2. Treat a digest as deletion-eligible only if **every** tag on it matches cairn's own
   content-hash shape, `^<series>-[0-9a-f]{12}$` (`BR-BUILD-008`). A digest carrying a moving
   series tag or a declared-environment tag — either a plain, non-hash-shaped name — is
   categorically protected. This is sufficient to guarantee `cairn-registry` never deletes an
   image an environment still points at, without reading `[cairn.declared_environments]`: an
   environment tag is created by `retag()`'s server-side copy onto the same digest a
   content-hash tag already names (`registry.py`), so it always shows up in this same map.
3. Rank eligible digests by the `org.opencontainers.image.created` label already stamped on
   every build (`BR-BUILD-011`) — newest first.
4. Keep the newest `keep_last` unconditionally, regardless of age — the rollback-headroom
   floor, mirroring `BR-DEPLOY-006`'s existing "keep last N" language for the target's local
   disk, applied here to the registry.
5. Of the remainder, delete only digests older than `max_age_days`.
6. Report every digest's disposition (kept — floor / kept — protected by tag shape / kept —
   under age / deleted) before deleting anything; `--dry-run` performs step 6 and nothing
   past it, matching `BR-CLI-011`'s "nothing consequential is silent."

**`BR-REG-007`** *(tag-shape recognition is not configurable)* — Which tag shapes are eligible
for retention is a built-in invariant derived from `BR-BUILD-008`, never an operator-supplied
pattern. `enabled`, `keep_last`, and `max_age_days` are the only retention knobs — narrowing the
config surface is deliberate: a wrong `keep_last` wastes disk, but a wrong eligibility pattern
can delete a live pointer, so that axis is not exposed to get wrong.

**`BR-REG-008`** *(with `enabled = false`, the default)* — `prune` still runs and reports its
full disposition list; it deletes nothing. Retention must be turned on deliberately.

## Garbage collection

**`BR-REG-009`** — `cairn-registry gc` reclaims blob storage for digests `prune` has already
deleted. It MUST put the registry into read-only maintenance mode before running the
registry's own `garbage-collect`, then return it to normal — reads (pulls, including
`cairn-adopt reconcile`'s polling) continue throughout; writes (pushes) are refused for the
duration. `gc` MUST report this window plainly before running and MUST require `--yes` or
`--dry-run`, mirroring the confirmation gate `BR-CLI-010` already uses for production-affecting
actions.

## Timer

**`BR-REG-010`** — `cairn-registry setup-timer` emits (never installs, `ADR-035`) a systemd
timer that runs `prune` then `gc` on the cadence named by `[registry.gc] schedule`, printed —
not assumed — exactly as `BR-CLI-019` already requires for the reconcile timer.

## Doctor

**`BR-REG-011`** — `cairn-registry doctor` checks: the registry container reachable over HTTPS,
certificate validity, and free disk headroom under `data_dir` — the registry-specific checks
`BR-CLI-007` already carves out per-binary.
