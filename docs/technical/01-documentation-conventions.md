---
status: authoritative
owner: technical
purpose: Defines Markdown status headers, documentation levels, and sprawl-control conventions.
---

# Documentation Conventions

## Four Documentation Levels

1. Always-on rules: short, stable, hard to misunderstand (`AGENTS.md`, `CURRENT_CONTEXT.md`).
2. Authority and index docs: maps that tell readers what to read and what owns each topic
   (`README.md` files, `25-documentation-authority.md`).
3. Deep working docs: requirements, technical notes, decisions, design discussions, drafts.
4. Live queues/trackers: short, high-churn, action-oriented (`open/OPEN_QUESTIONS.md`,
   `open/OPEN_DECISIONS.md`, `open/OPEN_WORK.md`). Not a rule, not an index, not a considered
   reference — check at the start of relevant work, update as items resolve.

## Markdown Header

Every Markdown document should begin with:

```markdown
---
status: exploratory
owner: requirements
purpose: One sentence describing what this document owns or why it exists.
---
```

Allowed `status` values:

- `exploratory`: working notes, analysis, options, drafts, unresolved ideas.
- `authoritative`: current source of truth for a defined topic.
- `active`: a live queue or tracker, not a fixed conclusion (`open/OPEN_QUESTIONS.md`,
  `open/OPEN_DECISIONS.md`, `open/OPEN_WORK.md`).
- `archived`: historical or superseded material; see `docs/archive/README.md` for load-hygiene
  guidance.
- `deliverable`: audience-facing material (client, end user, public — i.e. `userdocs/`).

Exceptions: `AGENTS.md` / `CLAUDE.md` (operational instruction files read before ordinary docs);
verbatim backups preserved for historical accuracy; and root `README.md`, root `CHANGELOG.md`,
and `userdocs/**/*.md` — all three are rendered by an external tool (GitHub, mkdocs-material)
that does not strip YAML frontmatter, so adding it would show as literal visible text rather
than being hidden metadata. Revisit `userdocs/` if `mkdocs.yml` ever gains a metadata-stripping
extension.

## Sprawl Control

Before creating a new Markdown document, ask whether the material belongs in an existing owner
document, an index, a decision record, `scratch/` (if it's not yet worth keeping), or
`docs/archive/`.

Create a new document only when it has a distinct owner, audience, lifecycle, or review path.

Avoid: multiple documents owning the same rule, unlabeled drafts, long notes with mixed
authority, loading archive material without a specific reason.

## Documentation Review Sessions

Documentation entropy is expected, not a sign of failure. Every requirement change, decision,
and implementation slice adds a small amount of drift: a stale claim, a link that now points at
the wrong owner, an index that fell one edit behind its target. Left alone, this compounds until
the docs stop being trustworthy — so periodic review is a standing part of the method, not a
one-time cleanup done once and considered finished.

Schedule a session dedicated only to documentation review, cleanup, and improvement on a regular
cadence, not just when something feels obviously broken. During that kind of session, avoid
implementation and avoid introducing new project ideas unless Brian explicitly changes the goal.

Review for: missing headers, unclear authority, duplicate content, contradictions, stale claims,
missing index links, documents that should be archived, split, or consolidated. Run
`tools/docs_check.py` as a first pass. For prose-heavy documents specifically, consider a Dorwin
Analysis pass — see [02-dorwin-analysis-and-hardin-version.md](02-dorwin-analysis-and-hardin-version.md).

Expect a real cleanup to take multiple passes within the same session, not one. A single pass
tends to surface problems (a doc that should be split, a rule that should move to a different
owner) whose fix creates new small inconsistencies elsewhere — updated links, a changed index, a
status that needs to flip. Re-run `tools/docs_check.py` and re-scan after each pass rather than
treating the first pass as done; stop when a pass produces no further changes.
