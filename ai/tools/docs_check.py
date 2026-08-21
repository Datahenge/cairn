"""Documentation hygiene checks for cairn's Scribe Coding docs tree.

Adapted from the generic checker in brian-pond/scribe_coding. Checks:

  DOC001  broken relative Markdown link
  DOC002  document exceeds the word-count sprawl limit
  DOC003  decision/ADR index status doesn't match the linked file's frontmatter
  DOC004  a path under the current user's home directory leaked into a doc
  DOC005  a Markdown link's #fragment matches no heading or anchor in its target

Run from the project root, or point --root elsewhere:

    python ai/tools/docs_check.py --root /path/to/cairn
"""

from __future__ import annotations

import argparse
import getpass
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "node_modules",
    "dist",
    "build",
}

#: The owned Docker build recipe (ADR-059) — never linted to our own standard, same as
#: ruff's own `extend-exclude` in pyproject.toml.
EXCLUDED_PATHS = {
    Path("src/cairn/recipe"),
}
DEFAULT_MAX_WORDS = 2200
ALLOWLIST_FILENAME = ".docs_check_allowlist"
#: Colocated with the scripts that read/write it, not the repo root — nothing else looks here.
ALLOWLIST_REL = Path("ai/tools") / ALLOWLIST_FILENAME

MARKDOWN_LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
INDEX_ROW_RE = re.compile(r"^\| \[([^\]]+)\]\(([^)]+)\) \| `?([^`|]+?)`? \|", re.MULTILINE)


@dataclass(frozen=True)
class DocIssue:
    code: str
    path: Path
    message: str

    def format(self) -> str:
        return f"{self.code}: {self.path}: {self.message}"


def repo_relative(path: Path, root: Path) -> Path:
    return path.resolve().relative_to(root.resolve())


def is_excluded(path: Path, root: Path) -> bool:
    rel = repo_relative(path, root)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return True
    return any(rel == excluded or excluded in rel.parents for excluded in EXCLUDED_PATHS)


def markdown_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*.md") if p.is_file() and not is_excluded(p, root)
    )


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def frontmatter_value(text: str, key: str) -> str | None:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    for line in match.group(1).splitlines():
        if line.startswith(f"{key}:"):
            return line.split(":", 1)[1].strip()
    return None


#: An `attr_list` id on a heading: `## Heading {#custom-id}`.
ATTR_LIST_ID_RE = re.compile(r"\{[^}]*#([A-Za-z0-9_:.-]+)[^}]*\}\s*$")
#: A hand-written HTML anchor, either spelling.
HTML_ANCHOR_RE = re.compile(r"<a\s[^>]*\b(?:id|name)\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
FENCE_RE = re.compile(r"^\s{0,3}(```|~~~)")


def _strip_inline_markdown(text: str) -> str:
    """Reduce a heading to the text a renderer would put inside the tag.

    Both slug functions below work on rendered text, not source: a heading that wraps a name
    in backticks yields an id with no trace of them.
    """
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # links and images
    text = re.sub(r"</?[^>]+>", "", text)  # inline HTML
    return text.replace("`", "").replace("**", "").replace("*", "").replace("_", " ")


def _slug_pymarkdown(text: str) -> str:
    """python-markdown's `toc` default, which is what mkdocs-material renders `userdocs/` with.

    Non-ASCII is dropped rather than transliterated, so an em dash in a heading vanishes and
    the spaces around it collapse into a single hyphen.
    """
    value = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


def _slug_github(text: str) -> str:
    """GitHub's slugger, which is what renders `docs/` when read in the web UI.

    It differs from python-markdown's on exactly the case that bit this repo: punctuation is
    deleted in place, leaving the spaces that surrounded it, so each becomes its own hyphen.
    """
    value = unicodedata.normalize("NFKD", text)
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return value.replace(" ", "-")


def collect_anchors(text: str) -> set[str]:
    """Every id a link in this repo could legitimately aim at, in one document.

    Both slug conventions are accepted for every heading. The two renderers disagree, the
    same file can be read through either, and the goal here is to catch an anchor that exists
    under *no* convention — which is what a hand-written or invented fragment looks like.
    """
    anchors: set[str] = set(HTML_ANCHOR_RE.findall(text))
    seen: dict[str, int] = {}
    in_fence = False
    for line in text.split("\n"):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        heading = match.group(2)
        explicit = ATTR_LIST_ID_RE.search(heading)
        if explicit:
            anchors.add(explicit.group(1))
            heading = ATTR_LIST_ID_RE.sub("", heading).strip()
        stripped = _strip_inline_markdown(heading)
        for slug in (_slug_pymarkdown(stripped), _slug_github(stripped)):
            if not slug:
                continue
            # Repeated headings get a numeric suffix, in both renderers.
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
            anchors.add(f"{slug}-{count + 1}")
    return anchors


def link_fragment(link: str) -> str:
    _, _, fragment = link.strip().partition("#")
    if " " in fragment:  # a Markdown title: [x](y#z "title")
        fragment = fragment.split(" ", 1)[0]
    return fragment


def link_target(link: str) -> str:
    target = link.strip().split("#", 1)[0]
    if " " in target:
        target = target.split(" ", 1)[0]
    return target


def should_skip_link(target: str) -> bool:
    return (
        not target
        or target.startswith("/")
        or target.startswith("http://")
        or target.startswith("https://")
        or target.startswith("mailto:")
    )


def load_word_count_allowlist(root: Path) -> dict[Path, int]:
    allowlist_path = root / ALLOWLIST_REL
    if not allowlist_path.exists():
        return {}
    overrides: dict[Path, int] = {}
    for line in allowlist_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        rel_path, _, max_words = line.partition("=")
        overrides[Path(rel_path.strip())] = int(max_words.strip())
    return overrides


def anchors_for(path: Path, cache: dict[Path, set[str]]) -> set[str]:
    """`collect_anchors` for one file, parsed once per run — a hub document is linked at
    from many others, and the whole tree is re-read on every check."""
    if path not in cache:
        try:
            cache[path] = collect_anchors(path.read_text(encoding="utf-8"))
        except OSError:
            cache[path] = set()
    return cache[path]


def check_links_and_word_count(
    root: Path, max_words_default: int, overrides: dict[Path, int]
) -> list[DocIssue]:
    issues: list[DocIssue] = []
    cache: dict[Path, set[str]] = {}
    for path in markdown_files(root):
        rel = repo_relative(path, root)
        text = path.read_text(encoding="utf-8")

        max_words = overrides.get(rel, max_words_default)
        count = word_count(text)
        if count > max_words:
            issues.append(
                DocIssue(
                    "DOC002",
                    rel,
                    f"{count} words exceeds limit {max_words}; split or route detail elsewhere",
                )
            )

        for match in MARKDOWN_LINK_RE.finditer(text):
            link = match.group(1)
            target = link_target(link)
            fragment = link_fragment(link)
            line_no = text.count("\n", 0, match.start()) + 1

            if should_skip_link(target):
                # A bare "#anchor" points into this same document.
                if fragment and not target and fragment not in anchors_for(path, cache):
                    issues.append(
                        DocIssue(
                            "DOC005",
                            rel,
                            f"link {link!r} on line {line_no} matches no heading in this file",
                        )
                    )
                continue

            target_path = (path.parent / target).resolve()
            if not target_path.exists():
                issues.append(
                    DocIssue(
                        "DOC001",
                        rel,
                        f"broken relative link {link!r} on line {line_no}",
                    )
                )
                continue

            if fragment and target_path.suffix == ".md":
                if fragment not in anchors_for(target_path, cache):
                    issues.append(
                        DocIssue(
                            "DOC005",
                            rel,
                            f"link {link!r} on line {line_no} points at "
                            f"{repo_relative(target_path, root)}, which has no such heading",
                        )
                    )
    return issues


def check_index_status_drift(root: Path) -> list[DocIssue]:
    """Check docs/decisions/README.md and docs/adr/README.md index tables against
    the `status` frontmatter of each file they link to."""
    issues: list[DocIssue] = []
    for index_rel in (Path("docs/decisions/README.md"), Path("docs/adr/README.md")):
        index_path = root / index_rel
        if not index_path.exists():
            continue

        index_text = index_path.read_text(encoding="utf-8")
        for match in INDEX_ROW_RE.finditer(index_text):
            target = match.group(2)
            indexed_status = match.group(3).strip()
            if should_skip_link(target):
                continue

            decision_path = (index_path.parent / target).resolve()
            if not decision_path.exists():
                continue

            actual_status = frontmatter_value(
                decision_path.read_text(encoding="utf-8"), "status"
            )
            if actual_status and indexed_status != actual_status:
                line_no = index_text.count("\n", 0, match.start()) + 1
                issues.append(
                    DocIssue(
                        "DOC003",
                        index_rel,
                        f"index status {indexed_status!r} on line {line_no} does not "
                        f"match {repo_relative(decision_path, root)} frontmatter {actual_status!r}",
                    )
                )
    return issues


def check_leaked_home_paths(root: Path) -> list[DocIssue]:
    """Flag absolute paths under the current user's home directory. A doc
    that hardcodes /home/<you>/... won't mean anything on another machine or
    to another reader."""
    home_path_re = re.compile(re.escape(f"/home/{getpass.getuser()}/"))
    issues: list[DocIssue] = []
    for path in markdown_files(root):
        rel = repo_relative(path, root)
        if rel.name in ("AGENTS.md",):
            continue
        text = path.read_text(encoding="utf-8")
        for match in home_path_re.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            issues.append(
                DocIssue(
                    "DOC004",
                    rel,
                    f"machine-local absolute path on line {line_no}; use a relative path or env var",
                )
            )
    return issues


def check_repository(root: Path, max_words_default: int) -> list[DocIssue]:
    overrides = load_word_count_allowlist(root)
    return [
        *check_links_and_word_count(root, max_words_default, overrides),
        *check_index_status_drift(root),
        *check_leaked_home_paths(root),
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check cairn's documentation hygiene.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root to check. Defaults to cwd.")
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help=f"Default per-document word-count limit (default {DEFAULT_MAX_WORDS}). "
        f"Override per file via {ALLOWLIST_REL}.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    issues = check_repository(args.root, args.max_words)
    if issues:
        for issue in issues:
            print(issue.format(), file=sys.stderr)
        return 1
    print("Documentation checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
