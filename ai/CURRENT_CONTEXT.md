---
status: authoritative
owner: project
purpose: Short entry point for future sessions; routes to the smallest relevant document.
---

# Current Context

Use this file as the first context checkpoint. Keep it short — point to detailed docs instead of repeating them.

## Current Phase

**Phase 4 — modular code.** Three binaries (`ADR-046`, `ADR-048`), no unified `cairn` command:
`cairn-build` (build/control), `cairn-adopt` (target), `cairn-registry` (registry host). The
binary invoked *is* the role signal.

Standing shape a session should know before reading anything else:

| | |
| --- | --- |
| Build recipe | cairn **owns** `src/cairn/recipe/` outright — no vendoring, no pin, no drift check (`ADR-059`) |
| Target compose file | cairn writes the **first** one and never regenerates it; the operator owns it thereafter (`ADR-074`) |
| Operating a target | the operator never runs `docker compose` directly — cairn provides the verbs (`ADR-073`, `ADR-075`) |
| Data plane | off-limits; the sole DB touch is `bench migrate` (`ADR-022`) |

**Live reference target:** Life Scientific's test VPS, running `0.4.12`. Its compose file is a
`pwd.yml` descendant the client built before cairn existed, now manually relocated to
`/etc/cairn/` — the first host in `ADR-074`'s shape, and the working reference for what
`W-033`'s automated take-ownership path should produce.

**What is in flight:** read `docs/open/OPEN_WORK.md` (backlog) and
`docs/technical/05-implementation-index.md` (what is built, and what is unverified against a
real host). Do not infer status from this file.

> **This section records standing state only.** Narrative history — what landed when, and why —
> belongs in `docs/CHANGELOG.md`, and is not repeated here. Compacted 2026-08-19 after the
> section had accreted into a second changelog roughly eight times the length this file's own
> header asks for; keep it that way.

## Read First

| Task | Read |
| --- | --- |
| General project work | `docs/requirements/00-overview.md`, `AGENTS.md` |
| Writing or changing code | `docs/technical/00-coding-standards.md` |
| Requirements or scope work | `docs/requirements/00-overview.md`, `docs/open/OPEN_QUESTIONS.md` |
| "What's done, what remains?" / implementation status | `docs/technical/05-implementation-index.md`, `docs/open/OPEN_WORK.md` |
| Architecture rationale | `docs/adr/README.md`, `docs/decisions/README.md` |
| Pending decisions needing sign-off | `docs/open/OPEN_DECISIONS.md` |
| Outstanding implementation or cleanup work | `docs/open/OPEN_WORK.md` |
| Documentation ownership / what to read for topic X | `docs/technical/25-documentation-authority.md` |

## Standing Rules

- `BR`/`ADR` identifiers never reach a user — see `AGENTS.md` and `tests/test_conventions.py`.
- The data-plane boundary (`ADR-022`) is a hard invariant, not a preference — cairn cannot touch SQL.
- `src/cairn/recipe/` is cairn's own Docker build recipe, freely edited by hand — no
  vendoring, no pin, no drift check (`ADR-059`).
- Removing a silent default surfaces everything that quietly depended on it. Search for other
  readers **before** shipping that kind of change — `BR-VEND-006` was correct and still broke a
  live client VPS, because three read-path probes had been relying on the default it removed.

## Context Rule

Do not scan the whole project by default. Read only what the current task's row above names.
