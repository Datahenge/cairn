---
status: authoritative
owner: technical
purpose: Defines Markdown status headers, documentation levels, and sprawl-control conventions.
---

# Documentation Conventions

## Four Documentation Levels

1. Always-on rules: short, stable, hard to misunderstand (`AGENTS.md`, `ai/CURRENT_CONTEXT.md`).
2. Authority and index docs: maps that tell readers what to read and what owns each topic
   (`README.md` files, `25-documentation-authority.md`).
3. Deep working docs: requirements, technical notes, decisions, design discussions, drafts.
4. Live queues/trackers: short, high-churn, action-oriented (`docs/open/OPEN_QUESTIONS.md`,
   `docs/open/OPEN_DECISIONS.md`, `docs/open/OPEN_WORK.md`). Not a rule, not an index, not a considered
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
- `active`: a live queue or tracker, not a fixed conclusion (`docs/open/OPEN_QUESTIONS.md`,
  `docs/open/OPEN_DECISIONS.md`, `docs/open/OPEN_WORK.md`).
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
document, an index, a decision record, `docs/scratch/` (if it's not yet worth keeping), or
`docs/archive/`.

Create a new document only when it has a distinct owner, audience, lifecycle, or review path.

Avoid: multiple documents owning the same rule, unlabeled drafts, long notes with mixed
authority, loading archive material without a specific reason.

`docs/CHANGELOG.md` specifically grows by same-day append and needs periodic archiving on its
own, separate from this review cadence — run `ai/tools/changelog_rotate.py` (`--dry-run` first)
rather than hand-writing another `docs/archive/CHANGELOG-*.md`; it archives the oldest entries
down to a comfortable margin under `.docs_check_allowlist`'s budget and keeps
`docs/archive/README.md`'s index in sync mechanically.

## Completion Judgment Cells Stay Terse

`05-implementation-index.md`'s "Completion Judgment" column is an inventory field, not a
changelog — but it has repeatedly drifted the other way: each session that lands a real fix
adds "just one more sentence" of context (the bug, the ADR, the exact function renamed), and by
the next session that cell is a full incident narrative, duplicated almost verbatim from
`docs/CHANGELOG.md`. A 2026-08-06 pass found the file had grown to 2,271 words this way — several
cells were multi-paragraph postmortems — and trimmed it back to a terse verdict-plus-pointer
shape (~1,450 words) in one sitting.

**The rule going forward:** a Completion Judgment cell states what's true *now* — implemented,
verified live, still-unexercised gap — in one or two sentences, with a `docs/CHANGELOG.md`
pointer for the story. It does not re-narrate which functions changed, which bug caused what, or
which ADR superseded which. That narrative already lives in `docs/CHANGELOG.md` (or the ADR/
decision itself); repeating it here is duplicate-maintenance debt, not extra safety, and it was
exactly this duplication (plus the resulting `docs_check.py` word-limit fights) that forced the
2026-08-06 trim.

Catch this in documentation review sessions (below): if a cell needs more than ~3 sentences to
say what's true now, the extra is narrative — cut it and point at the changelog instead.

## When A Decision Earns A Decision/ADR File

`docs/adr/` and `docs/decisions/` are the same kind of artifact — rationale for a choice, split
only by weight — and both are expensive: a stable ID that citations, tests, and other documents
may reference forever, plus an index row and (eventually) an archive stub to maintain. Reserve
them for choices about **cairn the product**.

Create a Decision/ADR file only when at least one of these holds:

- A rejected alternative has lasting explanatory value — a future reader would plausibly ask
  "why not the obvious simpler thing?" and deserves a real answer.
- The choice amends a requirement (`BR-<AREA>-NNN`) in a way that needs recorded justification
  beyond "we found a bug and fixed it."

**Out of scope for a Decision/ADR file:** documentation process, tooling calibration (e.g.
`docs_check.py`'s word-count ceiling, `changelog_rotate.py`'s archive cadence), directory or
scaffolding reorganization, cleanup sessions. None of these are things a future maintainer of
cairn-the-product would need to find by a stable ID — they get **one `docs/CHANGELOG.md` entry**
and nothing else. Rule of thumb: *would a future maintainer of cairn-the-product need to find
this by ID? If not, it's process — log it, don't file it.*

This rule applies to itself: a future tightening of these documentation conventions is process,
not product, and gets a `docs/CHANGELOG.md` entry, not a new Decision/ADR file.

**One home for rationale.** A product decision's full rationale lives in exactly one place — the
Decision/ADR file, or the requirement text itself for a small in-place amendment.
`docs/CHANGELOG.md` summarizes and links to it; it does not re-narrate the reasoning at ADR
length. `docs/discussions/discussion-log.md` stays reserved for reasoning that was exploratory
and did not resolve into a stable decision (parked ideas, rejected approaches, open threads).

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
`ai/tools/docs_check.py` as a first pass. For prose-heavy documents specifically, consider a Dorwin
Analysis pass — see [02-dorwin-analysis-and-hardin-version.md](02-dorwin-analysis-and-hardin-version.md).

Expect a real cleanup to take multiple passes within the same session, not one. A single pass
tends to surface problems (a doc that should be split, a rule that should move to a different
owner) whose fix creates new small inconsistencies elsewhere — updated links, a changed index, a
status that needs to flip. Re-run `ai/tools/docs_check.py` and re-scan after each pass rather than
treating the first pass as done; stop when a pass produces no further changes.
