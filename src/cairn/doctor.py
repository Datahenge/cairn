"""Preflight checks behind ``cairn doctor`` (BR-CLI-007).

Answers one question — *can this machine build?* — before a long build discovers the
answer the slow way. Every check runs even after one fails, so a single invocation
reports the full picture; each failure names its fix (BR-CLI-015) and any failure makes
the exit code non-zero (BR-CLI-012).

Checks: a usable build engine — docker or podman (`ADR-027`) — plus buildx when the
engine is docker; and the vendored tree clean (BR-VEND-005), free of upstream git
metadata (BR-VEND-007), and complete in its build inputs (BR-VEND-006).

Two legs of BR-CLI-007 land later, both by design:
* *config valid* — awaits the config module, which also supplies the configured engine
  preference (`BR-CFG-008`) currently passed as ``None`` here.
* *target-role checks* (Docker + Compose, systemd, registry reachability) — `ADR-028`
  makes doctor role-aware; the target branch lands with `DEPLOY`. Today doctor
  implements the build/control role only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import typer

from . import engine, vendor
from .errors import BuildEngineError, CairnError

_LABEL_WIDTH = 16


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one preflight check: a label, a verdict, and one line of detail.

    On failure *detail* states the fix, not merely the symptom (BR-CLI-015).
    """

    label: str
    ok: bool
    detail: str


def run(root: Path, preferred_engine: str | None = None) -> int:
    """Run every check under *root*, report the results, and return the exit code."""
    return report(run_checks(root, preferred_engine))


def run_checks(root: Path, preferred_engine: str | None = None) -> list[CheckResult]:
    """Run all build-role preflight checks in order and return their results (BR-CLI-007).

    *preferred_engine* is the build config's ``engine =`` (`BR-CFG-008`); ``None`` means
    auto-detect. The buildx check appears only when the selected engine needs it, so a
    podman machine is not told to install a Docker plugin it will never use (`ADR-027`).
    """
    engine_result, selected = check_build_engine(preferred_engine)
    results = [engine_result]
    if selected is not None and selected.needs_buildx:
        results.append(check_buildx())
    return [
        *results,
        _guard("vendored tree", lambda: vendor.assert_clean(root), "matches .ventwig.lock"),
        _guard("vendor .git", lambda: vendor.assert_no_nested_git(root), "no nested .git"),
        _guard("build inputs", lambda: vendor.assert_build_inputs(root), "Containerfile complete"),
    ]


def report(results: list[CheckResult]) -> int:
    """Print *results* and return ``0`` when all passed, ``1`` otherwise (BR-CLI-012)."""
    for result in results:
        mark, colour = ("OK", typer.colors.GREEN) if result.ok else ("FAIL", typer.colors.RED)
        typer.secho(f"{mark:<5}", fg=colour, bold=True, nl=False)
        typer.echo(f"{result.label:<{_LABEL_WIDTH}}{result.detail}")

    failures = [r for r in results if not r.ok]
    if failures:
        typer.secho(
            f"\n{len(failures)} of {len(results)} checks failed.", fg=typer.colors.RED, err=True
        )
        return 1
    typer.secho(f"\nAll {len(results)} checks passed.", fg=typer.colors.GREEN)
    return 0


def check_build_engine(
    preferred: str | None = None,
) -> tuple[CheckResult, engine.BuildEngine | None]:
    """Resolve the build engine, returning both the reportable result and the selection.

    The selection is returned so the caller knows whether to check for buildx (`ADR-027`).
    """
    try:
        selected = engine.detect(preferred)
    except BuildEngineError as exc:
        return CheckResult("build engine", False, _first_line(str(exc))), None
    return CheckResult("build engine", True, f"{selected.name} v{selected.version}"), selected


def check_buildx() -> CheckResult:
    """Check that the ``docker buildx`` plugin is installed and runnable.

    Docker-only: podman builds with buildah in-process and has no such plugin.
    """
    label = "docker buildx"
    try:
        return CheckResult(label, True, _first_line(engine.buildx_version()) or "present")
    except BuildEngineError as exc:
        return CheckResult(label, False, _first_line(str(exc)))


def _guard(label: str, assertion: Callable[[], None], passed_detail: str) -> CheckResult:
    """Turn one of the ``vendor.assert_*`` build preconditions into a :class:`CheckResult`.

    doctor reports rather than aborts, so the operator sees every problem at once; the
    hard stop stays with the build itself (BR-VEND-005).
    """
    try:
        assertion()
    except CairnError as exc:
        return CheckResult(label, False, _first_line(str(exc)))
    return CheckResult(label, True, passed_detail)


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""
