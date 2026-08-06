---
status: authoritative
owner: technical
purpose: ADR-068 — decisions/, open/, and scratch/ nest under docs/; CURRENT_CONTEXT.md and tools/ move into a new root-level ai/ directory
---

# ADR-068 — `decisions/`, `open/`, `scratch/` nest under `docs/`; `CURRENT_CONTEXT.md`/`tools/` move into `ai/`

**Decided:** 2026-08-06 (Brian, project-root cleanup).

## Raised

Brian asked for a root-directory cleanup: `decisions/`, `open/`, and `scratch/` sat as siblings
of `docs/` at the repo root even though every other durable-documentation tree (`docs/adr/`,
`docs/technical/`, `docs/requirements/`, `docs/discussions/`, `docs/plans/`, `docs/archive/`)
already lived under it — an artifact of the canonical Scribe Coding scaffold
(`brian-pond/scribe_coding`), not a deliberate split. Separately, `CURRENT_CONTEXT.md` and
`tools/` (the docs-hygiene scripts) are surface meant for an AI agent's own use at the start of
a session, not part of the documentation itself.

## Decision

**Nest `decisions/`, `open/`, and `scratch/` under `docs/`** — `docs/decisions/`, `docs/open/`,
`docs/scratch/` — so every documentation tree shares one root. No tree's role, audience, or
status semantics change; only their path depth does.

**Move `CURRENT_CONTEXT.md` and `tools/` into a new root-level `ai/` directory** —
`ai/CURRENT_CONTEXT.md`, `ai/tools/` — separating the AI-agent-facing session-router and
docs-hygiene tooling from `docs/`, which remains the project's documentation regardless of who
reads it.

This is a deliberate, intentional departure from the canonical Scribe Coding scaffold, recorded
here per `docs/technical/25-documentation-authority.md`'s existing "Deviations From The
Canonical Scribe Coding Template" section, not a fork of the method itself.

## Consequences

- Every relative Markdown link whose depth changed was corrected in the same change
  (`ai/tools/docs_check.py` confirms none are broken).
- `AGENTS.md`'s artifact table, `ai/CURRENT_CONTEXT.md`, and
  `docs/technical/25-documentation-authority.md`'s Doc Trees/Authority tables and Deviations
  section were updated to the new paths in the same change.
- `ai/tools/docs_check.py`'s `check_index_status_drift` now reads `docs/decisions/README.md`
  instead of `decisions/README.md`.
- No code under `src/cairn/` references any of these paths — this is a documentation- and
  tooling-only reorganization; the installed package is unaffected.
- Historical narrative in `docs/CHANGELOG.md` and `docs/archive/**` was left as originally
  written (it describes what was true at the time), except where it contained an actual
  Markdown link that would otherwise break.

*(no `BR-*` requirement affected)*
