---
status: authoritative
owner: requirements
purpose: BR-DATA requirements — the data-plane boundary cairn must never cross.
---

# BR-DATA — Data-Plane Boundary Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-08-03_

`DATA` is a **boundary area**, not a feature area: cairn ships code, not data. These
requirements are almost entirely prohibitions, with one sanctioned Frappe-command
exception (`migrate`) and one activation gap that is always the operator's, never
cairn's (`install-app`). Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-012`,
`ADR-013`, `ADR-014`, `ADR-022`, `ADR-023`, `ADR-037`.

---

**`BR-DATA-001`** — cairn MUST NOT connect to any SQL database directly (no SQL client, DB
driver, or credentials handling). *(ADR-022)*

**`BR-DATA-002`** — cairn MUST NOT run `bench execute`, `frappe` library code, or any
arbitrary data-manipulation command. *(ADR-022)*

**`BR-DATA-003`** — cairn MUST NOT export, import, restore, relocate, or otherwise move SQL
data between environments. *(ADR-013, ADR-022)*

**`BR-DATA-004`** *(Prime Directive)* — cairn MUST NOT directly alter any target database;
this MUST be **impossible by construction** (no code path or SQL capability exists), for
**all** environments. *(ADR-022)*

**`BR-DATA-005`** *(sanctioned exception — automatic)* — Immediately after enabling a new
image + containers on a target, cairn MUST run `bench migrate` in a subprocess, treating it
**opaquely** (invoke, observe success/failure, never inspect or influence). It does not
install new apps (`BR-DATA-008`). *(ADR-014)*

**`BR-DATA-006`** *(cairn does not itself touch volumes)* — cairn MUST NOT itself read,
write, seed, provision, or modify persistent Docker volumes, `site_config.json`,
`common_site_config.json`, or `encryption_key`. (The stack's own configurator/entrypoint
reconcile the volume on `compose up` — that is Frappe's machinery, not cairn.) *(ADR-022;
supersedes the seeding allowance formerly in `BR-CFG-006`)*

**`BR-DATA-007`** *(rollback is image-only)* — cairn's rollback reverts the image (and
re-points containers) only; it MUST NOT restore or roll back the database. *(ADR-012, ADR-022)*

**`BR-DATA-008`** *(a known gap — always the operator's, never cairn's)* — Activating a
Frappe App that ships in a newly-deployed image but was never previously installed on the
target site requires `bench install-app` (which `migrate` does not do — migrate only patches
apps already installed). cairn MUST NOT run it, under any flag or directive, automatically or
opt-in (`BR-DEPLOY-003a`, superseding the opt-in path `ADR-023` originally proposed — `ADR-037`
struck it entirely once implementation showed nothing could carry the directive across a
reconcile loop). The operator runs it **by hand** against the live site, exactly as initial
site creation is the operator's act (`BR-DEPLOY-007`). *(BR-DEPLOY-003a, BR-DEPLOY-007,
ADR-037)*

---

## Non-goals (out of scope per `ADR-022`)
Backup creation/retention/encryption; SQL restore; Prod→non-prod data refresh; site
creation (`bench new-site`); any `encryption_key` handling.

## Cross-references
- `bench migrate` / `install-app` sequencing is specified under `DEPLOY`.
- Initial environment/site provisioning is the operator's responsibility; cairn deploys to
  **existing** environments.
