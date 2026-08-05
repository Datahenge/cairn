"""cairn — reproducible ERPNext image builds and pull-based deploys.

Builds images from an owned Docker build recipe (`src/cairn/recipe/`, `ADR-059`) rather
than a vendored, pinned one. See ``docs/requirements/`` for the authoritative ``BR-*``
requirements this package implements.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("datahenge-cairn")
except PackageNotFoundError:
    # Not installed at all — e.g. `python -m pytest` against a bare checkout with
    # neither a regular nor an editable install. pyproject.toml is the single source
    # of truth for the real version; this is a placeholder, never a second copy of it.
    __version__ = "0.0.0+unknown"
