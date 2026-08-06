---
status: authoritative
owner: technical
purpose: ADR-053 — the registry role splits /etc/cairn (config + secrets) from /opt/cairn-registry (compose project + relocatable data)
---

# ADR-053 — the registry role splits `/etc/cairn` (config + secrets) from `/opt/cairn-registry` (compose project + relocatable data)

> **Amended by `ADR-060`** (2026-08-05): the FHS citation below for `/opt` as the default
> *data* location was wrong — `/opt` is for a program's own installed files, `/var/lib` is
> FHS's home for a service's growing runtime state. The default `data_dir` moved to
> `/var/lib/cairn-registry`. The split described here (low-churn shared config vs. relocatable
> bulk data) is otherwise unchanged, and `/opt/cairn-registry` still holds the compose project.

**Decided:** 2026-08-04 (retroactively — capturing a layout already implemented in
`registry_provision.py`, raised by Brian after reviewing a real `cairn-registry setup
--dry-run`, who asked whether maintaining two directories was worth it versus one).

**The layout.** `cairn-registry setup` writes to two separate places:

- **`/etc/cairn`** — `registry.toml` (`BR-REG-002`) and the TLS certificate/key
  (`BR-REG-003`). Shared with the `cairn-admins` group, mode `2775` (`ADR-043`); the key
  itself stays owner-only, `0600` (`BR-DEPLOY-021` rule 4).
- **`/opt/cairn-registry`** — the `docker compose` project file, plus `data_dir` (image
  blobs), which defaults under the same tree but is fully operator-relocatable
  (`registry_config.py`).

**Decision:** keep the split. Consolidating into one directory was considered and rejected.

**Why.** The two directories hold two different kinds of thing, and conflating them would cost
something real either way:

- `/etc/cairn` is the *machine-shared, low-churn configuration* home already established for
  every other role — `builder.toml`, the target's environment descriptor, and now
  `registry.toml`/its cert all live there so an operator has exactly one place to look for
  "how is this machine configured" (`ADR-042`, `ADR-043`). It also carries the one piece of
  secret material any role writes — the registry's private key — which needs owner-only
  permissions regardless of the directory's shared group.
- `/opt/cairn-registry` holds the compose project and, by default, `data_dir` — and `data_dir`
  is deliberately **operator-relocatable**, not fixed (`BR-REG-003`'s bind-mount, replacing an
  anonymous Docker volume as the original complaint this fixed). Image blobs can grow to many
  GB; an operator needs to be able to point them at a separate disk without fighting a
  directory whose whole contract is "shared config lives here, and only here." Defaulting
  multi-GB data under `/etc` would also risk filling whatever (often small) volume host
  configuration lives on.

Put plainly: secrets and small shared config in one place, relocatable bulk data in another.
This mirrors ordinary FHS convention (`/etc` = configuration, `/opt` = self-contained
application data) rather than inventing a cairn-specific scheme — reused deliberately, since a
reader already familiar with Linux layout conventions gets the split for free.

**Alternative considered.** A single directory (e.g. everything under `/etc/cairn/registry/`,
or a new `/var/lib/cairn-registry` holding both config and data). Rejected: it would either put
bulk, growing image storage under a path whose contract is "small, shared, low-churn" (`/etc`),
or require `data_dir` to still be independently configurable anyway — at which point the
"consolidation" buys nothing, since the two kinds of content still need two independently
addressable locations; only their common parent would change.

**Scope.** No code change — this documents the layout `registry_provision.py` (`CERT_DIR`,
`PROJECT_DIR`) and `registry_config.py` (`data_dir`) already implement. *(BR-REG-002,
BR-REG-003, ADR-042, ADR-043, ADR-048)*
