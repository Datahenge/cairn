"""The recipe tree: where it lives, and the one build precondition over it (`ADR-059`).

The owned ``frappe_docker`` recipe lives at ``src/cairn/recipe/frappe_docker`` — *inside*
the cairn package itself (`BR-VEND-001`) — so it ships in the wheel the same way every
other package file does, and every path in this module is resolved relative to cairn's own
installed location, never by searching the filesystem for a project root. That is what
makes these checks work identically in a development checkout and in a ``pip install``.

Cairn owns this tree outright: it may be created, modified, or deleted like any other part
of the codebase. There is no pin, no lock file, no drift check, and no sync obligation
(`BR-VEND-002`). The one thing this module still enforces is build-input completeness
(``assert_build_inputs``, `BR-VEND-003`) — an ordinary sanity check on cairn's own source,
not a vendoring precondition. ``cairn-build doctor`` runs the same check ahead of time
(`BR-CLI-007`).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .errors import VendorInputsMissingError

#: The recipe source that supplies the image build inputs.
FRAPPE_DOCKER_SOURCE = "frappe_docker"

#: Where the recipe tree lives, relative to cairn's own installed location — not searched
#: for, so this resolves identically in a checkout and in a wheel.
RECIPE_DIR = Path(__file__).resolve().parent / "recipe"
FRAPPE_DOCKER_DIR = RECIPE_DIR / FRAPPE_DOCKER_SOURCE

#: The custom-image Containerfile cairn builds with, relative to that source (ADR-004).
CUSTOM_CONTAINERFILE = "images/custom/Containerfile"


def assert_build_inputs() -> None:
    """Raise :class:`VendorInputsMissingError` unless the recipe tree carries every
    build input the custom Containerfile needs (BR-VEND-003).

    The required set is derived from the Containerfile itself — each path it copies from
    the build context — so it stays correct as the recipe is edited by hand, rather than
    encoding a list that silently rots.
    """
    containerfile = FRAPPE_DOCKER_DIR / CUSTOM_CONTAINERFILE
    if not containerfile.is_file():
        raise VendorInputsMissingError(
            f"Recipe source '{FRAPPE_DOCKER_SOURCE}' is missing {CUSTOM_CONTAINERFILE} "
            f"(expected at {containerfile})."
        )

    missing = [
        path for path in _context_copies(containerfile) if not _resolves(FRAPPE_DOCKER_DIR, path)
    ]
    if missing:
        raise VendorInputsMissingError(
            f"{CUSTOM_CONTAINERFILE} copies build inputs that are absent from the recipe "
            f"tree: {', '.join(sorted(missing))}."
        )


def containerfile_path() -> Path:
    """Return the path to the owned custom Containerfile (`ADR-004`)."""
    return FRAPPE_DOCKER_DIR / CUSTOM_CONTAINERFILE


def build_context() -> Path:
    """Return the build context — the recipe source root, per `BR-BUILD-009`."""
    return FRAPPE_DOCKER_DIR


def containerfile_arg_defaults(containerfile: Path) -> dict[str, str]:
    """Return the ``ARG NAME=default`` pairs declared by *containerfile*.

    `BR-BUILD-010` requires recording **effective** build args, "including Containerfile
    defaults where unset" — so the defaults are read from the artifact itself rather than
    transcribed, and a recipe edit that moves a default is picked up automatically.
    ``ARG`` lines without a default are skipped: they contribute no value.
    """
    defaults: dict[str, str] = {}
    for line in containerfile.read_text(encoding="utf-8").splitlines():
        tokens = line.strip().split(maxsplit=1)
        if len(tokens) != 2 or tokens[0].upper() != "ARG" or "=" not in tokens[1]:
            continue
        name, _, value = tokens[1].partition("=")
        defaults[name.strip()] = value.strip().strip('"').strip("'")
    return defaults


def recipe_commit() -> str:
    """Return the git commit that most recently touched the recipe tree, or ``""``.

    Provenance under ownership has no separate upstream pin to record (`ADR-059`) — this
    is what supplies ``com.datahenge.cairn.frappe-docker.commit`` instead: the commit in
    *cairn's own* git history that last changed anything under `FRAPPE_DOCKER_DIR`, not a
    commit of the recipe's own (there isn't one, `BR-VEND-004`). An installed wheel carries
    no ``.git`` directory, so this degrades to an empty string rather than raising — it is
    informational provenance, not a build precondition.
    """
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%H", "--", str(FRAPPE_DOCKER_DIR)],
            cwd=FRAPPE_DOCKER_DIR.parent,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _context_copies(containerfile: Path) -> list[str]:
    """Return the build-context paths the Containerfile's ``COPY`` instructions read.

    ``COPY --from=<stage>`` lines are skipped: their sources come from an earlier build
    stage, not from the recipe tree.
    """
    paths: list[str] = []
    for line in containerfile.read_text(encoding="utf-8").splitlines():
        tokens = line.strip().split()
        if not tokens or tokens[0].upper() != "COPY":
            continue
        flags = [t for t in tokens[1:] if t.startswith("--")]
        operands = [t for t in tokens[1:] if not t.startswith("--")]
        if any(flag.startswith("--from=") for flag in flags) or len(operands) < 2:
            continue
        paths.extend(operands[:-1])  # the last operand is the in-image destination
    return paths


def _resolves(source_root: Path, path: str) -> bool:
    """Report whether *path* (possibly a glob) exists under the recipe source root."""
    if any(ch in path for ch in "*?["):
        return any(source_root.glob(path))
    return (source_root / path).exists()
