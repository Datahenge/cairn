---
status: authoritative
owner: project
purpose: Short entry point for future sessions; routes to the smallest relevant document.
---

# Current Context

Use this file as the first context checkpoint. Keep it short — point to detailed docs instead of repeating them.

## Current Phase

Phase 4 (modular code) is under way, on the three-binary split (`cairn-build` / `cairn-adopt` /
`cairn-registry`, `ADR-046`/`ADR-048`) that replaced the unified `cairn` command and the
separate `cairn-provision` installer. Most recently landed: `ADR-052` (manifest:environment is
1:1; promotion is proof, found in the registry, not an assertion). Active work is `cairn-registry`
(`W-015`) and the first live run against real infrastructure — everything in the deploy path is
tested but unexercised on a real host or registry; see `open/OPEN_WORK.md`. Newly decided:
`ADR-059` retires `frappe_docker` vendoring in favor of cairn owning its Docker build recipe
outright, superseding `ADR-001`/`ADR-007`; the documentation cascade is done, the code
migration (renaming `src/cairn/vendored/` to `src/cairn/recipe/`, retiring the `ventwig`-backed
`vendor` command surface) is queued as separate `open/OPEN_WORK.md` items, not yet started. The docs tree itself
finished its migration onto the canonical Scribe Coding scaffold (`brian-pond/scribe_coding`) —
this file, `open/`, `scratch/`, `docs/technical/`, `docs/adr/`, `decisions/`, and
`docs/discussions/` are the result.

## Read First

| Task | Read |
| --- | --- |
| General project work | `docs/requirements/00-overview.md`, `AGENTS.md` |
| Writing or changing code | `docs/technical/00-coding-standards.md` |
| Requirements or scope work | `docs/requirements/00-overview.md`, `open/OPEN_QUESTIONS.md` |
| "What's done, what remains?" / implementation status | `docs/technical/05-implementation-index.md`, `open/OPEN_WORK.md`, `docs/plans/next-steps.md` |
| Architecture rationale | `docs/adr/README.md`, `decisions/README.md` |
| Pending decisions needing sign-off | `open/OPEN_DECISIONS.md` |
| Outstanding implementation or cleanup work | `open/OPEN_WORK.md` |
| Documentation ownership / what to read for topic X | `docs/technical/25-documentation-authority.md` |

## Standing Rules

- `BR`/`ADR` identifiers never reach a user — see `AGENTS.md` and `tests/test_conventions.py`.
- The data-plane boundary (`ADR-022`) is a hard invariant, not a preference — cairn cannot touch SQL.
- `src/cairn/recipe/frappe_docker/` is cairn's own Docker build recipe, freely edited by hand
  — no vendoring, no pin, no drift check (`ADR-059`).

## Context Rule

Do not scan the whole project by default. Read only what the current task's row above names.
