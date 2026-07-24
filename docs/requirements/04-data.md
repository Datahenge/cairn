# BR-DATA — Data-Plane Boundary Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-07-24_

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

**`BR-DATA-005`** *(sanctioned exception — automatic)* — Immediately after enabling a new
image + containers on a target environment, cairn MUST run `bench migrate` in a
subprocess. cairn treats it as **opaque** (invokes it, observes success/failure, never
inspects or influences what it does). `bench migrate` is non-destructive (never drops
columns/tables/indexes), hence safe in Production. It does **not** install new apps (see
`BR-DATA-008`). *(ADR-014)*

**`BR-DATA-006`** *(Feature 3 — cairn does not itself touch volumes)* — cairn MUST NOT
**itself** read, write, seed, provision, or modify persistent Docker volumes,
`site_config.json`, `common_site_config.json`, or `encryption_key`.

Note (accuracy): bringing up the stack **does** cause the volume to change — but by
**frappe_docker's own containers**, not by cairn. At every `compose up` the `configurator`
service runs `ls -1 apps > sites/apps.txt` (regenerating the bench app list from the
image), `bench set-config -g …` (refreshing `common_site_config.json`), and the backend
entrypoint relinks `sites/assets` to the image's baked assets. This is Frappe's machinery
reconciling the volume to the new image — the same "cairn invokes, Frappe acts" principle
as `bench migrate`. cairn performs **no volume writes of its own** and never hand-edits
these files. *(ADR-022; supersedes the seeding allowance formerly in `BR-CFG-006`)*

**`BR-DATA-007`** *(rollback is image-only)* — cairn's rollback reverts the **image**
(and re-points containers) only; it MUST NOT restore or roll back the database. Image
rollback and any data recovery are separate concerns, the latter outside cairn entirely.
*(ADR-012, ADR-022)*

**`BR-DATA-008`** *(sanctioned exception — opt-in only)* — Activating an app that is present
in the image but not yet installed on the target site requires `bench install-app`, which
`bench migrate` does **not** perform. cairn MAY run `bench install-app <apps>` on a target,
but **only via explicit opt-in — never by default**. A default deploy is code-swap +
`migrate` only and MUST NOT change a site's installed-app set (least surprise). Like
`migrate`, `install-app` is invoked **opaquely** (Frappe does the work). The opt-in
delivery mechanism (so the operator need not SSH in) is a `DEPLOY` concern, consistent with
the pull model (`ADR-005`/`ADR-006`). *(ADR-023)*

---

## Non-goals (explicit, for the avoidance of doubt)
Backup creation/retention/encryption; SQL restore; Prod→non-prod data refresh; site
creation (`bench new-site` writes a DB + config — operator's job); `encryption_key`
handling of any kind. All out of scope per `ADR-022`.

## Cross-references
- `bench migrate` sequencing (deploy, and on rollback) is specified under `DEPLOY`.
- Initial environment/site provisioning (fresh volumes) is the operator's responsibility;
  cairn deploys to **existing** environments (a `DEPLOY` scoping point).
