---
status: active
owner: project
purpose: Central queue for decisions that need explicit user approval before becoming durable project behavior.
---

# Open Decisions

## Status Values

| Status | Meaning |
| --- | --- |
| `needs_user` | Waiting on Brian's explicit choice. |
| `approved` | Decided; not yet promoted into a permanent record. |
| `rejected` | Considered and declined. |
| `deferred` | Acknowledged and tracked, but deliberately not acted on until a named trigger condition. |
| `implemented` | Approved and reflected in a permanent record + code. |

Once approved and implemented, a decision is promoted into a numbered record in
[../adr/](../adr/) or [../decisions/](../decisions/), carrying this ID forward so a
citation made while it was open still resolves. Do not treat chat-only approval as durable
unless it is also reflected here, in a `decisions/` record, or in an ADR.

The full analysis behind each row below already exists as a complete, `status: exploratory`
file in `docs/adr/` (not condensed here) — these rows exist for live-tracking visibility only.

## Queue

| ID | Status | Area | Decision needed | Recommendation / trigger | Full record |
|---|---|---|---|---|---|
| `ADR-044` | `deferred` | `BUILD` | Whether to add a local git mirror for private-app reachability, replacing the PAT-based auth `BR-BUILD-016` already ships | Deferred — revisit only if PAT-based auth proves insufficient for a client | [../adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md](../adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md) |

`ADR-020` and `ADR-021` were resolved 2026-08-05 by `ADR-059` (cairn owns its Docker build
recipe outright; the ventwig pin and the fork question are both moot) and removed from this
queue — see [../adr/059-cairn-owns-its-docker-build-recipe-frappe-docker-vendoring-retired.md](../adr/059-cairn-owns-its-docker-build-recipe-frappe-docker-vendoring-retired.md).
