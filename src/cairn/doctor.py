"""Preflight checks behind ``cairn doctor`` (BR-CLI-007).

Answers one question, but which one depends on the machine: *can this machine build?* on
a builder, *can this machine converge?* on a target. Every check runs even after one
fails, so a single invocation reports the full picture; each failure names its fix
(BR-CLI-015) and any failure makes the exit code non-zero (BR-CLI-012).

**Role detection** (`ADR-028`): a descriptor at the fixed path (`ADR-034`) means this
host is a target; its absence means build/control. No flag, and none needed — the same
signal `cairn doctor`'s docstring and `cairn systemd-units` already rely on.

**Build/control checks:** config valid (`BR-CFG-012`); a usable build engine — docker or
podman (`ADR-027`) — plus buildx when the engine is docker; ``git``, which every manifest
ref is resolved with (`BR-BUILD-005`); and the vendored tree clean (BR-VEND-005), free of
upstream git metadata (BR-VEND-007), and complete in its build inputs (BR-VEND-006).

**Target checks:** the descriptor itself parses; Docker is installed and its daemon
reachable (`DEPLOY` is Docker-only, `ADR-002`/`ADR-027`); `docker compose` is present;
the reconcile timer, if installed, is active; and the descriptor's watched tag resolves
in the registry — the exact read `reconcile` performs on every poll, so a failure here is
a failure `reconcile` would also hit.

A **missing** manifest is a warning, not a failure, on a build/control host: doctor is a
machine preflight, run legitimately before a manifest exists. A **malformed** one fails.
The reconcile timer not yet being installed is a warning on a target, not a failure — it
legitimately isn't, before the first manual `cairn reconcile` has succeeded.
"""

from __future__ import annotations

import grp
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import typer

from . import config, descriptor, engine, registry, resolve, systemd, vendor
from .descriptor import Descriptor
from .errors import (
    BuildEngineError,
    CairnError,
    DescriptorError,
    ManifestNotFoundError,
    RegistryError,
)

_LABEL_WIDTH = 16

#: Ceiling on a systemctl/compose probe — these are local, so slow means hung, not busy.
_PROBE_TIMEOUT_SECONDS = 15

#: Shared machine-scoped directory both roles use — `builder.toml` (`ADR-041`), the
#: environment descriptor (`ADR-034`), and whatever group `cairn-provision` sets it up
#: with (`ADR-043`).
SHARED_CONFIG_DIR = Path("/etc/cairn")


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


def run(preferred_engine: str | None = None, manifest_path: Path | None = None) -> int:
    """Run every check, report the results, and return the exit code."""
    return report(run_checks(preferred_engine, manifest_path))


def run_checks(
    preferred_engine: str | None = None, manifest_path: Path | None = None
) -> list[CheckResult]:
    """Run this host's role-appropriate preflight checks (BR-CLI-007, `ADR-028`).

    A descriptor at the fixed path means this host is a target; its absence means
    build/control. *preferred_engine* and *manifest_path* only ever matter on the
    build/control branch.
    """
    if descriptor.exists():
        return run_target_checks()
    return run_build_checks(preferred_engine, manifest_path)


def run_build_checks(
    preferred_engine: str | None = None, manifest_path: Path | None = None
) -> list[CheckResult]:
    """Run the build/control preflight checks in order and return their results.

    Config is checked first because it supplies the engine preference (`BR-CFG-008`);
    an explicit *preferred_engine* still wins over the configured one. The buildx check
    appears only when the selected engine needs it, so a podman machine is not told to
    install a Docker plugin it will never use (`ADR-027`).
    """
    config_result, build_config = check_config(manifest_path)
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
        check_shared_config_dir(),
    ]


def run_target_checks() -> list[CheckResult]:
    """Run the target preflight checks in order and return their results (`ADR-028`).

    The descriptor is checked first because the registry check needs the reference it
    names; if it fails to load there is nothing to check the registry against.
    """
    descriptor_result, loaded = check_descriptor()
    results = [descriptor_result, check_docker(), check_compose(), check_reconcile_timer()]
    if loaded is not None:
        results.append(check_registry_reachable(loaded))
    results.append(check_shared_config_dir())
    return results


def check_config(
    manifest_path: Path | None = None,
) -> tuple[CheckResult, config.BuildConfig | None]:
    """Validate the manifest and build config, returning the config for reuse.

    *manifest_path* comes from ``--manifest`` or is left to `config.find_manifest`'s own
    ``$CAIRN_MANIFEST`` fallback — doctor never searches a directory for one (`ADR-042`).
    A missing manifest **warns** rather than fails — doctor runs legitimately on a
    target, or before a manifest exists. A malformed manifest, or a malformed build
    config, fails (BR-CFG-012, BR-CLI-007).
    """
    label = "config"
    try:
        found = config.find_manifest(manifest_path)
    except ManifestNotFoundError as exc:
        return CheckResult(label, Status.WARN, _first_line(str(exc))), None

    try:
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
    except CairnError as exc:
        return CheckResult(label, Status.FAIL, _first_line(str(exc))), None

    sources = ", ".join(build_config.sources) or "defaults only"
    detail = f"{found.name} valid, {len(manifest.apps)} app(s); build config: {sources}"
    return CheckResult(label, Status.OK, detail), build_config


def check_shared_config_dir() -> CheckResult:
    """Report `SHARED_CONFIG_DIR`'s group and whether the invoking user can write to it.

    Purely informational (`ADR-043`) — cairn prescribes no particular group name and
    never changes what it finds; an operator may set this up however they like, or not
    at all. Read-only, so a multi-operator host surfaces the fact plainly rather than an
    operator discovering it the day their own `builder.toml` edit silently fails.
    """
    label = "shared config"
    if not SHARED_CONFIG_DIR.is_dir():
        return CheckResult(
            label,
            Status.WARN,
            f"{SHARED_CONFIG_DIR} does not exist yet — run cairn-provision, or create it "
            f"by hand",
        )

    try:
        info = SHARED_CONFIG_DIR.stat()
    except OSError as exc:
        return CheckResult(label, Status.WARN, f"{SHARED_CONFIG_DIR} cannot be inspected — {exc}")

    try:
        group_name = grp.getgrgid(info.st_gid).gr_name
    except KeyError:
        group_name = str(info.st_gid)

    setgid = bool(info.st_mode & 0o2000)
    group_writable = bool(info.st_mode & 0o020)
    member = info.st_gid == os.getgid() or info.st_gid in os.getgroups()

    detail = (
        f"{SHARED_CONFIG_DIR} owned by group '{group_name}'"
        f"{' (setgid)' if setgid else ''}, "
        f"{'group-writable' if group_writable else 'not group-writable'}, current user "
        f"{'is' if member else 'is not'} a member"
    )
    return CheckResult(label, Status.OK, detail)


def check_descriptor() -> tuple[CheckResult, Descriptor | None]:
    """Validate the environment descriptor, returning it for reuse (`BR-DEPLOY-010`).

    Doctor only reaches this branch because `descriptor.exists()` was already true
    (`run_checks`), so a failure here means the file is present but does not parse —
    the same failure `reconcile` would hit on its next poll.
    """
    label = "descriptor"
    try:
        loaded = descriptor.load()
    except DescriptorError as exc:
        return CheckResult(label, Status.FAIL, _first_line(str(exc))), None

    detail = (
        f"environment '{loaded.environment}', site '{loaded.site}', watching {loaded.reference}"
    )
    return CheckResult(label, Status.OK, detail), loaded


def check_docker() -> CheckResult:
    """Confirm Docker is installed and its daemon reachable.

    `DEPLOY` is Docker-only regardless of what a builder chose (`ADR-002`, `ADR-027`), so
    this checks `docker` specifically rather than reusing build-engine detection, which
    would also accept podman.
    """
    label = "docker"
    try:
        selected = engine.check(engine.DOCKER)
    except BuildEngineError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))
    return CheckResult.of(label, True, f"docker v{selected.version}")


def check_compose() -> CheckResult:
    """Confirm the `docker compose` plugin is present — every reconcile pass shells to it."""
    label = "docker compose"
    result = _run(["docker", "compose", "version"])
    if result is None or result.returncode != 0:
        detail = _first_line(result.stderr or result.stdout) if result else ""
        return CheckResult.of(
            label, False, detail or "`docker compose version` failed; is the plugin installed?"
        )
    return CheckResult.of(label, True, _first_line(result.stdout) or "present")


def check_reconcile_timer() -> CheckResult:
    """Report whether the reconcile timer is installed and active.

    A warning, not a failure: a target legitimately has no timer yet before the first
    manual `cairn reconcile` has succeeded — installing it earlier is what turns one wrong
    descriptor into a wrong deploy every few minutes, which is why `systemd-units` prints
    rather than installs. Unlike `check_compose`, a nonzero exit here is the *normal* answer
    for "not active" (`systemctl is-active`'s documented behaviour) — not a failure to run.
    """
    label = "reconcile timer"
    unit = f"{systemd.UNIT_NAME}.timer"
    result = _run(["systemctl", "is-active", unit])
    if result is None:
        return CheckResult(
            label, Status.WARN, "systemd not available, or the timer is not installed"
        )

    state = result.stdout.strip() or result.stderr.strip() or "unknown"
    if state == "active":
        return CheckResult(label, Status.OK, f"{unit} is active")
    return CheckResult(
        label,
        Status.WARN,
        f"{unit} is {state} — install it with `cairn systemd-units` once a manual "
        f"`cairn reconcile` has succeeded",
    )


def check_registry_reachable(loaded: Descriptor) -> CheckResult:
    """Resolve the descriptor's watched tag in the registry — reconcile's own read.

    Exercising the exact call `reconcile` makes on every poll (`BR-DEPLOY-002`) means a
    failure here is a failure reconcile would also hit, with the same message it would
    show — never a doctor-specific approximation of the real check.
    """
    label = "registry"
    try:
        ref = registry.parse_ref(loaded.reference)
        digest = registry.digest_of(ref)
    except RegistryError as exc:
        return CheckResult(label, Status.FAIL, _first_line(str(exc)))
    return CheckResult(label, Status.OK, f"{loaded.reference} resolves to {digest[:19]}")


def _run(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Run *command*, returning the completed process, or None if it could not run at all.

    Deliberately returns the whole result rather than picking stdout-on-success the way
    other probes in this codebase do: `check_compose` and `check_reconcile_timer` disagree
    about what a nonzero exit means, so the interpretation has to stay with each caller.
    """
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=_PROBE_TIMEOUT_SECONDS, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


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
