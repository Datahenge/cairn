"""Vendored-tree management: thin wrappers over ``ventwig`` plus the integrity checks
used as build preconditions.

cairn never re-implements ventwig. ``status``/``sync`` shell out to it (BR-CLI-006), and
the drift precondition trusts ventwig's **exit code** — 0 when every source is clean, 1 on
any drift — as the authoritative signal (BR-VEND-005), avoiding brittle output parsing.
ventwig is invoked as ``python -m ventwig`` so it always resolves from cairn's own
environment rather than an unrelated one on ``PATH``.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from .errors import VendorDriftError, VendorToolError
from .project import read_vendor_sources

GIT_DIR_NAME = ".git"


def status(root: Path, source: str | None = None) -> int:
    """Run ``ventwig status`` (streaming its output) and return its exit code (BR-CLI-006)."""
    return _run(_args("status", source), root, capture=False).returncode


def sync(root: Path, source: str | None = None) -> int:
    """Run ``ventwig sync`` (streaming its output) and return its exit code (BR-CLI-006)."""
    return _run(_args("sync", source), root, capture=False).returncode


def assert_clean(root: Path, source: str | None = None) -> None:
    """Raise :class:`VendorDriftError` unless every vendored source matches its
    ``.ventwig.lock`` anchor.

    This is the build precondition: drift is a **hard stop** with no override
    (BR-VEND-005). ventwig's exit code is authoritative (0 clean / 1 drifted).
    """
    result = _run(_args("status", source), root, capture=True)
    if result.returncode != 0:
        detail = ((result.stdout or "") + (result.stderr or "")).strip()
        raise VendorDriftError(
            "Vendored tree has drifted from .ventwig.lock; refusing to build. "
            "Restore it with `cairn vendor sync` (or revert your changes)."
            + (f"\n{detail}" if detail else "")
        )


def assert_no_nested_git(root: Path) -> None:
    """Raise :class:`VendorDriftError` if any vendored source contains a nested ``.git``.

    The vendored tree must be plain committed files (BR-VEND-007).
    """
    for src in read_vendor_sources(root):
        nested = root / src.local_path / GIT_DIR_NAME
        if nested.exists():
            raise VendorDriftError(
                f"Vendored source '{src.name}' contains a nested {GIT_DIR_NAME} "
                f"({nested}); the vendored tree must be plain files (BR-VEND-007)."
            )


def _args(subcommand: str, source: str | None) -> list[str]:
    return [subcommand, source] if source else [subcommand]


def _run(args: list[str], root: Path, *, capture: bool) -> subprocess.CompletedProcess[str]:
    _require_ventwig()
    return subprocess.run(
        [sys.executable, "-m", "ventwig", *args],
        cwd=root,
        capture_output=capture,
        text=True,
        check=False,
    )


def _require_ventwig() -> None:
    if importlib.util.find_spec("ventwig") is None:
        raise VendorToolError(
            "ventwig is required for vendoring commands but is not installed. "
            "Install it with: pip install ventwig"
        )
