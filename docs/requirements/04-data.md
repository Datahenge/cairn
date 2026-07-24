# BR-DATA — Data-Plane Boundary Requirements

_Status: living · drafted (Pass 1) · Last updated: 2026-07-24_

`DATA` is a **boundary area**, not a feature area. cairn ships **code**, not data. The
data plane (SQL, persistent volumes, site configs, encryption keys) is **off-limits**;
these requirements are almost entirely prohibitions, with one sanctioned exception.

Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-012`, `ADR-013`, `ADR-014`,
`ADR-019`, `ADR-022`.

---

**`BR-DATA-001`** — cairn MUST NOT connect to any SQL database directly (no SQL client,
no DB driver, no credentials handling). *(ADR-022)*

**`BR-DATA-002`** — cairn MUST NOT run `bench execute`, `frappe` library code, or any
arbitrary data-manipulation command. *(ADR-022)*

**`BR-DATA-003`** — cairn MUST NOT export, import, restore, relocate, or otherwise move
SQL data between environments. Database movement is **out of scope** (cofferdam's / the
operator's domain). *(ADR-013, ADR-022)*

**`BR-DATA-004`** *(Prime Directive)* — cairn MUST NOT directly alter any target database,
and this MUST be **impossible by construction**: no code path, SQL client, or
data-manipulation capability exists in cairn. This applies to **all** environments;
Production is not special-cased because the capability does not exist. *(ADR-022)*

**`BR-DATA-005`** *(the sole sanctioned exception)* — Immediately after enabling a new
image + containers on a target environment, cairn MUST run `bench migrate` in a
subprocess. This is the only DB interaction cairn performs, and only *indirectly* — Frappe
does the work. cairn treats it as **opaque** (invokes it, observes success/failure, never
inspects or influences what it does). `bench migrate` is non-destructive (never drops
columns/tables/indexes), hence safe in Production. *(ADR-014)*

**`BR-DATA-006`** *(Feature 3 — volumes/configs untouched)* — cairn MUST NOT read, write,
seed, provision, or modify persistent Docker volumes, `site_config.json`,
`common_site_config.json`, or `encryption_key`. It is *aware* these exist solely to leave
them intact; an image/container swap MUST leave the data-plane volume entirely untouched.
*(ADR-022; supersedes the seeding allowance formerly in `BR-CFG-006`)*

**`BR-DATA-007`** *(rollback is image-only)* — cairn's rollback reverts the **image**
(and re-points containers) only; it MUST NOT restore or roll back the database. Image
rollback and any data recovery are separate concerns, the latter outside cairn entirely.
*(ADR-012, ADR-022)*

---

## Non-goals (explicit, for the avoidance of doubt)
Backup creation/retention/encryption; SQL restore; Prod→non-prod data refresh; site
creation (`bench new-site` writes a DB + config — operator's job); `encryption_key`
handling of any kind. All out of scope per `ADR-022`.

## Cross-references
- `bench migrate` sequencing (deploy, and on rollback) is specified under `DEPLOY`.
- Initial environment/site provisioning (fresh volumes) is the operator's responsibility;
  cairn deploys to **existing** environments (a `DEPLOY` scoping point).
