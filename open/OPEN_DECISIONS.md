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
[../docs/adr/](../docs/adr/) or [../decisions/](../decisions/), carrying this ID forward so a
citation made while it was open still resolves. Do not treat chat-only approval as durable
unless it is also reflected here, in a `decisions/` record, or in an ADR.

The full analysis behind each row below already exists as a complete, `status: exploratory`
file in `docs/adr/` (not condensed here) — these rows exist for live-tracking visibility only.

## Queue

| ID | Status | Area | Decision needed | Recommendation / trigger | Full record |
|---|---|---|---|---|---|
| `ADR-020` | `deferred` | `VEND` | Strengthen upstream-pin immutability in ventwig (SHA pinning and/or re-sync verification) | Ventwig enhancement, not a cairn blocker; at minimum add re-sync verification | [../docs/adr/020-strengthen-upstream-pin-immutability-ventwig-enhancement.md](../docs/adr/020-strengthen-upstream-pin-immutability-ventwig-enhancement.md) |
| `ADR-021` | `deferred` | `VEND` | Whether to fork `frappe_docker` as an escape hatch for hard commit-pinning | Deferred until a concrete, essential need is evidenced — see the fork-pressure register in the full record | [../docs/adr/021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md](../docs/adr/021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md) |
| `ADR-044` | `deferred` | `BUILD` | Whether to add a local git mirror for private-app reachability, replacing the PAT-based auth `BR-BUILD-016` already ships | Deferred — revisit only if PAT-based auth proves insufficient for a client | [../docs/adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md](../docs/adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md) |
| `DOCS-01` | `approved` | `DOCS` | `docs/technical/ABOUT_GHCR.md` (~3,200 words) has a clean split into setup / ownership-and-cost / tags-and-troubleshooting sub-topics. `docs/CHANGELOG.md` (2026-08-03, `ADR-045` entry) already records that this file — along with `README.md`, `CONFIGURATION.md`, `ABOUT_REGISTRIES.md` — is slated for eventual migration into the `userdocs/` mkdocs nav as separate future work. Split it now in `docs/technical/` (risks being redone at migration time), defer any restructuring until that migration, or split it now shaped deliberately to become the future mkdocs pages directly? | Decided 2026-08-04, by precedent from `CONFIGURATION.md`'s migration (see `docs/CHANGELOG.md`): don't pre-split in `docs/technical/` — defer, and when `ABOUT_GHCR.md`'s own migration is undertaken, split it directly into its future `userdocs/` page shape (setup / ownership-and-cost / tags-and-troubleshooting), skipping an intermediate `docs/technical/` split that would just be redone. Not yet implemented — trigger is `ABOUT_GHCR.md`'s own migration work. | — |
