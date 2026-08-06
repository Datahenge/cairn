---
status: authoritative
owner: technical
purpose: Defines the archive area for superseded or historical material.
---

# Archive

Historical material only — fully superseded ADRs and decisions, moved here in full once
retired, with a forwarding stub left at their original `docs/adr/` or `docs/decisions/` path so
existing citations keep resolving. Also holds archived tails of otherwise-live documents
(e.g. `docs/CHANGELOG.md`) split off purely for size, not because the content is superseded.

Do not load archived material for active work unless historical context is specifically
needed.

## Index — superseded ADRs/decisions

| File | Was | Superseded by |
|---|---|---|
| [023-opt-in-bench-install-app-never-automatic.md](023-opt-in-bench-install-app-never-automatic.md) | `ADR-023` | `ADR-037` |
| [028-cairn-doctor-is-role-aware-detected-from-context.md](028-cairn-doctor-is-role-aware-detected-from-context.md) | `ADR-028` | `ADR-046` |
| [041-the-machine-build-config-file-is-named-builder-toml-not-config.md](041-the-machine-build-config-file-is-named-builder-toml-not-config.md) | `ADR-041` (in `docs/decisions/`) | `ADR-042` |
| [033-the-declared-environment-list-is-a-cairn-environments-table-in.md](033-the-declared-environment-list-is-a-cairn-environments-table-in.md) | `ADR-033` | `ADR-052` |
| [049-the-declared-environment-list-is-cairn-declared-environments-not.md](049-the-declared-environment-list-is-cairn-declared-environments-not.md) | `ADR-049` (in `docs/decisions/`) | `ADR-052` |
| [050-new-tag-and-retag-merge-into-assign-tag.md](050-new-tag-and-retag-merge-into-assign-tag.md) | `ADR-050` | `ADR-052` |
| [057-target-descriptor-splits-registry-host-from-image.md](057-target-descriptor-splits-registry-host-from-image.md) | `ADR-057` (in `docs/decisions/`) | `ADR-058` |
| [001-wrap-frappe-docker-never-modify-it.md](001-wrap-frappe-docker-never-modify-it.md) | `ADR-001` | `ADR-059` |
| [007-vendoring-via-ventwig-committed-drift-checked.md](007-vendoring-via-ventwig-committed-drift-checked.md) | `ADR-007` | `ADR-059` |
| [020-strengthen-upstream-pin-immutability-ventwig-enhancement.md](020-strengthen-upstream-pin-immutability-ventwig-enhancement.md) | `ADR-020` | `ADR-059` (moot) |
| [021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md](021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md) | `ADR-021` | `ADR-059` |

## Index — archived-for-size

| File | Archived from | Covers |
|---|---|---|
| [CHANGELOG-2026-07.md](CHANGELOG-2026-07.md) | `docs/CHANGELOG.md` | Dated entries 2026-07-21 through 2026-07-27 |
| [CHANGELOG-2026-08-03.md](CHANGELOG-2026-08-03.md) | `docs/CHANGELOG.md` | Dated entries 2026-08-03 |
| [CHANGELOG-2026-08-04-early.md](CHANGELOG-2026-08-04-early.md) | `docs/CHANGELOG.md` | Earlier 2026-08-04 entries (`setup` engine-detection fix through `CONFIGURATION.md` retirement) |
| [CHANGELOG-2026-08-04.md](CHANGELOG-2026-08-04.md) | `docs/CHANGELOG.md` | Dated entries 2026-08-04 |
| [CHANGELOG-2026-08-04-to-2026-08-05.md](CHANGELOG-2026-08-04-to-2026-08-05.md) | `docs/CHANGELOG.md` | Dated entries 2026-08-04 through 2026-08-05 |

## Index — archived open-work

| File | Archived from | Covers |
|---|---|---|
| [OPEN_WORK-done.md](OPEN_WORK-done.md) | `docs/open/OPEN_WORK.md` | `done` rows swept out once their completion judgment was recorded in `docs/technical/05-implementation-index.md` |

## Index — archived plans

| File | Archived from | Covers |
|---|---|---|
| [next-steps.md](next-steps.md) | `docs/plans/next-steps.md` | Session-resumption plan, `status: archived` since 2026-08-03 — its live-backlog role was absorbed into `docs/open/OPEN_WORK.md`; moved here 2026-08-05 purely to stop it loading for ordinary "what's done, what remains" questions, which `docs/technical/05-implementation-index.md` + `docs/open/OPEN_WORK.md` already answer |
| [phase-1-build.md](phase-1-build.md) | `docs/plans/phase-1-build.md` | Early Phase-1 build-pillar plan, `status: archived` since 2026-07-24 (superseded in part by `docs/requirements/` and later ADRs) — moved here 2026-08-06, closing `W-011`, which had sat open since Phase 4 began asking for exactly this move |
