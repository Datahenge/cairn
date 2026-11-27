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
| `OQ-007` | `open` | Should a `subdir` app's cache bust and input hash track only the folder's content, so a commit elsewhere in the repository does not rebuild the image? | `BR-BUILD-020` hashes the whole repository's commit, because `git ls-remote` cannot see a folder. Scoping it needs a fetch on the build host: a tree-only fetch (`git fetch --depth 1 --filter=tree:0`) and `git rev-parse <commit>:<subdir>` give the folder's tree id, which would replace the commit in the hash lines. That adds a network fetch per build and per `assign-tag` resolution. Raised by Life Scientific 2026-11-27, whose ERP monorepo holds other projects beside the app. Lean: ship whole-commit hashing now; add the tree id if rebuild churn proves costly | |
| `OQ-008` | `open` | Is `subdir` the right key name, and is the last part of the path the right folder name for the app? | `subdir` was chosen because no cairn document names this concept. Alternatives: `path`, `subdirectory`. bench names the app folder after the last part of `subdir`; the manifest `name` is the other candidate. They agree for Life Scientific's `apps/lifescientific`. Raised 2026-11-27 with `BR-BUILD-020` | |

`OQ-004`, `OQ-005`, and `OQ-006` were resolved and removed 2026-09-29, the day they were raised.
All three concerned build-machine retention, and their answers are authoritative elsewhere:
`OQ-004` (how the manifest reaches the image without an environment name) in `ADR-079` and
`BR-BUILD-011`; `OQ-005` (images predating the labels) in `BR-CLI-018`'s legacy exemption; and
`OQ-006` (the `require_pushed` default) in `BR-CFG-016`. `docs/CHANGELOG.md` carries the dated
narrative for each.

`OQ-001`, `OQ-002`, and `OQ-003` were resolved and removed 2026-08-06 — their answers are fully
captured in `ADR-061`, `ADR-065`, and `ADR-067` respectively, the requirement docs those ADRs
amended, and `docs/CHANGELOG.md`'s dated entries; nothing here would add information not already
authoritative elsewhere.

Unresolved architectural questions that already have a recorded lean live in
`docs/open/OPEN_DECISIONS.md` instead — this file is for questions that don't yet have one.

Resolved questions should move their answer into the relevant requirement document and be
noted in `docs/CHANGELOG.md`, then marked `resolved` here (or removed if no longer useful to
retain).
