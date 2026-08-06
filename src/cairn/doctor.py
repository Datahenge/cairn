"""Preflight checks behind `cairn-build doctor` / `cairn-adopt doctor` (`BR-CLI-007`).

Two fixed check sets, one per binary — no role detection (`ADR-028` retired by `ADR-046`):
the binary invoked already says which questions apply, *can this machine build?* for
`cairn-build`, *can this machine converge?* for `cairn-adopt`. Every check runs even after
one fails, so a single invocation reports the full picture; each failure names its fix
(BR-CLI-015) and any failure makes the exit code non-zero (BR-CLI-012).

**`cairn-build doctor` checks:** config valid (`BR-CFG-012`); a usable build engine —
docker or podman (`ADR-027`) — plus buildx when the engine is docker; free disk under the
engine's own data root and available memory, the same floors `setup`'s preflight gates a
build on (`BR-DEPLOY-021`); ``git``, which every manifest ref is resolved with
(`BR-BUILD-005`); the recipe tree complete in its build inputs (BR-VEND-003); and,
informationally only, which client manifests already exist under `/srv/cairn/`
(`BR-CLI-022`). When a manifest was found, every one of its refs is also resolved live
(`resolve.resolve_manifest`, `ADR-067`) — the same call `build` itself makes — so an
unauthenticated `github.com` app, or any other unreachable/moved ref, fails here rather
than mid-build.

**`cairn-adopt doctor` checks:** the descriptor itself parses; Docker is installed and its
daemon reachable (`DEPLOY` is Docker-only, `ADR-002`/`ADR-027`); `docker compose` is
present; the reconcile timer, if installed, is active; and the descriptor's watched tag
resolves in the registry — the exact read `reconcile` performs on every poll, so a failure
here is a failure `reconcile` would also hit.

A **missing** manifest is a warning, not a failure, on `cairn-build doctor`: it is a
machine preflight, run legitimately before a manifest exists. A **malformed** one fails.
The reconcile timer not yet being installed is a warning on `cairn-adopt doctor`, not a
failure — it legitimately isn't, before the first manual `cairn-adopt reconcile` has
succeeded.
"""

from __future__ import annotations

import grp
import os
import shutil
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
from .provision import MANIFEST_ROOT
from .setup_runner import MINIMUM_DISK_GB, MINIMUM_MEMORY_GB, read_available_memory_gb

_LABEL_WIDTH = 16

#: Ceiling on a systemctl/compose probe — these are local, so slow means hung, not busy.
_PROBE_TIMEOUT_SECONDS = 15

#: Shared machine-scoped directory both roles use — `builder.toml` (`ADR-041`), the
#: environment descriptor (`ADR-034`), and whatever group `setup` sets it up
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


def run_build(preferred_engine: str | None = None, manifest_path: Path | None = None) -> int:
    """Run `cairn-build doctor`'s checks, report the results, and return the exit code."""
    return report(run_build_checks(preferred_engine, manifest_path))


def run_target() -> int:
    """Run `cairn-adopt doctor`'s checks, report the results, and return the exit code."""
    return report(run_target_checks())


def run_build_checks(
    preferred_engine: str | None = None, manifest_path: Path | None = None
) -> list[CheckResult]:
    """Run the build/control preflight checks in order and return their results.

    Config is checked first because it supplies the engine preference (`BR-CFG-008`);
    an explicit *preferred_engine* still wins over the configured one. The buildx check
    appears only when the selected engine needs it, so a podman machine is not told to
    install a Docker plugin it will never use (`ADR-027`). Disk and memory are checked
    right after — the same host-resource floors `setup`'s preflight gates a build on
    (`BR-DEPLOY-021`) — once the engine is known, since free disk is read from wherever
    that engine actually stores images, not assumed to be `/`.
    """
    config_result, build_config, manifest = check_config(manifest_path)
    engine_result, selected = check_build_engine(
        preferred_engine or (build_config.engine if build_config else None)
    )

    results = [config_result, engine_result]
    if selected is not None and selected.needs_buildx:
        results.append(check_buildx())
    results.append(check_disk(selected))
    results.append(check_memory())
    results.extend(
        [
            check_git(),
            _guard("build inputs", vendor.assert_build_inputs, "Containerfile complete"),
            check_shared_config_dir(),
            check_known_manifests(),
        ]
    )
    if manifest is not None:
        results.append(check_github_reachability(manifest))
    return results


def run_target_checks() -> list[CheckResult]:
    """Run the target preflight checks in order and return their results.

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
) -> tuple[CheckResult, config.BuildConfig | None, config.Manifest | None]:
    """Validate the manifest and build config, returning both for reuse.

    *manifest_path* comes from ``--manifest`` or is left to `config.find_manifest`'s own
    ``$CAIRN_MANIFEST`` fallback — doctor never searches a directory for one (`ADR-042`).
    A missing manifest **warns** rather than fails — doctor runs legitimately on a
    target, or before a manifest exists. A malformed manifest, or a malformed build
    config, fails (BR-CFG-012, BR-CLI-007). The parsed `Manifest` is returned alongside
    the build config so `check_github_reachability` can reuse it without a second parse
    (`ADR-067`).
    """
    label = "config"
    try:
        found = config.find_manifest(manifest_path)
    except ManifestNotFoundError as exc:
        return CheckResult(label, Status.WARN, _first_line(str(exc))), None, None

    try:
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
    except CairnError as exc:
        return CheckResult(label, Status.FAIL, _first_line(str(exc))), None, None

    sources = ", ".join(build_config.sources) or "defaults only"
    detail = f"{found.name} valid, {len(manifest.apps)} app(s); build config: {sources}"
    return CheckResult(label, Status.OK, detail), build_config, manifest


def check_github_reachability(manifest: config.Manifest) -> CheckResult:
    """Resolve every ref in *manifest* live — the exact call `build` itself makes.

    Reuses `resolve.resolve_manifest` rather than reproducing ref-resolution logic, so a
    `github.com` app that would fail for lack of a token is caught here, with the same
    actionable message `BR-BUILD-016` point 5 already gives a failed build, before the
    first unattended timer run rather than during it (`ADR-067`). Uses whichever
    `$CAIRN_GITHUB_TOKEN` the invoking shell has exported, mirroring `cairn-build build`'s
    own interactive path — `setup-timer`'s pre-write gate checks the unit's own,
    file-scoped environment instead (`provision.py`).
    """
    label = "github reachability"
    try:
        resolve.resolve_manifest(manifest)
    except CairnError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))
    return CheckResult.of(label, True, f"{len(manifest.apps) + 1} ref(s) resolved")


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
            f"{SHARED_CONFIG_DIR} does not exist yet — run this CLI's `setup` subcommand, "
            f"or create it by hand",
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


def check_known_manifests() -> CheckResult:
    """List manifests found under `/srv/cairn/*/*.toml`, and flag any duplicate
    (`image_name`, `environment`) declaration within a client (`BR-CLI-007`, `ADR-052`).

    A report, not a discovery mechanism: nothing here selects a manifest for any command to
    act on — every manifest-consuming command still requires an explicit `--manifest`/
    `$CAIRN_MANIFEST` (`BR-CLI-014`, unchanged). The duplicate check is validation only, for
    the same reason: two manifests can legitimately share an `environment` name as long as
    their `image_name`s differ (a registry tag is scoped to one repository), so what's
    actually unsafe is the pair repeating together — case-insensitively, so `staging` and
    `Staging` collide.
    """
    label = "known manifests"
    if not MANIFEST_ROOT.is_dir():
        return CheckResult(label, Status.OK, f"none found under {MANIFEST_ROOT}")

    clients = sorted(p for p in MANIFEST_ROOT.iterdir() if p.is_dir())
    if not clients:
        return CheckResult(label, Status.OK, f"none found under {MANIFEST_ROOT}")

    names: list[str] = []
    collisions: list[str] = []
    for client_dir in clients:
        seen: dict[tuple[str, str], Path] = {}
        for manifest_path in sorted(client_dir.glob("*.toml")):
            names.append(f"{client_dir.name}/{manifest_path.name}")
            try:
                manifest = config.load_manifest(manifest_path)
            except CairnError:
                continue
            if manifest.environment is None:
                continue
            key = (manifest.image_name, manifest.environment.lower())
            if key in seen:
                collisions.append(
                    f"{client_dir.name}: '{manifest.image_name}'/'{manifest.environment}' "
                    f"declared by both {seen[key].name} and {manifest_path.name}"
                )
            else:
                seen[key] = manifest_path

    if collisions:
        return CheckResult(label, Status.WARN, "; ".join(collisions))
    if not names:
        return CheckResult(label, Status.OK, f"none found under {MANIFEST_ROOT}")
    return CheckResult(label, Status.OK, f"{', '.join(names)} (under {MANIFEST_ROOT})")


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
    manual `cairn-adopt reconcile` has succeeded — installing it earlier is what turns one wrong
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
        f"{unit} is {state} — install it with `cairn-adopt systemd-units` once a manual "
        f"`cairn-adopt reconcile` has succeeded",
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


def _engine_data_dir(selected: engine.BuildEngine | None) -> Path:
    """Where *selected* actually stores images and volumes.

    A separate mount for engine data is common on a build machine, and the root
    filesystem having (or lacking) room says nothing about it, so this is read rather
    than assumed. Falls back to `/` when unknown — no engine was selected, or the probe
    itself failed.
    """
    if selected is None:
        return Path("/")
    if selected.name == engine.PODMAN:
        result = _run([engine.PODMAN, "info", "--format", "{{.Store.GraphRoot}}"])
    else:
        result = _run([engine.DOCKER, "info", "--format", "{{.DockerRootDir}}"])
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return Path("/")
    return Path(result.stdout.strip())


def check_disk(selected: engine.BuildEngine | None) -> CheckResult:
    """Confirm free disk under the engine's data root meets what a build needs.

    Room for a transient git checkout, the builder stage, the final image, and
    BuildKit's cache — the same floor `setup`'s preflight gates a build on
    (`MINIMUM_DISK_GB`).
    """
    label = "free disk"
    path = _engine_data_dir(selected)
    try:
        free_gb = shutil.disk_usage(path).free / 1_000_000_000
    except OSError as exc:
        return CheckResult(label, Status.FAIL, f"cannot be determined ({exc})")
    ok = free_gb >= MINIMUM_DISK_GB
    detail = f"{free_gb:.0f} GB free on {path}" + ("" if ok else f" — needs {MINIMUM_DISK_GB} GB")
    return CheckResult.of(label, ok, detail)


def check_memory() -> CheckResult:
    """Confirm available memory meets what Frappe's asset build needs.

    Below `MINIMUM_MEMORY_GB` a build can OOM and take live containers with it — the
    same floor `setup`'s preflight gates a build on.
    """
    label = "available memory"
    available = read_available_memory_gb(Path("/proc/meminfo"))
    if available is None:
        return CheckResult(label, Status.FAIL, "cannot be determined from /proc/meminfo")
    ok = available >= MINIMUM_MEMORY_GB
    detail = f"{available:.1f} GB available" + (
        "" if ok else f" — needs {MINIMUM_MEMORY_GB} GB; asset builds can OOM"
    )
    return CheckResult.of(label, ok, detail)


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
    hard stop stays with the build itself (BR-VEND-003).
    """
    try:
        assertion()
    except CairnError as exc:
        return CheckResult.of(label, False, _first_line(str(exc)))
    return CheckResult.of(label, True, passed_detail)


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""
