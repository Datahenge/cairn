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


class ConfigError(CairnError):
    """Base for manifest and build-configuration problems."""


class ManifestNotFoundError(ConfigError):
    """No ``cairn.toml`` was found by the documented search (BR-CFG-012)."""


class ManifestInvalidError(ConfigError):
    """A ``cairn.toml`` exists but is unparseable or violates BR-BUILD-002/003/005."""


class BuildConfigInvalidError(ConfigError):
    """A build-config file exists but is unparseable or carries an invalid value."""


class BuildError(CairnError):
    """The build engine was invoked and failed (BR-BUILD-009)."""


class PushError(CairnError):
    """An image could not be pushed, or no registry is configured (BR-CLI-003)."""


class RefResolutionError(CairnError):
    """A manifest ref could not be resolved to exactly one commit (BR-BUILD-005)."""


class BuildEngineError(CairnError):
    """No usable build engine was found, or the requested one is unavailable
    or too old (`ADR-027`)."""


class ImageQueryError(CairnError):
    """Local or remote image introspection could not be completed (BR-CLI-005)."""


class TranscriptError(CairnError):
    """The build transcript directory or file cannot be used safely (BR-CLI-016)."""


class VendorInputsMissingError(CairnError):
    """The vendored tree is missing a required build input — the custom
    ``Containerfile`` or a file it copies from the build context (BR-VEND-006)."""
