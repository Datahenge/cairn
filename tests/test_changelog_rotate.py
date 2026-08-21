"""Tests for `ai/tools/changelog_rotate.py`'s parser.

Not a `BR` area: this is documentation-hygiene tooling, not product behavior. These tests
exist because the parser failed *silently* on 2026-08-20 — it split entries on the `---` rule
alone, separators had been dropping out of appended entries, the whole file parsed as one
entry, and the run reported "within budget" while `docs_check.py` reported the same file over
its ceiling. A quiet no-op in the tool that exists to keep the changelog under budget is worse
than a crash, so the properties that make it quiet are pinned here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ai" / "tools"))

import changelog_rotate as cr  # noqa: E402  (path shim above must run first)


def build(*entries: str, preamble: str = "# Documentation Changelog\n\nNewest first.") -> str:
    """A changelog in the canonical shape the tool writes: entries joined by a `---` rule."""
    return cr.ENTRY_SEP.join([preamble, *entries]) + "\n"


ENTRY_A = "## 2026-08-20 (newest)\n\nBody of the newest entry."
ENTRY_B = "## 2026-08-19 (middle)\n\nBody of the middle entry."
ENTRY_C = "## 2026-08-18 (oldest)\n\nBody of the oldest entry."


def test_entries_are_found_when_the_separators_are_present():
    _, entries = cr.parse_changelog(build(ENTRY_A, ENTRY_B, ENTRY_C))

    assert [e.entry_date for e in entries] == ["2026-08-20", "2026-08-19", "2026-08-18"]


def test_entries_are_found_when_the_separators_are_missing():
    """The 2026-08-20 failure: entries appended without a `---` rule between them. Splitting
    on the rule alone merged all three into one, which left `MIN_LIVE_ENTRIES` nothing safe to
    archive and turned the run into a no-op."""
    no_rules = "# Documentation Changelog\n\nNewest first.\n\n" + "\n\n".join(
        [ENTRY_A, ENTRY_B, ENTRY_C]
    )

    _, entries = cr.parse_changelog(no_rules)

    assert [e.entry_date for e in entries] == ["2026-08-20", "2026-08-19", "2026-08-18"]


def test_a_separator_less_file_renders_back_out_with_its_separators_restored():
    """Parsing repairs the file: the tool writes the canonical shape whatever it read."""
    canonical = build(ENTRY_A, ENTRY_B)
    no_rules = canonical.replace(cr.ENTRY_SEP, "\n\n")

    preamble, entries = cr.parse_changelog(no_rules)

    assert cr.render_changelog(preamble, entries, footer="") == canonical


def test_the_separator_is_not_left_attached_to_the_body_it_followed():
    """Slicing at headers leaves the preceding entry holding the next one's separator. Left
    in, it would double on every round trip, since `render_changelog` adds one back."""
    _, entries = cr.parse_changelog(build(ENTRY_A, ENTRY_B))

    assert entries[0].body == "Body of the newest entry."
    assert not entries[0].body.endswith("---")


def test_the_generated_footer_is_not_parsed_as_an_entry():
    """`render_changelog` regenerates the footer from the archive index every run, so the
    parser must drop the old one rather than carry it forward as content."""
    text = build(ENTRY_A, f"{cr.FOOTER_HEADING}\n\n- [CHANGELOG-2026-07.md](archive/x.md)")

    preamble, entries = cr.parse_changelog(text)

    assert [e.entry_date for e in entries] == ["2026-08-20"]
    assert cr.FOOTER_HEADING not in cr.render_changelog(preamble, entries, footer="")


def test_a_heading_inside_a_fenced_block_is_content_not_a_boundary():
    """Pasted terminal output can start a line with `## `. Slicing there would split an entry
    mid-body, or raise on a "header" that has no date in it."""
    with_fence = "## 2026-08-20 (entry)\n\nOutput:\n\n```\n## not a heading\n```\n\nTail."

    _, entries = cr.parse_changelog(build(with_fence))

    assert len(entries) == 1
    assert "## not a heading" in entries[0].body
    assert entries[0].body.endswith("Tail.")


def test_an_undated_heading_still_refuses_to_guess():
    """The one thing that should stay loud. Tolerating a missing separator is not the same as
    tolerating a header the tool cannot place in time."""
    with pytest.raises(ValueError, match="refusing to guess"):
        cr.parse_changelog(build("## Some untitled section\n\nBody."))


def test_the_preamble_keeps_its_content_and_loses_its_trailing_rule():
    preamble, _ = cr.parse_changelog(build(ENTRY_A))

    assert preamble == "# Documentation Changelog\n\nNewest first."


def test_the_real_changelog_round_trips_byte_for_byte():
    """The parser is only safe to run against the live file if rendering what it read
    reproduces exactly what was there. Guards the whole pipeline, not just the split."""
    changelog = REPO_ROOT / cr.CHANGELOG_REL
    original = changelog.read_text(encoding="utf-8")

    preamble, entries = cr.parse_changelog(original)
    footer = cr.render_footer(REPO_ROOT / cr.ARCHIVE_INDEX_REL)

    assert cr.render_changelog(preamble, entries, footer) == original


def test_the_real_changelog_parses_into_every_entry_it_visibly_has():
    """A file-level sanity check against the exact regression: one giant entry passes every
    unit test above and still breaks rotation."""
    text = (REPO_ROOT / cr.CHANGELOG_REL).read_text(encoding="utf-8")
    visible = len(re.findall(r"(?m)^## \d{4}-\d{2}-\d{2}", text))

    _, entries = cr.parse_changelog(text)

    assert len(entries) == visible > 1


def scaffold(tmp_path: Path, changelog: str, ceiling: int) -> None:
    """The minimum tree `build_plan` reads: a changelog, an allowlist, an archive index."""
    (tmp_path / "docs" / "archive").mkdir(parents=True)
    (tmp_path / "ai" / "tools").mkdir(parents=True)
    (tmp_path / cr.ALLOWLIST_REL).write_text(f"docs/CHANGELOG.md = {ceiling}\n")
    (tmp_path / cr.ARCHIVE_INDEX_REL).write_text(
        f"# Archive\n\n{cr.ARCHIVE_TABLE_HEADING}\n\n"
        "| File | Archived from | Covers |\n|---|---|---|\n"
    )
    (tmp_path / cr.CHANGELOG_REL).write_text(changelog)


def test_being_over_budget_with_nothing_movable_is_not_reported_as_within_budget(tmp_path):
    """The other half of the 2026-08-20 failure. `build_plan` returned `None` for two
    unrelated reasons and `main` printed the same reassuring line for both, so a file over
    its ceiling could look like a clean run while `docs_check.py` disagreed about it."""
    scaffold(tmp_path, build("## 2026-08-20 (only entry)\n\n" + "word " * 50), ceiling=5)

    with pytest.raises(cr.NothingToMove, match="never archived"):
        cr.build_plan(tmp_path, cr.DEFAULT_MAX_WORDS)


def test_the_within_budget_message_is_still_used_when_the_file_is_actually_small(tmp_path):
    scaffold(tmp_path, build(ENTRY_A, ENTRY_B), ceiling=5000)

    assert cr.build_plan(tmp_path, cr.DEFAULT_MAX_WORDS) is None
