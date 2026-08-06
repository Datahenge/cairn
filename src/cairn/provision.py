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
partial run without it — the invariant across every CLI holds: **cairn prints host
configuration; the operator installs it — `setup` is the one exception, and it exists
precisely so that exception never leaks into an ordinary command.**

There is no `--role` flag (`ADR-046`, retiring the separate `cairn-provision` program):
`cairn-build setup` runs only the builder stages, `cairn-adopt setup` only the target
stages — the binary invoked already says which. `cairn-adopt setup`'s descriptor stage
calls straight into :mod:`cairn.adopt` and its timer stage into :mod:`cairn.systemd`, both
in-process — there is no sibling binary left to shell out to.

**The local registry is provisioned by a third binary, not here** (`ADR-048`): what used to
be this module's `"registry"` stage is now `cairn-registry setup`
(`registry_provision.py`) — a registry host is provisioned independently of a build
machine, and the split gave it its own config, retention policy, and timer.

**Build/reconcile automation is a separate command** (`cairn-build setup-timer`,
`cairn-adopt setup-timer`, `BR-CLI-023`, `ADR-047`), not a stage of `setup` — the timer it
installs stays enabled-but-not-started either way, specifically so a first build or
reconcile gets run and watched by hand first; splitting it out just makes that a command a
first-time reader finds in `--help` on its own.

**`cairn-build setup` also provisions the manifest's home** (`BR-CLI-022`, `ADR-047`):
`--client <name>` (required) creates `/srv/cairn/<name>/` — cairn's own namespace within
`/srv`, never assuming anything about sibling paths there — and scaffolds a starter
`cairn.toml` only if that directory has none yet. An existing one is never touched.

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

import json
import os
import shlex
import tomllib
from collections.abc import Callable
from pathlib import Path

from . import adopt as adopt_module
from . import engine, setup_runner, systemd
from .errors import BuildEngineError
from .setup_runner import (
    SHARED_CONFIG_MODE,
    SYSTEMD_DIR,
    Aborted,
    Check,
    Report,
    Runner,
    SetupOptions,
    base_preflight_checks,
    check_command,
    execute,
    fail_on_checks,
    find_executable,
    group_gid,
    require_root,
    stage_admin_group,
    stages_for,
)

__all__ = [
    "Aborted",
    "Check",
    "Report",
    "Runner",
    "SetupOptions",
    "execute",
    "stages_for",
]

# --- host requirements -------------------------------------------------------

DESCRIPTOR_PATH = Path("/etc/cairn/adopt.toml")

#: cairn's own namespace within `/srv` (`BR-CLI-022`, `ADR-047`). A host's `/srv` may
#: already hold unrelated application data cairn has no business assuming anything about
#: — everything under `MANIFEST_ROOT` is cairn's; nothing beside it is cairn's concern.
MANIFEST_ROOT = Path("/srv/cairn")


def manifest_template(environment: str) -> str:
    """The starter manifest `setup` scaffolds into a client directory, for *environment*
    (`BR-CLI-022`, `ADR-047`, `ADR-052`) — the same illustrative example published in
    `README.md`/`userdocs/reference/manifest.md`, `BR-BUILD-003`'s ordered-list comment
    included, with `[cairn] environment` pre-filled from what the operator just named on the
    command line. One template, reused, not reinvented.
    """
    return f"""\
[cairn]
image_name = "erpnext-v16"
series = "v16"                      # the readable half of the image tag
environment = "{environment}"       # this manifest's declared environment — at most
                                     # one per manifest, and its name is its tag

[cairn.frappe]
url = "https://github.com/frappe/frappe"
ref = "v16.25.0"                    # a tag: reproducible. A branch (e.g. "version-16")
                                     # always builds its latest commit instead — cairn warns
                                     # when one is used, but it stays supported on purpose.

# Order matters: apps install in this order, and cairn never reorders or resolves
# dependencies for you. List every app after the apps it depends on.
[[cairn.apps]]
name = "erpnext"
url = "https://github.com/frappe/erpnext"
ref = "v16.26.1"

# Uncomment and edit to add another app, after the apps it depends on:
# [[cairn.apps]]
# name = "your_custom_app"
# url = "https://github.com/your-org/your_custom_app"
# ref = "v1.2.3"

[cairn.build]
python_version = "3.14.2"
node_version = "24.13.0"
install_chromium = true
"""


#: rw-rw-r--, for a file under `/etc/cairn` an operator in the shared group is meant to edit
#: (the descriptor; `builder.toml`, written by the operator, not cairn). Setgid on the
#: directory only propagates *group ownership* to a new file, never its permission bits —
#: without this, a root-created file inherits root's umask and ends up group-*readable* only,
#: silently defeating the whole point of sharing the directory (`BR-DEPLOY-022`).
SHARED_FILE_MODE = 0o664

#: A **builder** builds images and serves them, publishing to whichever registry its manifest
#: names — it has no ERPNext site, so nothing to reconnoitre, nothing to back up, and no
#: environment descriptor, which describes a *running* deployment. Build automation is a
#: separate command, `setup-timer` (`BR-CLI-023`), not a stage here. Provisioning a *local*
#: registry is `cairn-registry setup`'s job, not this one's (`ADR-048`).
BUILD_STAGES = ("preflight", "admin-group", "manifest")

#: A **target** runs ERPNext and converges to whatever its pointer says. It has a site — so it
#: is the only role with an existing stack to survey, a database to back up, and a descriptor.
#: Reconcile automation is a separate command, `setup-timer` (`BR-CLI-023`), not a stage here.
ADOPT_STAGES = ("preflight", "admin-group", "recon", "backup", "descriptor")

#: Every role's build/reconcile/registry-maintenance automation command runs exactly this one
#: stage (`cairn-build setup-timer`, `cairn-adopt setup-timer`, `cairn-registry setup-timer`;
#: `BR-CLI-023`, `ADR-047`).
TIMER_STAGES = ("timers",)


# --- stages shared by both roles ---------------------------------------------


def _check_build_engine() -> tuple[Check, engine.BuildEngine | None]:
    """Detect the build engine — docker or podman — the same way `cairn-build doctor`/
    `build` already do (`ADR-027`), rather than hard-coding `docker` the way a deploy
    target's preflight does (`base_preflight_checks`, always Docker, `ADR-002`).
    """
    try:
        selected = engine.detect()
    except BuildEngineError as exc:
        return Check("build engine", False, str(exc).strip().splitlines()[0]), None
    return Check("build engine", True, f"{selected.name} v{selected.version}"), selected


def _build_engine_data_dir(runner: Runner, selected: engine.BuildEngine | None) -> Path:
    """Where *selected* actually stores images and volumes — read, not assumed, since a
    separate mount for it is common on a build machine.

    Falls back to `/` when unknown: no engine was selected, or the probe itself failed.
    """
    if selected is not None and selected.name == engine.PODMAN:
        output = runner.probe(["podman", "info", "--format", "{{.Store.GraphRoot}}"])
    else:
        output = runner.probe(["docker", "info", "--format", "{{.DockerRootDir}}"])
    if output is None or not output.strip():
        return Path("/")
    return Path(output.strip())


def stage_preflight_build(runner: Runner, options: SetupOptions) -> None:
    """Gate a build machine: the engine (docker or podman), its disk/memory floors, and git
    (rule 5).

    Does not call `base_preflight_checks` — that fixes the engine to Docker, right for a
    deploy target but wrong here, since a build machine's engine is a genuine choice
    (`ADR-027`). `docker compose` is never checked either: a build never runs it, only
    `cairn-adopt`'s reconcile does. Free disk is read from wherever the *selected* engine
    stores images; buildx is only checked when that engine needs it (docker — podman builds
    with buildah in-process, no such plugin to check for).

    All results before the first failure is deliberate. An installer that dies on the first
    problem makes the operator discover prerequisites one reboot at a time.
    """
    engine_check, selected = _check_build_engine()
    checks = [setup_runner._check_root(), engine_check]
    if selected is not None and selected.needs_buildx:
        checks.append(check_command(runner, "docker buildx", ["docker", "buildx", "version"]))
    disk_check = setup_runner.check_disk(_build_engine_data_dir(runner, selected))
    checks.append(disk_check)
    checks.append(setup_runner.check_memory())
    checks.append(check_command(runner, "git", ["git", "--version"]))

    for check in checks:
        runner.say(check.render())
    if not disk_check.ok and options.skip_disk_free:
        runner.say("    overridden by --skip-disk-free")
        runner.report.warnings.append(
            "free disk was below the minimum but the check was overridden; "
            "a build or migration may run out of room"
        )
    fail_on_checks(checks, disk_check, options)


def stage_preflight_adopt(runner: Runner, options: SetupOptions) -> None:
    """Gate a target machine: the base checks only — no build tooling to demand of it."""
    checks, disk_check = base_preflight_checks(runner, options)
    fail_on_checks(checks, disk_check, options)


# --- build-only stages ---------------------------------------------------------


def stage_manifest(runner: Runner, options: SetupOptions) -> None:
    """Provision `/srv/cairn/<client>/`, scaffolding a starter `cairn_<environment>.toml` if
    none exists yet (`BR-CLI-022`, `ADR-047`, `ADR-052`).

    `MANIFEST_ROOT` is cairn's own namespace within `/srv` — a host's `/srv` may already
    hold unrelated application data cairn has no business assuming anything about, so
    nothing outside this one directory is ever read, listed, or touched.

    An existing manifest is **never** modified, `--force` included: unlike every other file
    `setup` can write, this one is the operator's own deployment source, not cairn's to
    manage — `setup` only ever creates it as a courtesy starting point when this specific
    environment has none yet. A distinctly-named file per call is what lets a client
    directory hold several environments (`BR-DEPLOY-009`'s 1:1 model) instead of one shared
    file being overwritten by the next `--environment`.
    """
    if not options.client:
        raise Aborted("--client <name> is required to provision a manifest directory")
    if not options.environment:
        raise Aborted("--environment <name> is required to scaffold a manifest")

    client_dir = MANIFEST_ROOT / options.client
    group_name = options.admin_group

    if runner.dry_run:
        runner.say(
            f"    ensure {client_dir} exists"
            + (f", shared with group '{group_name}'" if group_name else "")
        )
    else:
        MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
        client_dir.mkdir(parents=True, exist_ok=True)
        if group_name:
            gid = group_gid(group_name)
            if gid is not None:
                for directory in (MANIFEST_ROOT, client_dir):
                    os.chown(directory, -1, gid)
                    os.chmod(directory, SHARED_CONFIG_MODE)
    runner.report.done.append(f"{client_dir} provisioned")

    manifest_path = client_dir / f"cairn_{options.environment}.toml"
    if manifest_path.exists():
        runner.say(f"    {manifest_path} already exists — leaving it")
        runner.report.skipped.append(f"{manifest_path} (already present, not modified)")
        return

    runner.say(f"    write {manifest_path} (starter manifest)")
    if runner.dry_run:
        return
    manifest_path.write_text(manifest_template(options.environment), encoding="utf-8")
    os.chmod(manifest_path, SHARED_FILE_MODE)
    runner.report.done.append(f"scaffolded a starter manifest at {manifest_path}")


def client_from_manifest(manifest_path: Path) -> str:
    """The client segment of *manifest_path*'s canonical home (`ADR-047`, `ADR-062`).

    `ADR-052` settled uniqueness as `(client, image_name, environment)`, not environment
    alone — a build host serving more than one client (`BR-CLI-022`) can otherwise produce
    two unrelated builds that resolve to the same unit name. Client is derived from where the
    manifest actually lives, the same way `doctor`'s duplicate-declaration check already
    groups manifests by client directory, rather than a second `--client` flag that could
    disagree with it.
    """
    try:
        relative = manifest_path.resolve().relative_to(MANIFEST_ROOT.resolve())
    except (ValueError, OSError) as exc:
        raise Aborted(
            f"{manifest_path} is not under {MANIFEST_ROOT}/<client>/ — setup-timer needs a "
            "manifest at its canonical, client-scoped home to name the build timer safely "
            "and to give the generated script a shared, non-user-specific location. See "
            "`cairn-build setup --client <name> --environment <name>`."
        ) from exc
    if len(relative.parts) < 2:
        raise Aborted(
            f"{manifest_path} sits directly under {MANIFEST_ROOT}, not inside a client "
            "directory. See `cairn-build setup --client <name> --environment <name>`."
        )
    return relative.parts[0]


def build_unit_name(options: SetupOptions) -> str:
    """The unit basename for *options* (`ADR-052`, `ADR-062`) —
    e.g. ``cairn-build-acmecorp-erpnext-v16-production``.

    Parameterized on the full `(client, image_name, environment)` uniqueness key so more
    than one manifest's build timer can coexist on one machine: two `setup-timer` calls for
    two different manifests write two different, independently manageable units, rather than
    the second silently colliding with a name the first also produces. `client` and
    `image_name` come from the manifest's own location and content (`BR-DEPLOY-009a`), never
    a flag, so this can never disagree with what the script it names actually builds.
    """
    client = client_from_manifest(options.manifest)
    return f"cairn-build-{client}-{options.image_name}-{options.environment}"


def stage_timers_build(runner: Runner, options: SetupOptions) -> None:
    """Install the build timer, enabling but not starting it.

    Not started deliberately: the first build should be watched. A timer that fires before
    anyone has confirmed the manifest turns one wrong configuration into a wrong deploy every
    quarter of an hour. `setup-timer` has no preceding `preflight` stage, so this checks
    root itself (`BR-CLI-023`).
    """
    require_root(runner)
    cairn_build = find_executable("cairn-build")
    unit = build_unit_name(options)
    script = options.manifest.parent / f"{unit}.sh"
    runner.write(
        script, build_script(options, cairn_build), mode=0o755, what=f"build script at {script}"
    )
    runner.write(
        SYSTEMD_DIR / f"{unit}.service", build_service(options, script), what="build service"
    )
    runner.write(SYSTEMD_DIR / f"{unit}.timer", build_timer(options), what="build timer")

    runner.run(["systemctl", "daemon-reload"], what="reloading systemd")
    runner.run(["systemctl", "enable", f"{unit}.timer"], what=f"enabling {unit}.timer")
    runner.report.warnings.append(
        f"{unit}.timer is enabled but NOT started — run the first build by hand first, "
        f"then `systemctl start {unit}.timer`"
    )


def build_script(options: SetupOptions, cairn_build: Path) -> str:
    """Build and push, retag the environment onto whatever resulted, then prune superseded
    local images (`ADR-052`).

    `cairn-build build --push` is already an idempotent change detector — it resolves refs,
    computes the input hash, and short-circuits (locally, then in the registry, `BR-BUILD-014`/
    `014a`) when that hash is already built. So a timer is the whole of the trigger; no watcher
    is needed and a no-op poll costs three `git ls-remote` calls. `--assign-tag`
    (`BR-CLI-002a`) folds the retag into the same call rather than a second command — no
    `--environment` argument anywhere, since the manifest already declares exactly one
    (`BR-DEPLOY-009a`). `prune` (`ADR-051`) rides the same script rather than a separate timer,
    since local cruft only ever exists because this machine's own build just ran.
    """
    return f"""\
#!/bin/bash -e
# Written by `cairn-build setup-timer`. `cairn-build build --push` is idempotent: with no new
# commits it resolves refs, sees the input hash is already built, and exits without building.
cd {options.manifest.parent}
MANIFEST={shlex.quote(str(options.manifest))}
{cairn_build} build --manifest "$MANIFEST" --push --assign-tag --yes
{cairn_build} prune --keep 1 --yes
"""


def build_service(options: SetupOptions, script: Path) -> str:
    """The build unit.

    The script itself always passes `--manifest` explicitly (`ADR-042` — cairn never
    searches for one); ``WorkingDirectory`` is *script*'s own directory — the manifest's
    canonical `/srv/cairn/<client>/` home (`ADR-047`, `ADR-062`), never `options.workdir`.
    `options.workdir` defaults to the invoking shell's `cwd`, which a retired operator
    account can take with it (`ADR-062`'s whole point) — a unit whose `WorkingDirectory`
    still pointed there would fail to start once that directory is gone, even though the
    script itself had already been relocated to safety.
    """
    return f"""\
[Unit]
Description=cairn-build ({options.environment}) — build if the manifest's refs have moved
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory={script.parent}
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
Description=cairn-build ({options.environment}) — poll for new commits and build

[Timer]
OnBootSec=5min
OnUnitInactiveSec={options.build_interval}
RandomizedDelaySec=60
Persistent=true
Unit={build_unit_name(options)}.service

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
    runner.report.warnings.append("the backup is on the box; copy it off before relying on it")


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
    runner.say(
        f"    describes environment '{parsed.get('environment')}' on site '{parsed.get('site')}'"
    )


def stage_timers_adopt(runner: Runner, options: SetupOptions) -> None:
    """Install the reconcile timer, enabling but not starting it.

    Not started deliberately: the first reconcile should be watched. Rendered in-process via
    :func:`cairn.systemd.units` — no subprocess, no output to parse (`ADR-046`).
    `setup-timer` has no preceding `preflight` stage, so this checks root itself
    (`BR-CLI-023`).
    """
    require_root(runner)
    cairn_adopt = find_executable("cairn-adopt")
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


# --- entry points -------------------------------------------------------------

BUILD_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "preflight": stage_preflight_build,
    "admin-group": stage_admin_group,
    "manifest": stage_manifest,
}

ADOPT_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "preflight": stage_preflight_adopt,
    "admin-group": stage_admin_group,
    "recon": stage_recon,
    "backup": stage_backup,
    "descriptor": stage_descriptor,
}

#: `setup-timer`'s own stage table — one stage, no `--only` needed (`BR-CLI-023`).
BUILD_TIMER_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "timers": stage_timers_build,
}

ADOPT_TIMER_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "timers": stage_timers_adopt,
}
