"""Exception hierarchy for cairn.

Every error carries a user-facing, actionable message; the CLI renders these as a
clean ``Error: …`` line rather than a traceback (BR-CLI-015).
"""

from __future__ import annotations


class CairnError(Exception):
    """Base class for all cairn errors."""


class ProjectRootNotFoundError(CairnError):
    """No cairn project root (a ``pyproject.toml`` with a ``[tool.ventwig]`` table)
    was found at or above the working directory."""


class VendorToolError(CairnError):
    """The ``ventwig`` vendoring tool is unavailable or could not be invoked."""


class VendorDriftError(CairnError):
    """The vendored tree has drifted from its ``.ventwig.lock`` anchor, or otherwise
    fails a build-input integrity check (BR-VEND-005, BR-VEND-007)."""
