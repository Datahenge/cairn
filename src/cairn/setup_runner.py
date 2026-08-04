"""The generic `setup` execution engine, shared by every role's installer.

Extracted from `provision.py` when the registry role split out (`ADR-048`) — before that,
`cairn-build setup`/`cairn-adopt setup` were the only two installers, and this engine lived
inline in `provision.py`. `cairn-registry setup` (`registry_provision.py`) needed the same
report-first, dry-run-safe, never-silently-overwrite machinery (`BR-DEPLOY-021`'s seven-point
contract) without pulling in `provision.py`'s own import of `adopt.py`, which reads
`config.py` — a dependency `BR-REG-001` forbids for anything registry-side. This module has
no such dependency; it knows nothing about manifests, environments, or any one role.

`provision.py` re-exports everything here unchanged, so `cli_build.py`/`cli_adopt.py`/
`doctor.py`'s existing `from .provision import Runner, SetupOptions, execute, ...` needed no
changes.
"""

from __future__ import annotations

import grp
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: Free disk a build needs: ~2.5 GB of transient git, a ~4.6 GB builder stage, a ~2.75 GB final
#: image, the registry's own copy, and BuildKit's cache. 30 is the floor, not the comfort point.
MINIMUM_DISK_GB = 30

#: Frappe's asset compilation is memory-hungry. Below this a build can OOM and take live
#: containers with it, which on a box also running ERPNext is an outage caused by a deploy tool.
MINIMUM_MEMORY_GB = 4

#: Shared machine-scoped directory every role's `setup` may write into — `builder.toml`
#: (`ADR-041`), the environment descriptor (`ADR-034`), `registry.toml`/its TLS cert
#: (`BR-REG-002/003`) — a multi-operator VPS needs every login to see these identically.
CERT_DIR = Path("/etc/cairn")

SYSTEMD_DIR = Path("/etc/systemd/system")

DEFAULT_ADMIN_GROUP = "cairn-admins"

SHARED_CONFIG_MODE = 0o2775


@dataclass
class Check:
    """One prerequisite and how it turned out."""

    label: str
    ok: bool
    detail: str

    def render(self) -> str:
        return f"  [{'ok' if self.ok else 'FAIL'}] {self.label:<22} {self.detail}"


@dataclass
class Report:
    """What the run did, so the closing summary is a record rather than a claim."""

    done: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    revert: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Aborted(Exception):
    """A stage could not proceed. Reported, never a traceback."""


@dataclass
class SetupOptions:
    """Everything a `setup` stage might need. Which fields matter depends on the stage —
    a build-only stage never reads `project`, a registry-only one never reads `manifest`.
    """

    dry_run: bool = False
    force: bool = False
    workdir: Path = field(default_factory=Path.cwd)
    manifest: Path | None = None
    environment: str = "production"
    project: str | None = None
    private_ip: str | None = None
    interval: str = "5min"
    build_interval: str = "15min"
    skip_backup: bool = False
    skip_disk_free: bool = False
    admin_group: str | None = DEFAULT_ADMIN_GROUP
    client: str | None = None

    def __post_init__(self) -> None:
        if self.manifest is None:
            self.manifest = self.workdir / "cairn.toml"


@dataclass
class Runner:
    """Executes or narrates, depending on ``--dry-run``.

    Every mutation goes through here, which is what makes the dry run truthful rather than
    approximate — there is no second path that could quietly do something.
    """

    dry_run: bool
    force: bool
    report: Report = field(default_factory=Report)

    def say(self, message: str = "") -> None:
        print(message, file=sys.stderr, flush=True)

    def run(self, command: list[str], *, what: str, timeout: int = 600) -> str:
        """Run *command*, or print it. Raises :class:`Aborted` on failure."""
        self.say(f"    $ {shlex.join(command)}")
        if self.dry_run:
            return ""
        try:
            result = subprocess.run(
                command, timeout=timeout, check=False, capture_output=True, text=True
            )
        except FileNotFoundError as exc:
            raise Aborted(f"{command[0]} is not installed, so {what} is impossible") from exc
        except subprocess.TimeoutExpired as exc:
            raise Aborted(f"{what} timed out after {timeout}s") from exc
        if result.returncode != 0:
            raise Aborted(
                f"{what} failed (exit {result.returncode}): "
                f"{(result.stderr or result.stdout).strip().splitlines()[-1:] or ['no output']}"
            )
        return result.stdout

    def probe(self, command: list[str], timeout: int = 120) -> str | None:
        """Run an informational command, returning stdout or None. Runs even in a dry run.

        Reading is not a mutation, and a dry run that cannot see the host cannot tell you what
        it would do.
        """
        try:
            result = subprocess.run(
                command, timeout=timeout, check=False, capture_output=True, text=True
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return None
        return result.stdout if result.returncode == 0 else None

    def write(self, path: Path, content: str, *, mode: int = 0o644, what: str) -> None:
        """Write *path*, preserving anything already there (`BR-DEPLOY-021` rule 3).

        Convergence (rule 1) covers the mode as well as the content: a file created before a
        mode change shipped, or one a `chmod` outside cairn drifted, must still end up correct
        on a re-run — the directory's own setgid bit only propagates *group ownership* to new
        files, never permission bits, so an unrelated umask is otherwise free to leave a
        supposedly-shared file group-unwritable forever.
        """
        if path.exists() and path.read_text(encoding="utf-8") == content:
            current_mode = path.stat().st_mode & 0o7777
            if current_mode == mode:
                self.say(f"    {path} already correct — leaving it")
                self.report.skipped.append(f"{what} (already correct)")
            elif self.dry_run:
                self.say(
                    f"    {path} content correct — would fix mode {current_mode:o} -> {mode:o}"
                )
                self.report.done.append(f"would correct {path} to mode {mode:o}")
            else:
                os.chmod(path, mode)
                self.say(f"    {path} already correct — fixed mode {current_mode:o} -> {mode:o}")
                self.report.done.append(f"corrected {path} to mode {mode:o}")
            return

        if path.exists() and not self.force:
            raise Aborted(
                f"{path} already exists and differs from what would be written. Re-run with "
                f"--force to replace it; the current file will be kept alongside as a backup."
            )

        self.say(f"    write {path} (mode {mode:o}, {len(content)} bytes)")
        if self.dry_run:
            return

        if path.exists():
            backup = path.with_suffix(path.suffix + ".cairn-backup")
            shutil.copy2(path, backup)
            self.say(f"    kept the previous file as {backup}")
            self.report.warnings.append(f"replaced {path}; previous kept at {backup}")

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        os.chmod(path, mode)
        self.report.done.append(what)


# --- preflight, shared by every role ------------------------------------------


def _check_root() -> Check:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return Check("root", True, "running as root")
    return Check("root", False, "must be run with sudo — it writes to /etc and systemd")


def require_root(runner: Runner) -> None:
    """Gate a single-stage command that has no preceding `preflight` stage of its own."""
    check = _check_root()
    runner.say(check.render())
    if not check.ok:
        raise Aborted(check.detail)


def check_command(runner: Runner, label: str, command: list[str]) -> Check:
    output = runner.probe(command)
    if output is None:
        return Check(label, False, f"not available (`{shlex.join(command)}` failed)")
    return Check(label, True, output.strip().splitlines()[0] if output.strip() else "present")


def _docker_data_dir(runner: Runner) -> Path:
    """Where the engine actually stores images and volumes.

    A separate mount for Docker data is common on a target, and the root filesystem having
    (or lacking) room says nothing about it. Falls back to `/` when the engine can't answer
    yet — not installed, or this preflight is what would install it.
    """
    output = runner.probe(["docker", "info", "--format", "{{.DockerRootDir}}"])
    if output is None or not output.strip():
        return Path("/")
    return Path(output.strip())


def check_disk(path: Path = Path("/")) -> Check:
    """Free disk at *path* against `MINIMUM_DISK_GB` — the caller decides which path, since
    that's role/engine-specific (`_docker_data_dir` here for a fixed-Docker target; a build's
    own engine-aware lookup lives in `provision.py`, `cairn-build setup`'s engine being a
    genuine choice, `ADR-027`)."""
    try:
        free_gb = shutil.disk_usage(path).free / 1_000_000_000
    except OSError as exc:
        return Check("free disk", False, f"cannot be determined ({exc})")
    ok = free_gb >= MINIMUM_DISK_GB
    return Check(
        "free disk",
        ok,
        f"{free_gb:.0f} GB free on {path}" + ("" if ok else f" — needs {MINIMUM_DISK_GB} GB"),
    )


def check_memory() -> Check:
    """Available memory against `MINIMUM_MEMORY_GB` — identical for every role, so this is
    the one preflight primitive every `stage_preflight_*` calls directly rather than each
    keeping its own copy."""
    available = read_available_memory_gb(Path("/proc/meminfo"))
    if available is None:
        return Check("available memory", False, "cannot be determined from /proc/meminfo")
    ok = available >= MINIMUM_MEMORY_GB
    return Check(
        "available memory",
        ok,
        f"{available:.1f} GB available"
        + ("" if ok else f" — needs {MINIMUM_MEMORY_GB} GB; asset builds can OOM"),
    )


def read_available_memory_gb(meminfo: Path) -> float | None:
    """Parse ``MemAvailable`` from /proc/meminfo, in GB.

    ``MemAvailable`` rather than ``MemFree``: free memory excludes reclaimable cache and would
    make a healthy host look starved.
    """
    try:
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024 / 1_000_000_000
    except (OSError, IndexError, ValueError):
        return None
    return None


def base_preflight_checks(runner: Runner, options: SetupOptions) -> tuple[list[Check], Check]:
    """Docker, `docker compose`, free disk under Docker's own data root, and memory.

    Fixed to Docker: every caller of this is either a deploy target (`cairn-adopt setup`,
    always Docker, `ADR-002`) or the local registry (`cairn-registry setup`, which runs
    Docker itself via `docker compose`). `cairn-build setup`'s preflight does not call this
    — its engine is a genuine choice (`ADR-027`) and it assembles its own checks in
    `provision.py`.
    """
    disk_check = check_disk(_docker_data_dir(runner))
    checks = [
        _check_root(),
        check_command(runner, "docker", ["docker", "--version"]),
        check_command(runner, "docker compose", ["docker", "compose", "version"]),
        disk_check,
        check_memory(),
    ]
    for check in checks:
        runner.say(check.render())

    if not disk_check.ok and options.skip_disk_free:
        runner.say("    overridden by --skip-disk-free")
        runner.report.warnings.append(
            "free disk was below the minimum but the check was overridden; "
            "a build or migration may run out of room"
        )
    return checks, disk_check


def fail_on_checks(checks: list[Check], disk_check: Check, options: SetupOptions) -> None:
    failed = [
        check
        for check in checks
        if not check.ok and not (check is disk_check and options.skip_disk_free)
    ]
    if failed:
        raise Aborted(
            f"{len(failed)} prerequisite(s) failed: "
            f"{', '.join(check.label for check in failed)}. Nothing was changed."
        )


# --- /etc/cairn group-sharing, shared by every role (`ADR-043`) --------------


def stage_admin_group(runner: Runner, options: SetupOptions) -> None:
    """Share `/etc/cairn` with a group, so every operator can edit its config files without
    root (`ADR-043`).

    `/etc/cairn` holds `builder.toml` (`ADR-041`, `ADR-042`), the environment descriptor on a
    target, and `registry.toml` on a registry host — machine-scoped facts a multi-operator VPS
    needs every login to see identically.

    Runs before any stage that creates its own files underneath — a file written by root after
    this point still lands in the shared group, not root's own.

    ``--no-admin-group`` skips this entirely: the directory is left however it already is, and
    every subsequent stage still works root-only, exactly as before this existed.
    """
    name = options.admin_group
    if not name:
        runner.report.skipped.append("admin group (skipped: --no-admin-group)")
        return

    gid = group_gid(name)
    if gid is None:
        runner.run(["groupadd", name], what=f"create group '{name}'")
        runner.report.done.append(f"created group '{name}'")
    else:
        runner.say(f"    group '{name}' already exists (gid {gid})")
        runner.report.skipped.append(f"group '{name}' (already exists)")

    if runner.dry_run:
        runner.say(
            f"    share {CERT_DIR}: group '{name}', mode {SHARED_CONFIG_MODE:04o} "
            f"(rwxrws r-x, setgid)"
        )
        return

    CERT_DIR.mkdir(parents=True, exist_ok=True)
    gid = group_gid(name)  # re-read: may have just been created above
    current = CERT_DIR.stat()
    if (
        gid is not None
        and current.st_gid == gid
        and (current.st_mode & 0o7777) == SHARED_CONFIG_MODE
    ):
        runner.say(f"    {CERT_DIR} already shared with group '{name}' — leaving it")
        runner.report.skipped.append(f"{CERT_DIR} sharing (already correct)")
        return

    if gid is not None:
        os.chown(CERT_DIR, -1, gid)
    os.chmod(CERT_DIR, SHARED_CONFIG_MODE)
    runner.report.done.append(
        f"{CERT_DIR} shared with group '{name}' (mode {SHARED_CONFIG_MODE:04o})"
    )


def group_gid(name: str) -> int | None:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        return None


def find_executable(name: str) -> Path:
    """Locate *name* (e.g. ``cairn-build``, ``cairn-adopt``, ``cairn-registry``) installed
    alongside this one.

    Every cairn binary is always installed together, by the same distribution (`pip install` /
    `pipx install --global datahenge-cairn`) — so the reliable way to find one from another is
    as a sibling in the same ``bin/`` directory, not a `PATH` lookup, which depends on how the
    operator happened to invoke `sudo`.
    """
    sibling = Path(sys.argv[0]).resolve().parent / name
    if sibling.is_file():
        return sibling
    found = shutil.which(name)
    if found:
        return Path(found)
    raise Aborted(
        f"cannot find the `{name}` executable next to this one, or on PATH. Is datahenge-cairn "
        f"installed? (`pipx install --global datahenge-cairn`)"
    )


# --- entry points --------------------------------------------------------------


def stages_for(available: tuple[str, ...], stage_funcs: dict, only: str | None) -> tuple[str, ...]:
    """Which stages this run performs, in order.

    *stage_funcs* is one CLI's own fixed stage table — a stage belonging to another CLI is
    simply not a key in it, so it is reported the same way a typo would be, not as a separate
    "wrong role" case.
    """
    if only is None:
        return available
    if only not in stage_funcs:
        raise Aborted(f"unknown stage '{only}'; choose from {', '.join(available)}")
    return (only,)


def execute(
    runner: Runner,
    options: SetupOptions,
    stage_funcs: dict[str, Callable[[Runner, SetupOptions], None]],
    available_stages: tuple[str, ...],
    only: str | None,
    *,
    program: str,
) -> int:
    """Run the chosen stages in order, report a summary, and return the exit code.

    Shared by every role's `setup` — only *stage_funcs* and *available_stages* differ.
    """
    runner.say(f"{program} setup" + (" (dry run)" if runner.dry_run else ""))
    runner.say(f"workdir {options.workdir}")
    runner.say("")

    try:
        chosen = stages_for(available_stages, stage_funcs, only)
        for name in chosen:
            runner.say(f"[{name}]")
            stage_funcs[name](runner, options)
            runner.say("")
    except Aborted as exc:
        runner.say("")
        runner.say(f"Stopped: {exc}")
        _summarize(runner)
        return 2
    except KeyboardInterrupt:
        runner.say("")
        runner.say("Interrupted.")
        _summarize(runner)
        return 130

    _summarize(runner)
    if runner.dry_run:
        runner.say("Nothing was changed. Re-run without --dry-run to apply.")
    return 0


def _summarize(runner: Runner) -> None:
    """Close with a record of what happened, not a claim that it worked (rule 6)."""
    runner.say("--- summary ---")
    for label, entries in (
        ("did", runner.report.done),
        ("skipped", runner.report.skipped),
        ("note", runner.report.warnings),
        ("to revert the stack by hand", runner.report.revert),
    ):
        for entry in entries:
            runner.say(f"  {label}: {entry}")
    if not any((runner.report.done, runner.report.skipped, runner.report.warnings)):
        runner.say("  nothing to do")
