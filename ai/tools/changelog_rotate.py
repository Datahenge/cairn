"""Rotate `docs/CHANGELOG.md`: archive its oldest entries once the live file grows past its
configured word-count budget (`.docs_check_allowlist`, `DOC002` in `docs_check.py`) —
mechanically, so nobody has to hand-reason through which entries to move, hand-write another
`docs/archive/CHANGELOG-*.md`, and hand-update `docs/archive/README.md`'s index each time.

Run from the project root, or point --root elsewhere:

    python ai/tools/changelog_rotate.py --dry-run   # report what would move, change nothing
    python ai/tools/changelog_rotate.py             # do it

Structural assumption this script depends on (true of every entry in the file today): each
dated entry is a block starting with a `## <YYYY-MM-DD> ...` header, and consecutive entries
are separated by a blank line, a `---` line, and another blank line — the exact shape every
entry in `docs/CHANGELOG.md` already has. If that separator pattern is ever hand-broken,
re-run with --dry-run first; the parser raises rather than guessing.

The trailing "archived entries" block at the end of the live file is never hand-edited or
parsed as prose — this tool owns it outright, regenerating it in full each run from
`docs/archive/README.md`'s own "archived-for-size" index, so it can never drift from what
archive files actually exist.
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from docs_check import (
    DEFAULT_MAX_WORDS,
    check_links_and_word_count,
    load_word_count_allowlist,
    word_count,
)

CHANGELOG_REL = Path("docs/CHANGELOG.md")
ARCHIVE_DIR_REL = Path("docs/archive")
ARCHIVE_INDEX_REL = ARCHIVE_DIR_REL / "README.md"

#: Archive down to this fraction of the word-count ceiling, not exactly to it — leaving no
#: headroom means the very next entry trips the limit again, the churn this tool exists to end.
HEADROOM_FRACTION = 0.75

#: Never archive the newest entry, even if it alone exceeds the budget — rotation moves old
#: entries out of the way, it never hides the thing someone just wrote.
MIN_LIVE_ENTRIES = 1

ENTRY_SEP = "\n\n---\n\n"
HEADER_DATE_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})\b")
ARCHIVE_ROW_RE = re.compile(r"^\| \[([^\]]+)\]\(([^)]+)\) \| `([^`]+)` \| (.+) \|$", re.MULTILINE)
ARCHIVE_TABLE_HEADING = "## Index — archived-for-size"


@dataclass
class Entry:
    header: str  # the "## ..." line, verbatim
    body: str  # everything after it, blank lines at the edges stripped
    entry_date: str

    def render(self) -> str:
        return f"{self.header}\n\n{self.body}" if self.body else self.header

    @property
    def word_count(self) -> int:
        return word_count(self.render())


def _rebase_archive_links(text: str) -> str:
    """Entries being relocated from `docs/` into `docs/archive/` carry relative links written
    for their old location — `[...](archive/X)` was correct in `docs/CHANGELOG.md`, but from
    inside `docs/archive/` itself the same file is a sibling: `[...](X)`. Confirmed against
    the hand-archived precedent (`docs/archive/CHANGELOG-2026-08-04-early.md`), which made
    exactly this same correction when it was written by hand. This is the one relative-link
    shape ever seen in an entry body; anything else surfaces as a warning after writing (see
    `apply_plan`) rather than being silently left broken or guessed at.
    """
    return text.replace("](archive/", "](")


def parse_changelog(text: str) -> tuple[str, list[Entry]]:
    """Split into (preamble, entries newest-first). A trailing hand-written or previously
    machine-written footer, if present, is discarded here — `render_changelog` always
    regenerates it fresh rather than trying to preserve or extend it in place.
    """
    blocks = text.rstrip("\n").split(ENTRY_SEP)
    preamble = blocks[0]
    entries: list[Entry] = []
    for block in blocks[1:]:
        if not block.startswith("## "):
            continue  # the footer block, if this file has one
        header_line, _, rest = block.partition("\n")
        match = HEADER_DATE_RE.match(header_line)
        if not match:
            raise ValueError(
                f"entry header does not start with a date, refusing to guess: {header_line!r}"
            )
        entries.append(Entry(header=header_line, body=rest.strip("\n"), entry_date=match.group(1)))
    return preamble, entries


def read_archive_index_rows(archive_index_path: Path) -> list[tuple[str, str, str, str]]:
    """Every (display_name, relative_path, archived_from, covers) row in the archive's own
    'archived-for-size' index — filtering to `docs/CHANGELOG.md`'s rows is the caller's job,
    since the same row shape is reused by the 'archived open-work' table further down."""
    text = archive_index_path.read_text(encoding="utf-8")
    return [
        (m.group(1), m.group(2), m.group(3), m.group(4)) for m in ARCHIVE_ROW_RE.finditer(text)
    ]


def render_footer(archive_index_path: Path) -> str:
    """Rebuilt in full, every run, from `docs/archive/README.md`'s own index — never hand-
    extended — so the two can never quietly disagree about what's actually been archived."""
    rows = [
        (name, path)
        for name, path, archived_from, _covers in read_archive_index_rows(archive_index_path)
        if archived_from == str(CHANGELOG_REL).replace("\\", "/")
    ]
    if not rows:
        return ""
    paragraph = textwrap.fill(
        "Older entries are moved out once this file grows past its word-count budget "
        "(`.docs_check_allowlist`), by `tools/changelog_rotate.py` — each archive covers a "
        "contiguous range, newest-first within it same as here.",
        width=88,
    )
    lines = ["## Archived entries", "", paragraph, ""]
    lines += [f"- [{name}](archive/{path})" for name, path in rows]
    return "\n".join(lines)


def render_changelog(preamble: str, entries: list[Entry], footer: str) -> str:
    parts = [preamble, *[e.render() for e in entries]]
    if footer:
        parts.append(footer)
    return ENTRY_SEP.join(parts) + "\n"


def choose_archive_filename(archive_dir: Path, oldest: str, newest: str) -> Path:
    stem = f"CHANGELOG-{oldest}" if oldest == newest else f"CHANGELOG-{oldest}-to-{newest}"
    candidate = archive_dir / f"{stem}.md"
    n = 2
    while candidate.exists():
        candidate = archive_dir / f"{stem}-{n}.md"
        n += 1
    return candidate


def render_archive_file(archived: list[Entry], run_date: str) -> str:
    oldest, newest = archived[-1].entry_date, archived[0].entry_date
    label = oldest if oldest == newest else f"{oldest} through {newest}"
    purpose = (
        f"Archived tail of docs/CHANGELOG.md — entries from {label} ({len(archived)} entries)."
    )
    index_lines = [entry.header.removeprefix("## ") for entry in archived]
    intro = textwrap.fill(
        f"Relocated from `docs/CHANGELOG.md` on {run_date} to keep that file under its "
        "word-count budget (`.docs_check_allowlist`), by `tools/changelog_rotate.py`. Content "
        "only — nothing rewritten, nothing summarized. `docs/CHANGELOG.md` carries current "
        "entries; this file is historical-only per `docs/archive/README.md`.",
        width=88,
    )
    lines = [
        "---",
        "status: archived",
        "owner: technical",
        f"purpose: {purpose}",
        "---",
        "",
        f"# Changelog archive — {label}",
        "",
        intro,
        "",
        "## Index",
        "",
        *[f"- {line}" for line in index_lines],
        "",
        "---",
        "",
        ENTRY_SEP.join(_rebase_archive_links(entry.render()) for entry in archived),
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def budget_for(root: Path, max_words_default: int) -> int:
    overrides = load_word_count_allowlist(root)
    return overrides.get(CHANGELOG_REL, max_words_default)


def allowlist_headroom(count: int) -> int:
    """A generous, round budget for a frozen archive file — matches the margin every archive
    file already in `.docs_check_allowlist` carries; slack, not an invitation to keep adding."""
    return ((count + count // 2) // 100 + 1) * 100


@dataclass
class Plan:
    archived: list[Entry]
    remaining: list[Entry]
    archive_path: Path
    before_words: int
    after_words: int


def build_plan(root: Path, max_words_default: int) -> Plan | None:
    changelog_path = root / CHANGELOG_REL
    preamble, entries = parse_changelog(changelog_path.read_text(encoding="utf-8"))
    budget = budget_for(root, max_words_default)
    target = int(budget * HEADROOM_FRACTION)

    footer = render_footer(root / ARCHIVE_INDEX_REL)
    before_words = word_count(render_changelog(preamble, entries, footer))
    if before_words <= budget:
        return None

    k = 0
    while len(entries) - (k + 1) >= MIN_LIVE_ENTRIES:
        k += 1
        remaining = entries[: len(entries) - k]
        after_words = word_count(render_changelog(preamble, remaining, footer))
        if after_words <= target:
            break
    else:
        remaining = entries[: max(MIN_LIVE_ENTRIES, len(entries) - k)]
        after_words = word_count(render_changelog(preamble, remaining, footer))

    archived = entries[len(remaining) :]
    if not archived:
        return None  # nothing left that's safe to move — over budget, but MIN_LIVE_ENTRIES bites
    archive_path = choose_archive_filename(
        root / ARCHIVE_DIR_REL, archived[-1].entry_date, archived[0].entry_date
    )
    return Plan(
        archived=archived,
        remaining=remaining,
        archive_path=archive_path,
        before_words=before_words,
        after_words=after_words,
    )


def apply_plan(root: Path, plan: Plan, run_date: str) -> None:
    changelog_path = root / CHANGELOG_REL
    preamble, _ = parse_changelog(changelog_path.read_text(encoding="utf-8"))

    archive_text = render_archive_file(plan.archived, run_date)
    plan.archive_path.write_text(archive_text, encoding="utf-8")

    _update_archive_index(root / ARCHIVE_INDEX_REL, plan)

    footer = render_footer(root / ARCHIVE_INDEX_REL)  # re-read: now includes the new row
    changelog_path.write_text(
        render_changelog(preamble, plan.remaining, footer), encoding="utf-8"
    )

    _append_allowlist_entry(root / ".docs_check_allowlist", plan.archive_path, root)


def _update_archive_index(index_path: Path, plan: Plan) -> None:
    """Append a new row as the *last* row of the 'archived-for-size' table specifically —
    not merely somewhere after its heading, which would land before the table's own header
    and separator rows and break it. Walks: heading -> header row -> separator row -> every
    `|`-prefixed row after that -> insertion point, right after the table's actual last row.
    """
    lines = index_path.read_text(encoding="utf-8").split("\n")
    heading_idx = next(i for i, line in enumerate(lines) if line.strip() == ARCHIVE_TABLE_HEADING)

    i = heading_idx + 1
    while i < len(lines) and not lines[i].startswith("|"):
        i += 1
    if i >= len(lines):
        raise ValueError(f"{ARCHIVE_TABLE_HEADING!r} has no table beneath it")
    i += 1  # the "| File | Archived from | Covers |" header row
    if i >= len(lines) or not lines[i].startswith("|"):
        raise ValueError(f"{ARCHIVE_TABLE_HEADING!r}'s table has no separator row")
    i += 1  # the "|---|---|---|" separator row
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    # i now indexes the first line after the table's actual last row.

    oldest, newest = plan.archived[-1].entry_date, plan.archived[0].entry_date
    covers = (
        f"Dated entries {oldest}"
        if oldest == newest
        else f"Dated entries {oldest} through {newest}"
    )
    row = (
        f"| [{plan.archive_path.name}]({plan.archive_path.name}) | `{CHANGELOG_REL}` | "
        f"{covers} |"
    )
    lines.insert(i, row)
    index_path.write_text("\n".join(lines), encoding="utf-8")


def _append_allowlist_entry(allowlist_path: Path, archive_path: Path, root: Path) -> None:
    count = word_count(archive_path.read_text(encoding="utf-8"))
    budget = allowlist_headroom(count)
    rel = archive_path.relative_to(root)
    text = allowlist_path.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    text += (
        f"{rel} = {budget}\n"
        "# ^ archived-for-size, not sprawl — frozen content, headroom is just slack, not an\n"
        "# invitation to keep adding to it.\n"
    )
    allowlist_path.write_text(text, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path.cwd(), help="Project root. Defaults to cwd."
    )
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help="Fallback ceiling if docs/CHANGELOG.md has no .docs_check_allowlist override.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Report what would move; write nothing."
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root.resolve()

    plan = build_plan(root, args.max_words)
    if plan is None:
        print(f"{CHANGELOG_REL} is within budget — nothing to rotate.")
        return 0

    print(
        f"{CHANGELOG_REL}: {plan.before_words} words over budget → archiving "
        f"{len(plan.archived)} oldest entr{'y' if len(plan.archived) == 1 else 'ies'} "
        f"({plan.archived[-1].entry_date} through {plan.archived[0].entry_date}) to "
        f"{plan.archive_path.relative_to(root)}; {plan.after_words} words remain live."
    )
    if args.dry_run:
        print("--dry-run: nothing written.")
        return 0

    apply_plan(root, plan, date.today().isoformat())
    print(f"Wrote {plan.archive_path.relative_to(root)}, updated the archive index and "
          f"{CHANGELOG_REL}'s own footer, and gave the new file a .docs_check_allowlist entry.")

    # `_rebase_archive_links` only knows how to fix one relative-link shape. Anything else
    # broken by the move is reported here, not silently shipped — reuses docs_check's own
    # checker rather than a second, drifting implementation of the same rule.
    overrides = load_word_count_allowlist(root)
    broken = [
        issue
        for issue in check_links_and_word_count(root, args.max_words, overrides)
        if issue.code == "DOC001" and issue.path == plan.archive_path.relative_to(root)
    ]
    for issue in broken:
        print(f"WARNING: {issue.format()} — not auto-fixed; needs a manual look", file=sys.stderr)
    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
