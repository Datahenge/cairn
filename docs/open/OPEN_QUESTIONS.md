---
status: active
owner: project
purpose: Unresolved discovery and validation questions that need the user's answer before requirements can be finalized.
---

# Open Questions

Do not infer answers to these from general knowledge or unstated preference. Ask Brian.

## Status Values

| Status | Meaning |
| --- | --- |
| `open` | Question is unanswered. |
| `resolved` | Answered; the answer has been moved into the relevant requirement document. |

## Queue

| ID | Status | Question | Context | Answer |
|---|---|---|---|---|

None open currently. `OQ-001`, `OQ-002`, and `OQ-003` were resolved and removed 2026-08-06 —
their answers are fully captured in `ADR-061`, `ADR-065`, and `ADR-067` respectively, the
requirement docs those ADRs amended, and `docs/CHANGELOG.md`'s dated entries; nothing here would
add information not already authoritative elsewhere.

Unresolved architectural questions that already have a recorded lean live in
`docs/open/OPEN_DECISIONS.md` instead — this file is for questions that don't yet have one.

Resolved questions should move their answer into the relevant requirement document and be
noted in `docs/CHANGELOG.md`, then marked `resolved` here (or removed if no longer useful to
retain).
