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
    """The vendored tree has drifted from its ``.ventwig.lock`` anchor, or contains
    upstream version-control metadata (BR-VEND-005, BR-VEND-007)."""


class BuildEngineError(CairnError):
    """No usable build engine was found, or the requested one is unavailable
    or too old (`ADR-027`)."""


class VendorInputsMissingError(CairnError):
    """The vendored tree is missing a required build input — the custom
    ``Containerfile`` or a file it copies from the build context (BR-VEND-006)."""
