"""Preflight checks behind ``cairn doctor`` (BR-CLI-007).

Answers one question — *can this machine build?* — before a long build discovers the
answer the slow way. Every check runs even after one fails, so a single invocation
reports the full picture; each failure names its fix (BR-CLI-015) and any failure makes
the exit code non-zero (BR-CLI-012).

Checks: config valid (`BR-CFG-012`); a usable build engine — docker or podman
(`ADR-027`) — plus buildx when the engine is docker; ``git``, which every manifest ref is
resolved with (`BR-BUILD-005`); and the vendored tree clean (BR-VEND-005), free of
upstream git metadata (BR-VEND-007), and complete in its build inputs (BR-VEND-006).

A **missing** manifest is a warning, not a failure: doctor is a machine preflight, run
legitimately on a target or before a manifest exists. A **malformed** one fails.

One leg of BR-CLI-007 lands later by design: the *target-role* checks (Docker + Compose,
systemd, registry reachability). `ADR-028` makes doctor role-aware; that branch lands
with `DEPLOY`. Today doctor implements the build/control role only.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

import typer

from . import config, engine, resolve, vendor
from .errors import BuildEngineError, CairnError, ManifestNotFoundError

_LABEL_WIDTH = 16


class Status(Enum):
    """A check's verdict. Only ``FAIL`` affects the exit code (BR-CLI-012)."""

    OK = ("OK", typer.colors.GREEN)
    WARN = ("WARN", typer.colors.YELLOW)
    FAIL = ("FAIL", typer.colors.RED)

    def __init__(self, label: str, colour: str) -> None:
        self.mark = label
        self.colour = colour


@dataclass(frozen=True)
class CheckResult:
    """The outcome of one preflight check: a label, a verdict, and one line of detail.

    On failure *detail* states the fix, not merely the symptom (BR-CLI-015).
    """

    label: str
    status: Status
    detail: str

    @classmethod
    def of(cls, label: str, ok: bool, detail: str) -> CheckResult:
        """Build a pass/fail result, for the checks with no warning state."""
        return cls(label, Status.OK if ok else Status.FAIL, detail)


def run(preferred_engine: str | None = None) -> int:
    """Run every check, report the results, and return the exit code."""
    return report(run_checks(preferred_engine))


def run_checks(preferred_engine: str | None = None) -> list[CheckResult]:
    """Run all build-role preflight checks in order and return their results (BR-CLI-007).

    Config is checked first because it supplies the engine preference (`BR-CFG-008`);
    an explicit *preferred_engine* still wins over the configured one. The buildx check
    appears only when the selected engine needs it, so a podman machine is not told to
    install a Docker plugin it will never use (`ADR-027`).
    """
    config_result, build_config = check_config()
    engine_result, selected = check_build_engine(
        preferred_engine or (build_config.engine if build_config else None)
    )

    results = [config_result, engine_result]
    if selected is not None and selected.needs_buildx:
        results.append(check_buildx())
    return [
        *results,
        check_git(),
        _guard("vendored tree", vendor.assert_clean, "matches its recorded pin"),
        _guard("vendor .git", vendor.assert_no_nested_git, "no nested .git"),
        _guard("build inputs", vendor.assert_build_inputs, "Containerfile complete"),
    ]


def check_config() -> tuple[CheckResult, config.BuildConfig | None]:
    """Validate the manifest and build config, returning the config for reuse.

    A missing manifest **warns** rather than fails — doctor runs legitimately on a
    target, or before a manifest exists. A malformed manifest, or a malformed build
    config, fails (BR-CFG-012, BR-CLI-007).
    """
    label = "config"
    try:
        manifest_path = config.find_manifest()
    except ManifestNotFoundError as exc:
        return CheckResult(label, Status.WARN, _first_line(str(exc))), None

    try:
        manifest = config.load_manifest(manifest_path)
        build_config = config.load_build_config(manifest_path)
    except CairnError as exc:
        return CheckResult(label, Status.FAIL, _first_line(str(exc))), None

    sources = ", ".join(str(p) for p in build_config.sources) or "defaults only"
    detail = f"{manifest_path.name} valid, {len(manifest.apps)} app(s); build config: {sources}"
    return CheckResult(label, Status.OK, detail), build_config


def report(results: list[CheckResult]) -> int:
    """Print *results* and return ``0`` unless some check failed (BR-CLI-012).

    Warnings are reported but do not affect the exit code.
    """
    for result in results:
        typer.secho(f"{result.status.mark:<5}", fg=result.status.colour, bold=True, nl=False)
        typer.echo(f"{result.label:<{_LABEL_WIDTH}}{result.detail}")

    failures = [r for r in results if r.status is Status.FAIL]
    warnings = [r for r in results if r.status is Status.WARN]
    if failures:
        typer.secho(
            f"\n{len(failures)} of {len(results)} checks failed.", fg=typer.colors.RED, err=True
        )
        return 1

    suffix = f" ({len(warnings)} warning(s))" if warnings else ""
    typer.secho(f"\nAll {len(results)} checks passed{suffix}.", fg=typer.colors.GREEN)
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
        return CheckResult.of("build engine", False, _first_line(str(exc))), None
    return CheckResult.of("build engine", True, f"{selected.name} v{selected.version}"), selected


def check_buildx() -> CheckResult:
    """Check that the ``docker buildx`` plugin is installed and runnable.

    Docker-only: podman builds with buildah in-process and has no such plugin.
    """
    label = "docker buildx"
    try:
        return CheckResult.of(label, True, _first_line(engine.buildx_version()) or "present")
    except BuildEngineError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))


def check_git() -> CheckResult:
    """Check that git is installed — every manifest ref is resolved with it (BR-CLI-007).

    A machine without git would otherwise fail at ref resolution, well into a build.
    """
    label = "git"
    try:
        return CheckResult.of(label, True, f"v{resolve.git_version()}")
    except CairnError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))


def _guard(label: str, assertion: Callable[[], None], passed_detail: str) -> CheckResult:
    """Turn one of the ``vendor.assert_*`` build preconditions into a :class:`CheckResult`.

    doctor reports rather than aborts, so the operator sees every problem at once; the
    hard stop stays with the build itself (BR-VEND-005).
    """
    try:
        assertion()
    except CairnError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))
    return CheckResult.of(label, True, passed_detail)


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""
