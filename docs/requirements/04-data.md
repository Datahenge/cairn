# BR-DATA — Data-Plane Boundary Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-07-24_

`DATA` is a **boundary area**, not a feature area: cairn ships code, not data. These
requirements are almost entirely prohibitions, with two sanctioned Frappe-command
exceptions. Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-012`, `ADR-013`, `ADR-014`,
`ADR-022`, `ADR-023`.

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

**`BR-DATA-008`** *(sanctioned exception — opt-in only)* — Activating an app present in the
image but not yet installed on the target site requires `bench install-app` (which `migrate`
does not do). cairn MAY run `bench install-app <apps>` on a target, but **only via explicit
opt-in — never by default**; a default deploy MUST NOT change a site's installed-app set.
`install-app` is invoked opaquely. Delivery mechanism is a `DEPLOY` concern. *(ADR-023)*

---

## Non-goals (out of scope per `ADR-022`)
Backup creation/retention/encryption; SQL restore; Prod→non-prod data refresh; site
creation (`bench new-site`); any `encryption_key` handling.

## Cross-references
- `bench migrate` / `install-app` sequencing is specified under `DEPLOY`.
- Initial environment/site provisioning is the operator's responsibility; cairn deploys to
  **existing** environments.
