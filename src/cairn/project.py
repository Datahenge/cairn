"""Locate the cairn project root and read its ventwig vendoring configuration.

The project root is the directory holding the ``pyproject.toml`` whose ``[tool.ventwig]``
table declares the vendored sources (BR-VEND-001) — the single source of truth for what
is vendored and where it lives on disk.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from .errors import ProjectRootNotFoundError

PYPROJECT = "pyproject.toml"


@dataclass(frozen=True)
class VendorSource:
    """A single ventwig-managed vendored source (a ``[[tool.ventwig.sources]]`` entry)."""

    name: str
    local_path: str
    ref: str | None = None


def find_project_root(start: Path | None = None) -> Path:
    """Return the nearest ancestor directory (from *start*, default cwd) containing a
    ``pyproject.toml`` with a ``[tool.ventwig]`` table.

    Raises :class:`ProjectRootNotFoundError` if none is found.
    """
    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        pyproject = directory / PYPROJECT
        if not pyproject.is_file():
            continue
        data = _try_load(pyproject)
        if data is not None and "ventwig" in data.get("tool", {}):
            return directory
    raise ProjectRootNotFoundError(
        f"No cairn project found at or above {start} "
        f"(expected a {PYPROJECT} with a [tool.ventwig] table)."
    )


def read_vendor_sources(root: Path) -> list[VendorSource]:
    """Return the vendored sources declared in ``root``'s ``[[tool.ventwig.sources]]``."""
    data = _try_load(root / PYPROJECT)
    if data is None:
        raise ProjectRootNotFoundError(f"Cannot read {root / PYPROJECT}.")
    raw = data.get("tool", {}).get("ventwig", {}).get("sources", [])
    return [VendorSource(name=s["name"], local_path=s["local_path"], ref=s.get("ref")) for s in raw]


def _try_load(pyproject: Path) -> dict | None:
    """Parse *pyproject* as TOML, returning ``None`` if it cannot be read/parsed."""
    try:
        with pyproject.open("rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return None
