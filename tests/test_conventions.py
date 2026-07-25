"""Executable guards for the working agreement in ``/CLAUDE.md``.

These test the *project's conventions* rather than its behaviour. They exist because a
convention that lives only in prose gets violated: the rule that `BR`/`ADR` identifiers
stay out of user-facing text was broken twice — first in Typer's ``--help`` output, then
in runtime error messages — and both times it was caught by a human reading output, not
by the suite.

If one of these fails, the source is wrong, not the test.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

SOURCE_DIR = Path(__file__).resolve().parent.parent / "src" / "cairn"

#: The identifiers `/CLAUDE.md` defines as internal: BR-<AREA>-NNN and ADR-NNN.
INTERNAL_ID = re.compile(r"\b(?:BR-[A-Z]+-\d+|ADR-\d+)")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Return the ids of string nodes that are docstrings, not runtime values."""
    documented = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, documented) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(getattr(first.value, "value", None), str):
            ids.add(id(first.value))
    return ids


def runtime_strings(path: Path) -> list[tuple[int, str]]:
    """Return every ``(lineno, text)`` string literal in *path* that is **not** a docstring.

    Covers f-string fragments too, since ``ast.walk`` reaches the ``Constant`` parts of a
    ``JoinedStr``. Comments are absent from the AST entirely, which is correct — a comment
    is internal and may cite identifiers freely.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


@pytest.mark.parametrize("source", sorted(SOURCE_DIR.glob("*.py")), ids=lambda p: p.name)
def test_no_internal_identifiers_in_user_facing_strings(source: Path):
    """BR/ADR identifiers are internal: docstrings, comments, tests and docs/ only.

    Every non-docstring string in the package is a candidate for reaching a user — Typer
    renders `help=` verbatim, and error messages are printed as `Error: ...`. So the guard
    is deliberately broad: it is easier to keep identifiers out of all runtime strings
    than to decide, per string, whether a user will ever see it.
    """
    offenders = [
        f"{source.name}:{lineno}: {INTERNAL_ID.search(text).group()} in {text.strip()[:70]!r}"
        for lineno, text in runtime_strings(source)
        if INTERNAL_ID.search(text)
    ]

    assert not offenders, (
        "Internal identifiers must not appear in user-facing text (/CLAUDE.md). "
        "Move the citation into the docstring and say *why* in the message instead:\n  "
        + "\n  ".join(offenders)
    )


def test_the_guard_actually_detects_a_violation(tmp_path):
    """A guard that cannot fail is worse than no guard — prove this one can."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        '"""Docstring citing BR-CLI-015 is fine."""\n'
        "# A comment citing ADR-030 is fine too.\n"
        'MESSAGE = "this is not fine (BR-BUILD-002)."\n',
        encoding="utf-8",
    )

    found = [text for _, text in runtime_strings(planted) if INTERNAL_ID.search(text)]

    assert found == ["this is not fine (BR-BUILD-002)."]
