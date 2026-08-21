"""Tests for `ai/tools/docs_check.py`'s link-fragment check (DOC005).

Not a `BR` area: documentation-hygiene tooling, outside every requirement area. The check
exists because `docs_check.py` verified that a link's target *file* existed but never that
its `#anchor` resolved, so `userdocs/registry/ghcr-setup.md` pointed at `#what-it-costs` for
some time while the heading was a much longer phrase. A checker that reports clean while the
thing it guards is broken is the failure mode worth testing.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ai" / "tools"))

import docs_check as dc  # noqa: E402  (path shim above must run first)


def codes(root: Path) -> list[str]:
    return [i.code for i in dc.check_links_and_word_count(root, dc.DEFAULT_MAX_WORDS, {})]


def write(root: Path, name: str, text: str) -> None:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text, encoding="utf-8")


def test_the_historical_break_is_caught(tmp_path):
    """The real one: an anchor invented from the first few words of a long heading."""
    write(tmp_path, "cost.md", "# Cost\n\n## What it costs — read this before you push\n")
    write(tmp_path, "setup.md", "# Setup\n\nSee [cost](cost.md#what-it-costs).\n")

    assert codes(tmp_path) == ["DOC005"]


def test_both_renderers_slug_conventions_are_accepted():
    """`docs/` is read on GitHub and `userdocs/` through mkdocs, and the two disagree about
    punctuation: GitHub deletes the em dash and keeps the spaces that surrounded it, so each
    becomes a hyphen. A link written for either renderer has to pass."""
    anchors = dc.collect_anchors("## What it costs — read this")

    assert "what-it-costs-read-this" in anchors  # python-markdown
    assert "what-it-costs--read-this" in anchors  # GitHub


def test_a_resolving_fragment_is_not_reported(tmp_path):
    write(tmp_path, "cost.md", "# Cost\n\n## What it costs\n")
    write(tmp_path, "setup.md", "# Setup\n\nSee [cost](cost.md#what-it-costs).\n")

    assert codes(tmp_path) == []


def test_a_same_file_fragment_is_checked_too(tmp_path):
    """`[x](#y)` has no target file, so it used to skip the whole check."""
    write(tmp_path, "page.md", "# Page\n\n[jump](#nowhere)\n\n## Somewhere\n")

    assert codes(tmp_path) == ["DOC005"]


def test_an_explicit_attr_list_id_is_honoured(tmp_path):
    """`attr_list` is enabled in mkdocs.yml, so a heading can name its own id."""
    write(tmp_path, "page.md", "# Page\n\n[jump](#custom)\n\n## A Heading {#custom}\n")

    assert codes(tmp_path) == []


def test_a_hand_written_html_anchor_is_honoured(tmp_path):
    write(tmp_path, "page.md", '# Page\n\n[jump](#spot)\n\n<a id="spot"></a>\n')

    assert codes(tmp_path) == []


def test_backticks_in_a_heading_do_not_reach_the_id(tmp_path):
    """Ids come from rendered text, not source. This repo's headings are full of code spans."""
    write(tmp_path, "page.md", "# Page\n\n[jump](#cairn-build-verbs)\n\n## `cairn-build` verbs\n")

    assert codes(tmp_path) == []


def test_a_heading_inside_a_fenced_block_is_not_an_anchor(tmp_path):
    """Pasted terminal output can start a line with `## `. It renders as code, not a heading,
    so a link aiming at it would 404 in the browser and must not pass here."""
    write(tmp_path, "page.md", "# Page\n\n[jump](#not-a-heading)\n\n```\n## not a heading\n```\n")

    assert codes(tmp_path) == ["DOC005"]


def test_a_missing_file_reports_the_broken_link_and_not_a_missing_anchor(tmp_path):
    """One fault, one finding. A fragment on a link whose file is gone says nothing extra."""
    write(tmp_path, "setup.md", "# Setup\n\nSee [gone](gone.md#anything).\n")

    assert codes(tmp_path) == ["DOC001"]


def test_the_real_tree_has_no_unresolved_fragments():
    """44 fragment links across docs/ and userdocs/ at the time this was written. This is the
    assertion that keeps a hand-written anchor from landing unnoticed."""
    issues = dc.check_links_and_word_count(
        REPO_ROOT, dc.DEFAULT_MAX_WORDS, dc.load_word_count_allowlist(REPO_ROOT)
    )

    assert [i.format() for i in issues if i.code == "DOC005"] == []
