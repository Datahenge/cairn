---
status: authoritative
owner: project
purpose: Archived `done` rows swept from `open/OPEN_WORK.md`, preserved for historical reference.
---

# Open Work — Completed

Rows removed from [`open/OPEN_WORK.md`](../../open/OPEN_WORK.md) once `done` and their
completion judgment was recorded in
[`docs/technical/05-implementation-index.md`](../technical/05-implementation-index.md), per
`OPEN_WORK.md`'s own rule: "Sweep `done` rows out on the next cleanup pass... This file tracks
what's outstanding, not a permanent record of everything ever finished." This file is that
permanent record, kept verbatim as of the sweep date rather than updated further.

## Swept 2026-08-04

| ID | Status | Area | Work | Notes / Links |
| --- | --- | --- | --- | --- |
| `W-016` | `done` | `CFG`, `CLI` | **Superseded by `W-019`/`ADR-052` the same day.** The `[cairn.environments]` → `[cairn.declared_environments]` rename (`ADR-049`) landed 2026-08-04, but the table itself (any name) is retired hours later by `ADR-052` in favor of a scalar `[cairn] environment` field. Left `done` as a true record of what was implemented and verified at the time — the table shape it produced no longer exists in the codebase. | `decisions/049-...md` (now archived); superseding work is `W-019` |
| `W-017` | `done` | `CLI` | **Superseded by `W-019`/`ADR-052` the same day.** The `new-tag`/`retag` → `assign-tag` merge (`ADR-050`) landed 2026-08-04, but its selector menu (`--latest`/`--previous`/`--id`/`--from`) and positional `<env>` argument are retired hours later by `ADR-052` in favor of a no-build resolve-and-check operation taking `--manifest`. The `setup_runner.execute` `verb` param fix (drive-by, unrelated to the selector design) stands unaffected. Left `done` as a true record of what was implemented and verified at the time. | `docs/adr/050-...md` (now archived); superseding work is `W-019` |

## Swept 2026-08-05

| ID | Status | Area | Work | Notes / Links |
| --- | --- | --- | --- | --- |
| `W-001` | `done` | `DEPLOY` | First live deployment: decide registry → `cairn-build setup`/`cairn-adopt setup` → `cairn-build build --push` → `cairn-build new-tag` → `cairn-adopt reconcile` on a real VPS, in that reversible order | Done 2026-08-05, with a real caveat: the target's pre-existing compose file didn't consume `CUSTOM_IMAGE`/`CUSTOM_TAG` for any service (fork-pressure register item 4, `ADR-021`), so the first `reconcile` falsely reported convergence — see `docs/technical/05-implementation-index.md`'s Reconcile/deploy row and `W-022` (still open). Compose file hand-fixed, convergence confirmed by `docker inspect`, a subsequent real `reconcile` correctly reported `Already running` |
| `W-002` | `done` | `CLI`, `DEPLOY` | Exercise `cairn-adopt doctor`'s target-role checks against a real target post-`ADR-046` split | Verified live 2026-08-05 against the same target — all 6 checks (descriptor, docker, compose, reconcile timer, registry, shared config) pass, both before and after descriptor install |
| `W-007` | `done` | `DOCS` | Decide whether `USAGE.md` is still needed separately from `README.md`, or was superseded by it | Closed 2026-08-05 — never written; superseded by the published user-facing docs on GitHub Pages (`userdocs/` → `https://datahenge.github.io/cairn/`, `ADR-045`), which already cover installation and per-role walkthroughs. `docs/archive/next-steps.md` §5 |
| `W-010` | `done` | `VEND` | Measure fork-pressure register item 1: time a rebuild after a single custom-app commit, against a first build | Closed 2026-08-05 — measurement superseded by `ADR-059`; cairn now owns the recipe outright, no fork-vs-no-fork decision to gate |
