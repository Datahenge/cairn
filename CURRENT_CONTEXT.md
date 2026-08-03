---
status: authoritative
owner: project
purpose: Short entry point for future sessions; routes to the smallest relevant document.
---

# Current Context

Use this file as the first context checkpoint. Keep it short — point to detailed docs instead of repeating them.

## Current Phase

Phase 4 (modular code) is under way. The `cairn-build` / `cairn-adopt` two-binary split (`ADR-046`)
just landed, replacing the unified `cairn` command and the separate `cairn-provision` installer
(folded into each CLI's own `setup` subcommand). The docs tree itself is mid-migration onto the
canonical Scribe Coding scaffold (`brian-pond/scribe_coding`) — this file, `open/`, `scratch/`,
`docs/technical/`, `docs/adr/`, `decisions/`, and `docs/discussions/` are new as of that migration.

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
- `src/cairn/vendored/frappe_docker/` is never edited by hand; only `cairn-build vendor sync`
  may change it.

## Context Rule

Do not scan the whole project by default. Read only what the current task's row above names.
