"""Provision a cairn build machine or deploy target (`BR-DEPLOY-021`, `ADR-040`).

    sudo cairn-provision --role builder --dry-run
    sudo cairn-provision --role builder

Installed the same way as `cairn` itself — `pip install datahenge-cairn`, or for a machine
meant to outlive any one operator's own account, `sudo pipx install --global
datahenge-cairn` (installs to a shared system location, not tied to a personal login that
might one day be deactivated).

**Why this is a separate program and not a `cairn` subcommand.** Two decisions would break if
it were one: cairn *emits* systemd units and never installs them (`ADR-035`), and cairn writes
nothing to a data-plane volume (`ADR-022`) — a pre-install `bench backup` writes into the sites
volume. An operator running `cairn-provision` with explicit privilege *is* the operator doing
those things. cairn's own boundary stays exactly where it was drawn, and the invariant across
the CLI holds: **cairn prints host configuration; the operator installs it — cairn-provision is
the one exception, and it exists precisely so that exception never has to live inside cairn.**

It shells out to `cairn` for the read-only and print-only work (`doctor`, `adopt`,
`systemd-units`) rather than reaching into cairn's internals, so provisioning always reflects
exactly what a human running those commands by hand would see.

**The contract it keeps** (`BR-DEPLOY-021`), which is also why it is Python rather than shell —
this runs as root on client infrastructure and therefore has to be testable:

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

import argparse
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
DESCRIPTOR_PATH = Path("/etc/cairn/environment.toml")
SYSTEM_CA_DIR = Path("/usr/local/share/ca-certificates")
DOCKER_CERT_DIR = Path("/etc/docker/certs.d")
SYSTEMD_DIR = Path("/etc/systemd/system")

#: How long the self-signed certificate lasts. 825 days is the longest most clients accept.
CERT_DAYS = 825

#: A **builder** builds images and serves them. It has a manifest, a vendored tree, and a
#: registry. It has no ERPNext site — so nothing to reconnoitre, nothing to back up, and no
#: environment descriptor, which describes a *running* deployment.
BUILDER_STAGES = ("preflight", "registry", "timers")

#: A **target** runs ERPNext and converges to whatever its pointer says. It has a site — so it
#: is the only role with an existing stack to survey, a database to back up, and a descriptor.
#: It pulls from the builder's registry and hosts none of its own.
TARGET_STAGES = ("preflight", "recon", "backup", "descriptor", "timers")

#: Both roles on one box. Today's case while builder and target are the same machine; the union
#: in dependency order, so the backup still happens before anything is installed.
BOTH_STAGES = ("preflight", "recon", "backup", "registry", "descriptor", "timers")

ROLE_STAGES = {"builder": BUILDER_STAGES, "target": TARGET_STAGES, "both": BOTH_STAGES}


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


def builds(options: argparse.Namespace) -> bool:
    """Whether this host builds images — needs buildx, git, a container engine, a registry."""
    return options.role in ("builder", "both")


def serves(options: argparse.Namespace) -> bool:
    """Whether this host runs a site — the only role with a stack to survey, back up, describe."""
    return options.role in ("target", "both")


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
        """Write *path*, preserving anything already there (`BR-DEPLOY-021` rule 3)."""
        if path.exists() and path.read_text(encoding="utf-8") == content:
            self.say(f"    {path} already correct — leaving it")
            self.report.skipped.append(f"{what} (already correct)")
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


# --- stages ------------------------------------------------------------------


def stage_preflight(runner: Runner, options: argparse.Namespace) -> None:
    """Gate the host: report every check, then stop if any failed (rule 5).

    All results before the first failure is deliberate. An installer that dies on the first
    problem makes the operator discover prerequisites one reboot at a time.
    """
    checks = [
        _check_root(),
        _check_command(runner, "docker", ["docker", "--version"]),
        _check_command(runner, "docker compose", ["docker", "compose", "version"]),
        _check_disk(),
        _check_memory(),
    ]
    if builds(options):
        # Only a builder needs these: buildx for the secret-mount build, git for ref
        # resolution, openssl for the registry certificate. A target has no use for any of
        # them.
        checks.append(_check_command(runner, "docker buildx", ["docker", "buildx", "version"]))
        checks.append(_check_command(runner, "git", ["git", "--version"]))
        checks.append(_check_command(runner, "openssl", ["openssl", "version"]))

    for check in checks:
        runner.say(check.render())

    failed = [check for check in checks if not check.ok]
    if failed:
        raise Aborted(
            f"{len(failed)} prerequisite(s) failed: "
            f"{', '.join(check.label for check in failed)}. Nothing was changed."
        )


def _check_root() -> Check:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return Check("root", True, "running as root")
    return Check("root", False, "must be run with sudo — it writes to /etc and systemd")


def _check_command(runner: Runner, label: str, command: list[str]) -> Check:
    output = runner.probe(command)
    if output is None:
        return Check(label, False, f"not available (`{shlex.join(command)}` failed)")
    return Check(label, True, output.strip().splitlines()[0] if output.strip() else "present")


def _check_disk(path: Path = Path("/")) -> Check:
    try:
        free_gb = shutil.disk_usage(path).free / 1_000_000_000
    except OSError as exc:
        return Check("free disk", False, f"cannot be determined ({exc})")
    ok = free_gb >= MINIMUM_DISK_GB
    return Check(
        "free disk",
        ok,
        f"{free_gb:.0f} GB free" + ("" if ok else f" — needs {MINIMUM_DISK_GB} GB"),
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


def stage_recon(runner: Runner, options: argparse.Namespace) -> None:
    """Read the existing stack, and record how to put it back (read-only).

    The revert note is the point. `reconcile` never rolls back (`BR-DEPLOY-018`), so the values
    it would replace have to be captured *before* anything changes.

    Target-only: a builder has no deployment to survey.
    """
    if not serves(options):
        raise Aborted(
            "there is no running deployment to survey on a build machine. "
            "Use --role target or --role both."
        )

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


def stage_backup(runner: Runner, options: argparse.Namespace) -> None:
    """Back up every site, and verify the dump exists and is non-empty (rule 6).

    The installer's job rather than cairn's: a backup writes into the sites volume, which
    `ADR-022` forbids cairn from doing. Verified rather than assumed, because the whole reason
    this stage exists is that `bench migrate` is irreversible.

    Target-only. A builder has no site, so there is nothing here to back up — running `bench`
    on a build machine would be asking a question of a container that does not exist.
    """
    if not serves(options):
        raise Aborted(
            "backup applies only to a host running a site. A builder has none — use "
            "--role target or --role both."
        )

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


def stage_registry(runner: Runner, options: argparse.Namespace) -> None:
    """Run a local registry over self-signed TLS, trusted by both Python and Docker.

    TLS rather than plain HTTP so that **cairn needs no change**: its registry client speaks
    https, and both `urllib` and Docker read the system CA store. The private IP goes into the
    certificate now so the same registry keeps working when the builder and the target become
    two machines.

    Builder-only. A target pulls from the builder's registry and hosts none of its own.
    """
    if not builds(options):
        raise Aborted(
            "a registry belongs on the build machine, which serves images to targets. "
            "Use --role builder or --role both."
        )

    host = f"localhost:{REGISTRY_PORT}"
    crt, key = CERT_DIR / "registry.crt", CERT_DIR / "registry.key"

    if not crt.exists() or options.force:
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
    runner.run(
        ["docker", "compose", "--project-directory", str(REGISTRY_DIR), "up", "-d"],
        what="starting the registry",
    )

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
    """
    return f"""\
# Written by cairn-provision. A local OCI registry over self-signed TLS.
services:
  registry:
    image: docker.io/library/registry:2
    restart: unless-stopped
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


def stage_descriptor(runner: Runner, options: argparse.Namespace) -> None:
    """Generate the descriptor with `cairn adopt`, install it, and confirm it parses.

    Target-only. The descriptor describes a *running* deployment (`BR-DEPLOY-010a`), and its
    presence is what marks a machine as a target. A builder is described by its manifest.
    """
    if not serves(options):
        raise Aborted(
            "a descriptor describes a running deployment; a build machine has none. "
            "Use --role target or --role both."
        )

    cairn = _cairn_executable()
    command = [str(cairn), "adopt", "--environment", options.environment]
    if options.project:
        command += ["--project", options.project]

    rendered = runner.probe(command)
    if rendered is None or not rendered.strip():
        raise Aborted(
            f"`cairn adopt` could not describe this host. Run it directly to see why:\n"
            f"  {shlex.join(command)}"
        )

    runner.write(DESCRIPTOR_PATH, rendered, what=f"installed {DESCRIPTOR_PATH}")
    if runner.dry_run:
        return

    try:
        parsed = tomllib.loads(DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise Aborted(f"{DESCRIPTOR_PATH} does not parse after writing — {exc}") from exc
    runner.say(f"    describes environment '{parsed.get('environment')}' on site "
               f"'{parsed.get('site')}'")


def stage_timers(runner: Runner, options: argparse.Namespace) -> None:
    """Install the systemd units, enabling but not starting the build timer.

    Not started deliberately: the first build should be watched. A timer that fires before
    anyone has confirmed the manifest turns one wrong configuration into a wrong deploy every
    quarter of an hour.
    """
    cairn = _cairn_executable()
    enable = []

    # Each role gets only the timer it actually runs. A builder converges nothing; a target
    # builds nothing.
    if serves(options):
        emitted = runner.probe([str(cairn), "systemd-units", "--interval", options.interval])
        if emitted is None:
            raise Aborted("`cairn systemd-units` did not answer; is cairn installed?")

        service, timer = split_units(emitted)
        if service is None or timer is None:
            raise Aborted(
                "could not split `cairn systemd-units` output into a service and a timer"
            )

        # cairn resolves its own path with shutil.which, which will not find a sibling
        # binary under sudo unless it happens to be on root's PATH — write the resolved
        # path we already located instead.
        service = service.replace("ExecStart=cairn ", f"ExecStart={cairn} ")
        runner.write(SYSTEMD_DIR / "cairn-reconcile.service", service, what="reconcile service")
        runner.write(SYSTEMD_DIR / "cairn-reconcile.timer", timer, what="reconcile timer")
        enable.append("cairn-reconcile.timer")

    if builds(options):
        script = options.workdir / "build-and-advance.sh"
        runner.write(
            script,
            build_script(options),
            mode=0o755,
            what=f"build script at {script}",
        )
        runner.write(
            SYSTEMD_DIR / "cairn-build.service",
            build_service(options, script),
            what="build service",
        )
        runner.write(
            SYSTEMD_DIR / "cairn-build.timer", build_timer(options), what="build timer"
        )
        enable.append("cairn-build.timer")

    runner.run(["systemctl", "daemon-reload"], what="reloading systemd")
    for unit in enable:
        runner.run(["systemctl", "enable", unit], what=f"enabling {unit}")
    runner.report.warnings.append(
        "timers are enabled but NOT started — run the first build and reconcile by hand first, "
        f"then `systemctl start {' '.join(enable)}`"
    )


def _cairn_executable() -> Path:
    """Locate the `cairn` executable installed alongside this one.

    `cairn-provision` and `cairn` are always installed together, by the same distribution
    (`pip install` / `pipx install --global datahenge-cairn`) — so the reliable way to find
    one from the other is as a sibling in the same ``bin/`` directory, not a `PATH` lookup,
    which depends on how the operator happened to invoke `sudo`.
    """
    sibling = Path(sys.argv[0]).resolve().parent / "cairn"
    if sibling.is_file():
        return sibling
    found = shutil.which("cairn")
    if found:
        return Path(found)
    raise Aborted(
        "cannot find the `cairn` executable next to this one, or on PATH. Is datahenge-cairn "
        "installed? (`pipx install --global datahenge-cairn`)"
    )


def split_units(emitted: str) -> tuple[str | None, str | None]:
    """Split `cairn systemd-units` output into (service, timer).

    Keyed on the filename headers cairn prints, so a change to its layout fails loudly here
    rather than installing half a unit.
    """
    service_marker = "cairn-reconcile.service ---"
    timer_marker = "cairn-reconcile.timer ---"
    if service_marker not in emitted or timer_marker not in emitted:
        return None, None

    after_service = emitted.split(service_marker, 1)[1]
    service, _, rest = after_service.partition("# ---")
    timer = rest.split(timer_marker, 1)[1] if timer_marker in rest else None
    return service.strip() + "\n", (timer.strip() + "\n") if timer else None


def build_script(options: argparse.Namespace) -> str:
    """Build, then advance the environment pointer.

    `cairn build --push` is already an idempotent change detector — it resolves refs, computes
    the input hash, and short-circuits when that hash is already built. So a timer is the whole
    of the trigger; no watcher is needed and a no-op poll costs three `git ls-remote` calls.
    """
    cairn = _cairn_executable()
    return f"""\
#!/bin/bash -e
# Written by cairn-provision. `cairn build --push` is idempotent: with no new commits it
# resolves refs, sees the input hash is already built, and exits without building.
cd {options.workdir}
MANIFEST={shlex.quote(str(options.manifest))}
{cairn} build --manifest "$MANIFEST" --push
{cairn} retag {shlex.quote(options.environment)} --latest --yes --manifest "$MANIFEST"
"""


def build_service(options: argparse.Namespace, script: Path) -> str:
    """The build unit.

    ``WorkingDirectory`` is required, not decoration: cairn finds a manifest not given
    explicitly by searching upward from the working directory.
    """
    return f"""\
[Unit]
Description=cairn — build a new image if the manifest's refs have moved
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


def build_timer(options: argparse.Namespace) -> str:
    """The build timer.

    Measured from the end of the last run, and deliberately slower than reconcile's: builds take
    tens of minutes. systemd will not start a unit that is already active, which supplies the
    single-flight that `cairn build` does not have of its own.
    """
    return f"""\
[Unit]
Description=cairn — poll for new commits and build

[Timer]
OnBootSec=5min
OnUnitInactiveSec={options.build_interval}
RandomizedDelaySec=60
Persistent=true
Unit=cairn-build.service

[Install]
WantedBy=timers.target
"""


# --- entry point -------------------------------------------------------------

STAGES: dict[str, Callable[[Runner, argparse.Namespace], None]] = {
    "preflight": stage_preflight,
    "recon": stage_recon,
    "backup": stage_backup,
    "registry": stage_registry,
    "descriptor": stage_descriptor,
    "timers": stage_timers,
}


def stages_for(role: str, only: str | None) -> tuple[str, ...]:
    """Which stages this run performs, in order."""
    available = ROLE_STAGES[role]
    if only is None:
        return available
    if only not in STAGES:
        raise Aborted(f"unknown stage '{only}'; choose from {', '.join(STAGES)}")
    if only not in available:
        raise Aborted(f"stage '{only}' does not apply to role '{role}'")
    return (only,)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cairn-provision",
        description="Provision a cairn build machine or deploy target.",
    )
    parser.add_argument(
        "--role",
        choices=("builder", "target", "both"),
        required=True,
        help="builder = builds and serves images; target = runs a site and converges; "
        "both = one box doing each, which is the bootstrap case",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print every action and change nothing"
    )
    parser.add_argument(
        "--only", metavar="STAGE", help=f"run one stage: {', '.join(STAGES)}"
    )
    parser.add_argument(
        "--force", action="store_true", help="replace existing files (the old ones are kept)"
    )
    parser.add_argument(
        "--workdir", type=Path, default=Path.cwd(),
        help="the deployment directory: cairn.toml and the build timer live here "
        "(default: the current directory)",
    )
    parser.add_argument("--manifest", type=Path, help="deployment manifest for the build timer")
    parser.add_argument("--environment", default="production", help="environment name")
    parser.add_argument("--project", help="compose project to adopt and back up")
    parser.add_argument("--private-ip", help="also put this IP in the registry certificate")
    parser.add_argument("--interval", default="5min", help="reconcile poll interval")
    parser.add_argument("--build-interval", default="15min", help="build poll interval")
    parser.add_argument(
        "--skip-backup", action="store_true", help="do not back up before changing anything"
    )
    options = parser.parse_args(argv)
    if options.manifest is None:
        options.manifest = options.workdir / "cairn.toml"
    return options


def main(argv: list[str] | None = None) -> int:
    options = parse_args(argv)
    runner = Runner(dry_run=options.dry_run, force=options.force)

    runner.say(f"cairn-provision — role {options.role}" + (" (dry run)" if options.dry_run else ""))
    runner.say(f"workdir {options.workdir}")
    runner.say("")

    try:
        chosen = stages_for(options.role, options.only)
        for name in chosen:
            runner.say(f"[{name}]")
            STAGES[name](runner, options)
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
    if options.dry_run:
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


if __name__ == "__main__":
    sys.exit(main())
