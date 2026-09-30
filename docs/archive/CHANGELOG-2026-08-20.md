---
status: archived
owner: technical
purpose: Archived tail of docs/CHANGELOG.md — entries from 2026-08-20 (5 entries).
---

# Changelog archive — 2026-08-20

Relocated from `docs/CHANGELOG.md` on 2026-09-29 to keep that file under its word-count
budget (`.docs_check_allowlist`), by `tools/changelog_rotate.py`. Content only — nothing
rewritten, nothing summarized. `docs/CHANGELOG.md` carries current entries; this file is
historical-only per `docs/archive/README.md`.

## Index

- 2026-08-20 (orientation pages promoted; README rewritten)
- 2026-08-20 (`docs_check.py` gains DOC005: unresolved link fragments)
- 2026-08-20 (`W-034` closed, both halves)
- 2026-08-20 (`changelog_rotate.py` splits on dated headings, not on the `---` rule)
- 2026-08-20 (changelog rotation was a silent no-op; separators restored)

---

## 2026-08-20 (orientation pages promoted; README rewritten)

`userdocs/index.md` is replaced by the funnel-ordered rewrite from `docs/scratch/`, and
`why-cairn.md` is new. Both follow `26-userdocs-style.md`. The old front page opened with "a
thin, opinionated wrapper" (§3.4's verbatim *before* example) and carried "Two pillars",
"low-thought", "a strict data-plane boundary", and "it ships code, not data" — all four of
§3.3's banned-by-example slogans — plus a project-status admonition inventorying unverified
pages, which §6 says must not appear on `index.md`.

Two changes to the drafts as promoted. The mermaid diagram is dropped: `mkdocs.yml` configures
`pymdownx.superfences` with no mermaid custom fence, so it would have rendered as a literal code
block. And `why-cairn.md`'s sample `cairn-build images` listing is replaced with prose, because
it was composed rather than captured — faithful to `images.render()`'s shape but missing the
per-image line that function always emits, which is exactly the drift §5 warns about. This
workstation has no container engine, so no real capture was possible; the page's footer says so.

Links are retargeted at today's page tree rather than the funnel filenames the drafts assumed,
per `W-039`. `docs/scratch/workflow.md` stays in scratch: it depends on `concepts.md` and
`install.md`, which do not exist yet.

The root `README.md` is rewritten in the same pass, at Brian's direction: mermaid diagram
removed, slogans out, and a "How it works" paragraph that says what actually happens instead of
asserting that it is magic. `README.md` is outside `26-userdocs-style.md`'s scope by that
document's own first paragraph, but the voice rules were applied anyway.

---

## 2026-08-20 (`docs_check.py` gains DOC005: unresolved link fragments)

`docs_check.py` verified that a link's target file existed but never that its `#anchor`
resolved, which is how `ghcr-setup.md` pointed at `#what-it-costs` while the heading was "What
it costs — read this before you push several images". Found by hand earlier the same day; now
mechanical.

Both slug conventions are accepted for every heading, because `docs/` is read on GitHub and
`userdocs/` through mkdocs and the two disagree: python-markdown drops the em dash and collapses
the surrounding spaces into one hyphen, GitHub deletes it in place and turns each remaining
space into its own. Accepting both catches an anchor that exists under *neither*, which is what
an invented fragment looks like, without inventing false positives. `attr_list` ids, hand-written
HTML anchors, duplicate-heading suffixes, and code spans in headings are all handled; a `## ` line
inside a fenced block is not an anchor.

44 fragment links across `docs/` and `userdocs/` — all currently resolve. `tests/test_docs_check.py`
is new (10 tests), including the historical break as a regression test.

---

## 2026-08-20 (`W-034` closed, both halves)

The crash originally reported was real and Brian fixed it on 2026-08-06 in `cb1ffd5`, which added
`parse_changelog`'s `header_line == FOOTER_HEADING` guard — the same day the item was filed,
which is why the 2026-08-18 re-check could not reproduce it. That was never recorded, so the row
stayed open on a "close if it stays quiet" clause for two weeks.

The second half is fixed here: `build_plan` returned `None` both when the file was under budget
and when it was over budget with nothing movable, and `main` printed the same reassuring line for
both. It now raises `NothingToMove`, naming the file, its size, its ceiling, and the two ways out.
`.docs_check_allowlist`'s stopgap note about rotation being blocked is removed, since it isn't.

---

## 2026-08-20 (`changelog_rotate.py` splits on dated headings, not on the `---` rule)

Brian: fix the parser rather than rely on the separators staying put. `parse_changelog` now
slices `docs/CHANGELOG.md` at its `## <YYYY-MM-DD>` headers. A `## ` line inside a fenced code
block is content, not a boundary, and the separator that slicing leaves attached to the end of
the preceding entry is dropped, since `render_changelog` writes one back. A file missing its
separators parses correctly and is written back out repaired. A header the tool cannot date
still raises rather than guessing, which is the one thing that should stay loud.

`tests/test_changelog_rotate.py` is new, and is the tool's first test coverage — the parser was
untested, which is why the failure was silent for weeks. Ten tests, including the exact
regression (a separator-less file parsing as one entry) and a byte-for-byte round trip against
the live changelog. Full suite: 981 passing.

No `BR` ID: `ai/tools/` is documentation-hygiene tooling, outside every requirement area.
`01-documentation-conventions.md`'s separator note is corrected in the same change, and `W-034`
records what remains — `build_plan` still reports "within budget" on every `None`, including the
`MIN_LIVE_ENTRIES` case.

---

## 2026-08-20 (changelog rotation was a silent no-op; separators restored)

Adding the two entries above put `docs/CHANGELOG.md` over its 6,500-word ceiling, and
`changelog_rotate.py` answered "within budget — nothing to rotate" while `docs_check.py` reported
`DOC002` on the same file.

Cause: `parse_changelog` splits entries on the `---` rule and nothing else. Those separators had
been dropping out of appended entries for some time, so all 23 entries parsed as one, and
`MIN_LIVE_ENTRIES` left nothing safe to archive. Restoring the separators (no content changed,
23 words added) made rotation work normally: 7 entries covering 2026-08-06 through 2026-08-18
moved to `docs/archive/CHANGELOG-2026-08-06-to-2026-08-18.md`, leaving 4,761 words live, and the
archive index, this file's footer, and `.docs_check_allowlist` updated mechanically.

The separator requirement is now stated in `01-documentation-conventions.md`, and `W-034` records
the root cause. This is not the crash `W-034` originally reported, which still has not
reproduced.
