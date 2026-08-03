---
status: authoritative
owner: technical
purpose: Maps which cairn documents own each topic and defines reading order.
---

# Documentation Authority Map

> Review date: 2026-08-03.

This document defines which project documents own which topics, to prevent duplicated rules,
stale parallel summaries, and unnecessary context loading.

## Principle

Write each rule once in its owner document. Other documents link to the owner or carry only a
thin audience-specific summary.

## Doc Trees

| Tree | Path | Audience |
|---|---|---|
| Project scope | [../00-project-scope.md](../00-project-scope.md) | Purpose, pillars, principles — read before requirements |
| Requirements | [../requirements/](../requirements/) | Implementation and validation source |
| Technical | [technical/](.) | Implementation/configuration/operations details |
| ADRs | [adr/](../adr/) | Consequential decisions and rationale |
| Decisions | [../../decisions/](../../decisions/) | Lighter-weight dated decisions |
| Discussions | [discussions/](../discussions/) | Informal write-ups; not authoritative, not required reading |
| Open | [../../open/](../../open/) | Live queues/trackers: open questions, decisions, work |
| Scratch | [../../scratch/](../../scratch/) | Temporary notes; promote or delete, never authoritative |
| Archive | [archive/](../archive/) | Historical only |
| Plans | [../plans/](../plans/) | Narrative implementation plans, downstream of requirements (cairn-specific; see Deviations) |
| Published site | [../../userdocs/](../../userdocs/) | End-user/operator docs, published via mkdocs-material (`ADR-045`) — the only tree a user ever sees |

## Authority By Topic

| Topic | Authority |
|---|---|
| Project purpose, pillars, what it is/isn't | [../00-project-scope.md](../00-project-scope.md) |
| Requirements index, identifiers, table of contents | [../requirements/00-overview.md](../requirements/00-overview.md) |
| Per-area requirements | [../requirements/](../requirements/) (`01-vendoring.md` … `07-docs.md`) |
| Documentation revision history (requirements + decisions + discussion) | [../CHANGELOG.md](../CHANGELOG.md) |
| Software release history | [../../CHANGELOG.md](../../CHANGELOG.md) |
| Open discovery/validation questions | [../../open/OPEN_QUESTIONS.md](../../open/OPEN_QUESTIONS.md) |
| Pending/deferred decisions | [../../open/OPEN_DECISIONS.md](../../open/OPEN_DECISIONS.md) |
| Outstanding implementation/cleanup work | [../../open/OPEN_WORK.md](../../open/OPEN_WORK.md) |
| Consequential architecture/process decisions | [adr/](../adr/) |
| Lightweight dated decisions | [../../decisions/](../../decisions/) |
| Coding standards, naming, lint/format tooling, design patterns | [00-coding-standards.md](00-coding-standards.md) |
| Documentation conventions and Markdown headers | [01-documentation-conventions.md](01-documentation-conventions.md) |
| Dorwin Analysis / Hardin Version compression technique | [02-dorwin-analysis-and-hardin-version.md](02-dorwin-analysis-and-hardin-version.md) |
| Durable technical findings about tools cairn builds on | [04-lessons-learned.md](04-lessons-learned.md) |
| Current implementation inventory | [05-implementation-index.md](05-implementation-index.md) |
| Manifest / build-config full reference | [CONFIGURATION.md](CONFIGURATION.md) |
| Registry choice tradeoffs | [ABOUT_REGISTRIES.md](ABOUT_REGISTRIES.md), [ABOUT_GHCR.md](ABOUT_GHCR.md) |
| Practice-level "why" narrative, no requirement numbers | [high-level-motivations-and-workflows.md](high-level-motivations-and-workflows.md) |

## Reading Orders

### General Project Work

1. `CURRENT_CONTEXT.md`
2. [../00-project-scope.md](../00-project-scope.md), [../requirements/00-overview.md](../requirements/00-overview.md)
3. Relevant requirements, technical, or ADR documents

### Implementation Status Or Code Navigation

1. `CURRENT_CONTEXT.md`, when not already loaded
2. [technical/README.md](README.md)
3. [05-implementation-index.md](05-implementation-index.md) and [../../open/OPEN_WORK.md](../../open/OPEN_WORK.md)
4. Relevant owner documents named by the implementation index
5. Named code locations and targeted searches

### Requirements Work

1. [../requirements/00-overview.md](../requirements/00-overview.md)
2. Relevant requirement documents
3. [../CHANGELOG.md](../CHANGELOG.md) when requirements change

## Changelog Discipline

| Change type | Update |
|---|---|
| Requirement or acceptance criterion | [../CHANGELOG.md](../CHANGELOG.md) |
| Important implementation or process decision | [../../decisions/](../../decisions/) or an ADR |
| Documentation ownership or reading order | This file |
| Current implementation state, code locations, validation commands | [05-implementation-index.md](05-implementation-index.md) |
| Software release | [../../CHANGELOG.md](../../CHANGELOG.md) |

## Post-Implementation Doc Hygiene

After meaningful implementation, configuration, documentation work, or a completion judgment
reached through review or discussion, ask: does any referenced document describe intent rather
than reality? If yes, update the owner document before closing the task.

## Archive Rule

Do not load [archive/](../archive/) for active work unless historical context is explicitly
needed.

## Superseded ADRs

When an ADR is fully retired, move its body to [archive/](../archive/) and leave a stub at the
original [adr/](../adr/) or [decisions/](../../decisions/) path pointing to the current
authority document and the archive copy, so existing citations keep resolving. See
[adr/README.md](../adr/README.md).

## Deviations From The Canonical Scribe Coding Template

cairn adopted the canonical scaffold (`brian-pond/scribe_coding`) after already having a
substantial docs tree, and kept a few intentional departures rather than force a mechanical
match:

- **`docs/CHANGELOG.md` is broader than canonical's requirements-only changelog.** It also
  narrates decision and discussion-log revisions. Kept as-is rather than split, since the
  narrative connective tissue between a requirement change and the decision that drove it is
  itself useful, and splitting it would scatter that connective tissue across files. The new
  root `../../CHANGELOG.md` covers only software releases, matching canonical exactly.
- **`../00-project-scope.md` stands apart from `../requirements/00-overview.md`.** Canonical
  folds "project overview" into `requirements/00-overview.md` itself; cairn keeps scope/purpose
  (the "why," rarely revised) separate from the requirements table of contents and conventions
  (the "index," revised whenever an area is added).
- **`../discussions/discussion-log.md` stays one running chronological file**, not split into
  one file per dated entry as the canonical directory shape implies. Many `ADR-*` entries cite
  it by date rather than by anchor, and splitting would multiply files without adding
  navigability for a log that's read chronologically anyway.
- **`../plans/` is kept alongside `open/OPEN_WORK.md`.** Canonical's backlog is a single table;
  cairn's `docs/plans/*.md` carry richer narrative per implementation phase that a table would
  flatten. `open/OPEN_WORK.md` tracks the live, itemized backlog; `docs/plans/` holds the
  narrative record of how a phase was approached and what was learned along the way.
