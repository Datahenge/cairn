---
status: authoritative
owner: technical
purpose: ADR-014 — `bench migrate` is the sole sanctioned DB interaction
---

# ADR-014 — `bench migrate` is the sole sanctioned DB interaction

**Decided:** 2026-07-24
After enabling a new image + containers on a target environment, cairn **MUST** run
`bench migrate` in a subprocess. This is *indirect* — Frappe performs the work.

**Superseded in part by `ADR-037`:** an earlier version of this decision named opt-in
`bench install-app` (`ADR-023`) as a second sanctioned interaction. `ADR-037` struck that
clause entirely — cairn never installs an app. `bench migrate` is now the **sole** sanctioned
DB interaction, automatic or otherwise.

**Why it is required and safe:**
1. **Required** — Frappe demands it after any app change; skipping it leaves code assuming
   a schema that doesn't exist (a *worse*, broken state).
2. **Sanctioned** — it is a normal Frappe command runnable anytime from a terminal; *what*
   it does and *how* are Frappe's business, not cairn's. cairn's only job is to call it.
3. **Non-destructive** — `bench migrate` never drops columns, tables, or indexes (dropping
   requires explicit opt-in). It creates new SQL objects and leaves the rest intact, so it
   is safe to run in Production. Patches run because Frappe says they should.

cairn treats `bench migrate` as opaque: it invokes it and observes success/failure, but
never inspects or influences what it does. Sequencing (incl. on rollback) is a `DEPLOY`
concern. Supersedes the earlier "orchestrate with pre-migrate snapshot" lean (no snapshot
— that would be data handling, forbidden by `ADR-022`).
