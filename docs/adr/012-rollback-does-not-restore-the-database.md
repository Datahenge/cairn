---
status: authoritative
owner: technical
purpose: ADR-012 — Rollback does NOT restore the database
---

# ADR-012 — Rollback does NOT restore the database

**Decided:** 2026-07-21
`cairn rollback` reverts the **image** (and restarts/re-points the stack) only. It
does **not** restore a DB snapshot. Image rollback and DB restore are separate,
deliberate verbs the operator composes explicitly.

**Rationale:** Production data is fast-moving; auto-restoring a SQL backup on rollback
would silently discard live transactions. Restoring SQL must be a deliberate,
manual last resort — never a side effect of flipping images.

Harm from an image/schema mismatch is bounded by Frappe/ERPNext behavior: a normal
`bench migrate` does **not** drop SQL tables or columns. So even when a rolled-back
image's DocType/DocField JSON no longer matches the live MariaDB schema, the extra
columns/tables simply sit unused rather than causing data loss — making image-only
rollback safe by default.

**Superseded in part by `ADR-022`:** an earlier version of this consequence had cairn
snapshot before a forward migration. `ADR-022` (data-plane boundary) removed that — cairn
performs **no** snapshot or any data handling. The core decision (rollback reverts the image
only, never the database) stands, and is stronger under `ADR-022`.
