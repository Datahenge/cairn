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
