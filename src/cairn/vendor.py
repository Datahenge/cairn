"""Vendored-tree management: thin wrappers over ``ventwig`` plus the integrity checks
used as build preconditions.

cairn never re-implements ventwig. ``status``/``sync`` shell out to it (BR-CLI-006), and
the drift precondition trusts ventwig's **exit code** — 0 when every source is clean, 1 on
any drift — as the authoritative signal (BR-VEND-005), avoiding brittle output parsing.
ventwig is invoked as ``python -m ventwig`` so it always resolves from cairn's own
environment rather than an unrelated one on ``PATH``.

``assert_clean`` / ``assert_no_nested_git`` / ``assert_build_inputs`` are the reusable
build preconditions (BR-VEND-005, BR-VEND-007, BR-VEND-006); ``cairn doctor`` runs the
same three ahead of time (BR-CLI-007).
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from .errors import VendorDriftError, VendorInputsMissingError, VendorToolError
from .project import read_vendor_sources

GIT_DIR_NAME = ".git"

#: The vendored source that supplies the image build inputs (BR-VEND-006).
FRAPPE_DOCKER_SOURCE = "frappe_docker"

#: The custom-image Containerfile cairn builds with, relative to that source (ADR-004).
CUSTOM_CONTAINERFILE = "images/custom/Containerfile"


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


def assert_build_inputs(root: Path, source_name: str = FRAPPE_DOCKER_SOURCE) -> None:
    """Raise :class:`VendorInputsMissingError` unless the vendored tree carries every
    build input the custom Containerfile needs (BR-VEND-006).

    The required set is derived from the Containerfile itself — each path it copies from
    the build context — so it stays correct across upstream bumps rather than encoding a
    list that silently rots.
    """
    source_root = root / _source_path(root, source_name)
    containerfile = source_root / CUSTOM_CONTAINERFILE
    if not containerfile.is_file():
        raise VendorInputsMissingError(
            f"Vendored source '{source_name}' is missing {CUSTOM_CONTAINERFILE} "
            f"(expected at {containerfile}). Restore it with `cairn vendor sync`."
        )

    missing = [path for path in _context_copies(containerfile) if not _resolves(source_root, path)]
    if missing:
        raise VendorInputsMissingError(
            f"{CUSTOM_CONTAINERFILE} copies build inputs that are absent from the vendored "
            f"tree: {', '.join(sorted(missing))}. Restore them with `cairn vendor sync`."
        )


def containerfile_path(root: Path, source_name: str = FRAPPE_DOCKER_SOURCE) -> Path:
    """Return the path to the vendored custom Containerfile (`ADR-004`)."""
    return root / _source_path(root, source_name) / CUSTOM_CONTAINERFILE


def build_context(root: Path, source_name: str = FRAPPE_DOCKER_SOURCE) -> Path:
    """Return the build context — the vendored source root, per `BR-BUILD-009`."""
    return root / _source_path(root, source_name)


def containerfile_arg_defaults(containerfile: Path) -> dict[str, str]:
    """Return the ``ARG NAME=default`` pairs declared by *containerfile*.

    `BR-BUILD-010` requires recording **effective** build args, "including Containerfile
    defaults where unset" — so the defaults are read from the artifact itself rather than
    transcribed, and a vendored-pin bump that moves a default is picked up automatically.
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


def _source_path(root: Path, source_name: str) -> str:
    """Return the declared ``local_path`` of the named vendored source."""
    for src in read_vendor_sources(root):
        if src.name == source_name:
            return src.local_path
    raise VendorInputsMissingError(
        f"No vendored source named '{source_name}' is declared in "
        f"{root / 'pyproject.toml'} under [[tool.ventwig.sources]]."
    )


def _context_copies(containerfile: Path) -> list[str]:
    """Return the build-context paths the Containerfile's ``COPY`` instructions read.

    ``COPY --from=<stage>`` lines are skipped: their sources come from an earlier build
    stage, not from the vendored tree.
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
    """Report whether *path* (possibly a glob) exists under the vendored source root."""
    if any(ch in path for ch in "*?["):
        return any(source_root.glob(path))
    return (source_root / path).exists()


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
