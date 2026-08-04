"""Provision a cairn build machine or deploy target — the `setup` subcommand shared by
`cairn-build` and `cairn-adopt` (`BR-CLI-021`, `BR-DEPLOY-021`, `ADR-046`).

    sudo cairn-build setup --dry-run
    sudo cairn-build setup

    sudo cairn-adopt setup --dry-run
    sudo cairn-adopt setup

Installed the same way as the rest of cairn — `pip install datahenge-cairn`, or for a
machine meant to outlive any one operator's own account, `sudo pipx install --global
datahenge-cairn` (installs to a shared system location, not tied to a personal login
that might one day be deactivated).

**Why this is a subcommand, not an ordinary one.** Two decisions would break if `setup`
behaved like `build`, `push`, or `examine`: cairn *emits* systemd units and never installs
them except through this explicit path (`ADR-035`), and cairn writes nothing to a
data-plane volume (`ADR-022`) — a pre-install `bench backup` writes into the sites volume.
An operator running `setup` with explicit privilege *is* the operator doing those things.
`setup` checks its own privilege and exits, reporting the shortfall, rather than attempt a
partial run without it — the invariant across both CLIs holds: **cairn prints host
configuration; the operator installs it — `setup` is the one exception, and it exists
precisely so that exception never leaks into an ordinary command.**

There is no `--role` flag (`ADR-046`, retiring the separate `cairn-provision` program):
`cairn-build setup` runs only the builder stages, `cairn-adopt setup` only the target
stages — the binary invoked already says which. `cairn-adopt setup`'s descriptor stage
calls straight into :mod:`cairn.adopt` and its timer stage into :mod:`cairn.systemd`, both
in-process — there is no sibling binary left to shell out to.

It also shares `/etc/cairn` with a group (`--admin-group`, default `cairn-admins`,
`ADR-043`) so `builder.toml` and the environment descriptor can be edited by every
operator on a multi-login box without sudo — `--no-admin-group` skips this and leaves the
directory exactly as found.

**The contract it keeps** (`BR-DEPLOY-021`), which is also why it is Python rather than
shell — this runs as root on client infrastructure and therefore has to be testable:

1. **Idempotent.** Re-running converges; it is what makes the second and third machine cheap.
2. **`--dry-run` prints every action, including every command, and writes nothing.**
3. **Never silently overwrites.** A file it would replace is preserved beside itself and named.
4. **Handles no secrets.** Key material it creates is owner-only; nothing is prompted or logged.
5. **Gates before acting.** Every prerequisite is checked and *all* results reported before the
   first change.
6. **Verifies what it claims.** A backup is confirmed non-empty, a registry confirmed reachable,
   a descriptor confirmed to parse.
7. **Is never the only path.** Every action is reported as the command an operator could run.

It creates no site, volume, or database: `BR-DEPLOY-007` keeps that the operator's job.
"""

from __future__ import annotations

import grp
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from . import adopt as adopt_module
from . import systemd

# --- host requirements -------------------------------------------------------

#: Free disk a build needs: ~2.5 GB of transient git, a ~4.6 GB builder stage, a ~2.75 GB final
#: image, the registry's own copy, and BuildKit's cache. 30 is the floor, not the comfort point.
MINIMUM_DISK_GB = 30

#: Frappe's asset compilation is memory-hungry. Below this a build can OOM and take live
#: containers with it, which on a box also running ERPNext is an outage caused by a deploy tool.
MINIMUM_MEMORY_GB = 4

REGISTRY_PORT = 5000
REGISTRY_DIR = Path("/opt/cairn-registry")
CERT_DIR = Path("/etc/cairn")
DESCRIPTOR_PATH = Path("/etc/cairn/adopt.toml")
SYSTEM_CA_DIR = Path("/usr/local/share/ca-certificates")
DOCKER_CERT_DIR = Path("/etc/docker/certs.d")
SYSTEMD_DIR = Path("/etc/systemd/system")

#: How long the self-signed certificate lasts. 825 days is the longest most clients accept.
CERT_DAYS = 825

#: Default name for the group `/etc/cairn` is shared with (`ADR-043`). Just a starting point
#: — `--admin-group` renames it, and an operator who prefers their own scheme can chown the
#: directory however they like; cairn never checks for this name specifically.
DEFAULT_ADMIN_GROUP = "cairn-admins"

#: rwxrws r-x + setgid: owner and group get full access (setgid so files later created
#: inside inherit the group, not the creating process's own primary group); world keeps
#: read/traverse but not write — nothing under /etc/cairn is a secret (`BR-CFG-010`), only
#: writes are meant to be restricted to the shared group.
SHARED_CONFIG_MODE = 0o2775

#: rw-rw-r--, for a file under `/etc/cairn` an operator in the shared group is meant to edit
#: (the descriptor; `builder.toml`, written by the operator, not cairn). Setgid on the
#: directory only propagates *group ownership* to a new file, never its permission bits —
#: without this, a root-created file inherits root's umask and ends up group-*readable* only,
#: silently defeating the whole point of sharing the directory (`BR-DEPLOY-022`).
SHARED_FILE_MODE = 0o664

#: A **builder** builds images and serves them. It has a manifest, a vendored tree, and a
#: registry. It has no ERPNext site — so nothing to reconnoitre, nothing to back up, and no
#: environment descriptor, which describes a *running* deployment.
BUILD_STAGES = ("preflight", "admin-group", "registry", "timers")

#: A **target** runs ERPNext and converges to whatever its pointer says. It has a site — so it
#: is the only role with an existing stack to survey, a database to back up, and a descriptor.
#: It pulls from the builder's registry and hosts none of its own.
ADOPT_STAGES = ("preflight", "admin-group", "recon", "backup", "descriptor", "timers")


# --- reporting ---------------------------------------------------------------


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
    a build-only stage never reads `project`, an adopt-only one never reads `private_ip`.
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

    def __post_init__(self) -> None:
        if self.manifest is None:
            self.manifest = self.workdir / "cairn.toml"


@dataclass
class Runner:
    """Executes or narrates, depending on ``--dry-run``.

    Every mutation in this file goes through here, which is what makes the dry run truthful
    rather than approximate — there is no second path that could quietly do something.
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


# --- stages shared by both roles ---------------------------------------------


def _base_preflight_checks(runner: Runner, options: SetupOptions) -> tuple[list[Check], Check]:
    disk_check = _check_disk(_docker_data_dir(runner))
    checks = [
        _check_root(),
        _check_command(runner, "docker", ["docker", "--version"]),
        _check_command(runner, "docker compose", ["docker", "compose", "version"]),
        disk_check,
        _check_memory(),
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


def _fail_on_checks(checks: list[Check], disk_check: Check, options: SetupOptions) -> None:
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


def stage_preflight_build(runner: Runner, options: SetupOptions) -> None:
    """Gate a build machine: base checks, plus buildx/git/openssl (rule 5).

    All results before the first failure is deliberate. An installer that dies on the first
    problem makes the operator discover prerequisites one reboot at a time.
    """
    checks, disk_check = _base_preflight_checks(runner, options)
    extra = [
        _check_command(runner, "docker buildx", ["docker", "buildx", "version"]),
        _check_command(runner, "git", ["git", "--version"]),
        _check_command(runner, "openssl", ["openssl", "version"]),
    ]
    for check in extra:
        runner.say(check.render())
    _fail_on_checks(checks + extra, disk_check, options)


def stage_preflight_adopt(runner: Runner, options: SetupOptions) -> None:
    """Gate a target machine: the base checks only — no build tooling to demand of it."""
    checks, disk_check = _base_preflight_checks(runner, options)
    _fail_on_checks(checks, disk_check, options)


def _check_root() -> Check:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return Check("root", True, "running as root")
    return Check("root", False, "must be run with sudo — it writes to /etc and systemd")


def _check_command(runner: Runner, label: str, command: list[str]) -> Check:
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


def _check_disk(path: Path = Path("/")) -> Check:
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


def _check_memory() -> Check:
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


def stage_admin_group(runner: Runner, options: SetupOptions) -> None:
    """Share `/etc/cairn` with a group, so every operator can edit `builder.toml` without
    root (`ADR-043`).

    `/etc/cairn` holds `builder.toml` (`ADR-041`, `ADR-042`) and, on a target, the
    environment descriptor — both machine-scoped facts a multi-operator VPS needs every
    login to see identically (`ADR-042` rejected per-user home-directory config for
    exactly this reason). Left root-only, every edit needs sudo; this stage makes that
    optional rather than mandatory, without prescribing who ends up in the group.

    Runs before `registry`/`descriptor` so the setgid bit is already set when those
    stages create their own files underneath — a file written by root after this point
    still lands in the shared group, not root's own.

    ``--no-admin-group`` skips this entirely: the directory is left however it already
    is, and every subsequent stage still works root-only, exactly as before this existed.
    """
    name = options.admin_group
    if not name:
        runner.report.skipped.append("admin group (skipped: --no-admin-group)")
        return

    gid = _group_gid(name)
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
    gid = _group_gid(name)  # re-read: may have just been created above
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


def _group_gid(name: str) -> int | None:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        return None


# --- build-only stages ---------------------------------------------------------


def stage_registry(runner: Runner, options: SetupOptions) -> None:
    """Run a local registry over self-signed TLS, trusted by both Python and Docker.

    TLS rather than plain HTTP so that **cairn needs no change**: its registry client speaks
    https, and both `urllib` and Docker read the system CA store. The private IP goes into the
    certificate now so the same registry keeps working when the builder and the target become
    two machines.
    """
    host = f"localhost:{REGISTRY_PORT}"
    crt, key = CERT_DIR / "registry.crt", CERT_DIR / "registry.key"

    cert_renewed = not crt.exists() or options.force
    if cert_renewed:
        CERT_DIR.mkdir(parents=True, exist_ok=True)
        runner.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", str(CERT_DAYS),
                "-keyout", str(key), "-out", str(crt),
                "-subj", "/CN=cairn-registry",
                "-addext", f"subjectAltName={subject_alt_names(options.private_ip)}",
            ],
            what="generating the registry certificate",
        )
        if not runner.dry_run:
            os.chmod(key, 0o600)  # rule 4: key material is owner-only
        runner.report.done.append(f"generated {crt}")
    else:
        runner.say(f"    {crt} already exists — reusing it")
        runner.report.skipped.append("registry certificate (already present)")

    # Trusted twice, because two consumers read two stores: Python via the system bundle,
    # Docker via its own per-registry directory.
    ca_copy = SYSTEM_CA_DIR / "cairn-registry.crt"
    docker_ca = DOCKER_CERT_DIR / host / "ca.crt"
    if not runner.dry_run and crt.exists():
        content = crt.read_text(encoding="utf-8")
        runner.write(ca_copy, content, what=f"trusted the certificate system-wide ({ca_copy})")
        runner.write(docker_ca, content, what=f"trusted the certificate for Docker ({docker_ca})")
    else:
        runner.say(f"    write {ca_copy} and {docker_ca} from {crt}")
    runner.run(["update-ca-certificates"], what="refreshing the system CA bundle")

    runner.write(
        REGISTRY_DIR / "compose.yaml",
        registry_compose(),
        what=f"wrote the registry compose file to {REGISTRY_DIR}",
    )
    up_command = ["docker", "compose", "--project-directory", str(REGISTRY_DIR), "up", "-d"]
    if cert_renewed:
        # An already-running container has the old cert loaded in memory; `up -d` alone
        # would leave it serving a certificate nothing trusts anymore, since the bind-mounted
        # file changing underneath it is invisible to compose's own change detection.
        up_command.append("--force-recreate")
    runner.run(up_command, what="starting the registry")

    if not runner.dry_run:
        probe = runner.probe(["curl", "-fsS", f"https://{host}/v2/"])
        if probe is None:
            raise Aborted(
                f"the registry at https://{host}/v2/ did not answer over TLS. If curl reports a "
                f"certificate problem, the CA was not trusted; check {docker_ca}."
            )
        runner.report.done.append(
            f"registry reachable at https://{host} with a trusted certificate"
        )


def subject_alt_names(private_ip: str | None) -> str:
    """Assemble the certificate's SANs.

    ``localhost`` and ``127.0.0.1`` cover today, when the builder and the target are one box.
    The private IP is included so the certificate survives them splitting — reissuing later
    would mean re-trusting it on every host that already had it.
    """
    names = ["DNS:localhost", "DNS:cairn-registry", "IP:127.0.0.1"]
    if private_ip:
        names.append(f"IP:{private_ip}")
    return ",".join(names)


def registry_compose() -> str:
    """The registry, bound to localhost and able to delete versions.

    ``REGISTRY_STORAGE_DELETE_ENABLED`` is what makes keep-N retention possible later — the
    reason hosted registries make retention awkward is that some of them cannot delete a single
    version at all.

    Carries ``CAIRN_MANAGED_LABEL`` so ``cairn-adopt examine`` can recognize this project as
    cairn's own infrastructure and exclude it when auto-detecting a site — by label, never by
    the ``cairn-registry`` project name, which is only ``REGISTRY_DIR``'s basename and asserts
    nothing on its own.
    """
    return f"""\
# Written by `cairn-build setup`. A local OCI registry over self-signed TLS.
services:
  registry:
    image: docker.io/library/registry:2
    restart: unless-stopped
    labels:
      - "{adopt_module.CAIRN_MANAGED_LABEL}=true"
    ports:
      - "127.0.0.1:{REGISTRY_PORT}:{REGISTRY_PORT}"
    environment:
      REGISTRY_HTTP_TLS_CERTIFICATE: /certs/registry.crt
      REGISTRY_HTTP_TLS_KEY: /certs/registry.key
      REGISTRY_STORAGE_DELETE_ENABLED: "true"
    volumes:
      - {CERT_DIR}:/certs:ro
      - registry-data:/var/lib/registry
volumes:
  registry-data:
"""


def stage_timers_build(runner: Runner, options: SetupOptions) -> None:
    """Install the build timer, enabling but not starting it.

    Not started deliberately: the first build should be watched. A timer that fires before
    anyone has confirmed the manifest turns one wrong configuration into a wrong deploy every
    quarter of an hour.
    """
    cairn_build = _executable("cairn-build")
    script = options.workdir / "build-and-advance.sh"
    runner.write(
        script, build_script(options, cairn_build), mode=0o755, what=f"build script at {script}"
    )
    runner.write(
        SYSTEMD_DIR / "cairn-build.service", build_service(options, script), what="build service"
    )
    runner.write(SYSTEMD_DIR / "cairn-build.timer", build_timer(options), what="build timer")

    runner.run(["systemctl", "daemon-reload"], what="reloading systemd")
    runner.run(["systemctl", "enable", "cairn-build.timer"], what="enabling cairn-build.timer")
    runner.report.warnings.append(
        "cairn-build.timer is enabled but NOT started — run the first build by hand first, "
        "then `systemctl start cairn-build.timer`"
    )


def build_script(options: SetupOptions, cairn_build: Path) -> str:
    """Build, then advance the environment pointer.

    `cairn-build build --push` is already an idempotent change detector — it resolves refs,
    computes the input hash, and short-circuits when that hash is already built. So a timer is
    the whole of the trigger; no watcher is needed and a no-op poll costs three `git ls-remote`
    calls.
    """
    return f"""\
#!/bin/bash -e
# Written by `cairn-build setup`. `cairn-build build --push` is idempotent: with no new
# commits it resolves refs, sees the input hash is already built, and exits without building.
cd {options.workdir}
MANIFEST={shlex.quote(str(options.manifest))}
{cairn_build} build --manifest "$MANIFEST" --push
{cairn_build} retag {shlex.quote(options.environment)} --latest --yes --manifest "$MANIFEST"
"""


def build_service(options: SetupOptions, script: Path) -> str:
    """The build unit.

    The script itself always passes `--manifest` explicitly (`ADR-042` — cairn never
    searches for one); ``WorkingDirectory`` is set so relative paths inside the script,
    and the deployment directory the operator finds if they inspect the unit, still land
    in the right place.
    """
    return f"""\
[Unit]
Description=cairn-build — build a new image if the manifest's refs have moved
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory={options.workdir}
ExecStart={script}
# A build that cannot finish in 90 minutes is stuck, not slow.
TimeoutStartSec=5400

[Install]
WantedBy=multi-user.target
"""


def build_timer(options: SetupOptions) -> str:
    """The build timer.

    Measured from the end of the last run, and deliberately slower than reconcile's: builds take
    tens of minutes. systemd will not start a unit that is already active, which supplies the
    single-flight that `cairn-build build` does not have of its own.
    """
    return f"""\
[Unit]
Description=cairn-build — poll for new commits and build

[Timer]
OnBootSec=5min
OnUnitInactiveSec={options.build_interval}
RandomizedDelaySec=60
Persistent=true
Unit=cairn-build.service

[Install]
WantedBy=timers.target
"""


# --- adopt-only stages ---------------------------------------------------------


def stage_recon(runner: Runner, options: SetupOptions) -> None:
    """Read the existing stack, and record how to put it back (read-only).

    The revert note is the point. `reconcile` never rolls back (`BR-DEPLOY-018`), so the values
    it would replace have to be captured *before* anything changes.
    """
    listing = runner.probe(["docker", "compose", "ls", "--format", "json"])
    if listing is None:
        runner.say("    no compose project is running, or Docker did not answer")
        runner.report.warnings.append("no existing stack was found to reconnoitre")
        return

    try:
        projects = [p for p in json.loads(listing) if isinstance(p, dict)]
    except json.JSONDecodeError:
        runner.report.warnings.append("compose's project list was not JSON")
        return

    if not projects:
        runner.say("    no compose project is running")
        return

    for project in projects:
        runner.say(f"    project {project.get('Name')} — {project.get('Status', '?')}")
        first = str(project.get("ConfigFiles", "")).split(",")[0].strip()
        if not first:
            continue
        env_file = Path(first).parent / ".env"
        current = read_env_values(env_file, ("CUSTOM_IMAGE", "CUSTOM_TAG", "SITES"))
        for key, value in current.items():
            runner.say(f"      {key}={value}")
        if current:
            runner.report.revert.append(
                f"In {env_file}, restore: "
                + ", ".join(f"{k}={v}" for k, v in current.items())
                + f" then: docker compose --project-name {project.get('Name')} up -d"
            )


def read_env_values(env_file: Path, keys: tuple[str, ...]) -> dict[str, str]:
    """Read selected ``KEY=value`` pairs from a compose ``.env``, ignoring the rest."""
    values: dict[str, str] = {}
    try:
        lines = env_file.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() in keys:
            values[key.strip()] = value.strip()
    return values


def stage_backup(runner: Runner, options: SetupOptions) -> None:
    """Back up every site, and verify the dump exists and is non-empty (rule 6).

    The installer's job rather than cairn's: a backup writes into the sites volume, which
    `ADR-022` forbids cairn from doing. Verified rather than assumed, because the whole reason
    this stage exists is that `bench migrate` is irreversible.
    """
    if options.skip_backup:
        runner.say("    skipped by --skip-backup")
        runner.report.skipped.append("pre-install backup (explicitly skipped)")
        runner.report.warnings.append(
            "no backup was taken; bench migrate is irreversible and cairn never rolls back"
        )
        return

    project = options.project or _only_project(runner)
    if project is None:
        runner.say("    no single compose project to back up; name one with --project")
        runner.report.skipped.append("pre-install backup (no project identified)")
        return

    compose = ["docker", "compose", "--project-name", project]
    runner.run(
        [*compose, "exec", "-T", "backend", "bench", "--site", "all", "backup", "--with-files"],
        what="backing up the site(s)",
        timeout=3600,
    )

    inspect = "ls -l sites/*/private/backups | tail -20"
    listing = runner.probe([*compose, "exec", "-T", "backend", "bash", "-lc", inspect])
    if runner.dry_run:
        return
    if not listing or not listing.strip():
        raise Aborted(
            "the backup reported success but no dump could be found under "
            "sites/*/private/backups. Not proceeding — verify by hand."
        )
    runner.say("    backups present:")
    for line in listing.strip().splitlines()[-6:]:
        runner.say(f"      {line}")
    runner.report.done.append("verified pre-install backup")
    runner.report.warnings.append(
        "the backup is on the box; copy it off before relying on it"
    )


def _only_project(runner: Runner) -> str | None:
    listing = runner.probe(["docker", "compose", "ls", "--format", "json"])
    if listing is None:
        return None
    try:
        projects = [p for p in json.loads(listing) if isinstance(p, dict) and p.get("Name")]
    except json.JSONDecodeError:
        return None
    return str(projects[0]["Name"]) if len(projects) == 1 else None


def stage_descriptor(runner: Runner, options: SetupOptions) -> None:
    """Generate the descriptor with :mod:`cairn.adopt`, install it, and confirm it parses.

    Calls straight into `adopt.survey`/`adopt.render` in-process — `setup` and `examine` are
    two subcommands of the same binary now, so there is no sibling process to shell out to
    (`ADR-046`).
    """
    found = adopt_module.survey(options.project)
    if found.is_multi_site:
        raise Aborted(
            f"this host serves {len(found.sites)} sites and a descriptor names one. Run "
            f"`cairn-adopt examine` for the full findings before deciding how to proceed."
        )

    try:
        rendered = adopt_module.render(found, options.environment)
        adopt_module.validate(rendered)
    except ValueError as exc:
        raise Aborted(
            f"not enough could be determined to describe this host: {exc}. Run "
            f"`cairn-adopt examine` to see what is missing."
        ) from exc

    runner.write(
        DESCRIPTOR_PATH, rendered, mode=SHARED_FILE_MODE, what=f"installed {DESCRIPTOR_PATH}"
    )
    if runner.dry_run:
        return

    try:
        parsed = tomllib.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Aborted(f"{DESCRIPTOR_PATH} does not parse after writing — {exc}") from exc
    runner.say(f"    describes environment '{parsed.get('environment')}' on site "
               f"'{parsed.get('site')}'")


def stage_timers_adopt(runner: Runner, options: SetupOptions) -> None:
    """Install the reconcile timer, enabling but not starting it.

    Not started deliberately: the first reconcile should be watched. Rendered in-process via
    :func:`cairn.systemd.units` — no subprocess, no output to parse (`ADR-046`).
    """
    cairn_adopt = _executable("cairn-adopt")
    rendered = systemd.units(executable=str(cairn_adopt), interval=options.interval)

    runner.write(
        SYSTEMD_DIR / "cairn-reconcile.service", rendered.service, what="reconcile service"
    )
    runner.write(SYSTEMD_DIR / "cairn-reconcile.timer", rendered.timer, what="reconcile timer")

    runner.run(["systemctl", "daemon-reload"], what="reloading systemd")
    runner.run(
        ["systemctl", "enable", "cairn-reconcile.timer"], what="enabling cairn-reconcile.timer"
    )
    runner.report.warnings.append(
        "cairn-reconcile.timer is enabled but NOT started — run `cairn-adopt reconcile` by hand "
        "first, then `systemctl start cairn-reconcile.timer`"
    )


def _executable(name: str) -> Path:
    """Locate *name* (``cairn-build`` or ``cairn-adopt``) installed alongside this one.

    Both are always installed together, by the same distribution (`pip install` / `pipx
    install --global datahenge-cairn`) — so the reliable way to find one from the other is
    as a sibling in the same ``bin/`` directory, not a `PATH` lookup, which depends on how
    the operator happened to invoke `sudo`.
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


# --- entry points -------------------------------------------------------------

BUILD_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "preflight": stage_preflight_build,
    "admin-group": stage_admin_group,
    "registry": stage_registry,
    "timers": stage_timers_build,
}

ADOPT_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "preflight": stage_preflight_adopt,
    "admin-group": stage_admin_group,
    "recon": stage_recon,
    "backup": stage_backup,
    "descriptor": stage_descriptor,
    "timers": stage_timers_adopt,
}


def stages_for(available: tuple[str, ...], stage_funcs: dict, only: str | None) -> tuple[str, ...]:
    """Which stages this run performs, in order.

    *stage_funcs* is one CLI's own fixed stage table (`BUILD_STAGE_FUNCS` or
    `ADOPT_STAGE_FUNCS`) — a stage belonging to the other CLI is simply not a key in it,
    so it is reported the same way a typo would be, not as a separate "wrong role" case.
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

    Shared by `cairn-build setup` and `cairn-adopt setup` — only *stage_funcs* and
    *available_stages* differ between them.
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
        runner.say("  nothing to report")
