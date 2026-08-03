---
status: authoritative
owner: technical
purpose: ADR-013 — Backup / restore / DB movement: OUT OF SCOPE
---

# ADR-013 — Backup / restore / DB movement: OUT OF SCOPE

**Decided:** 2026-07-24 (was: backup storage/retention/restic)
Backup, restore, and database movement are **out of scope** for cairn per `ADR-022`.
cairn does not create, store, retain, encrypt, restore, or relocate SQL backups. Any such
work belongs to the operator or to cofferdam. (Frappe's own `bench backup`/`restore`
remain available to operators independently of cairn.)
