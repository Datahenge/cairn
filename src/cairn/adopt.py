"""Derive an environment descriptor from a deployment already running (`BR-CLI-020`).

`BR-DEPLOY-010a` says a target is described by `/etc/cairn/adopt.toml`. Writing that file
by hand means transcribing facts off a running box — the compose project, which overrides are
layered, the exact site name, the image currently deployed — and a transcription error there is
not a typo, it is a wrong deploy. Three of the sharpest risks in adopting an existing stack come
from exactly that.

So cairn reads them instead, from the live stack, and **prints** the descriptor. It writes
nothing (`ADR-040`), which is the same contract `cairn systemd-units` has and gives the CLI one
rule:

    cairn prints host configuration; the operator installs it.

Two disciplines make the output trustworthy rather than merely plausible:

* **Gaps are reported, never filled.** Anything that cannot be determined is named along with
  the reason and left absent from the emitted TOML. A default silently inserted here surfaces
  weeks later as a stack composed from the wrong files.
* **What is printed must be loadable.** The result is round-tripped through
  :func:`descriptor.load` before it is offered, so `adopt` cannot emit something `reconcile`
  would reject.

It also answers two questions that decide whether adopting this host is safe at all: whether the
manifest's ordered app list matches what the site actually has installed (`BR-BUILD-003`), and
whether the host serves more than one site — which `BR-DEPLOY-014` does not support and which
`reconcile` would silently narrow.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .config import Manifest
from .descriptor import Compose, Descriptor, Health

#: Ceiling on any probe. Every command here is informational; a slow answer is a broken one.
PROBE_TIMEOUT_SECONDS = 120

#: The compose service `bench` runs in, per frappe_docker's own layout.
BENCH_SERVICE = "backend"

#: A container cairn itself stood up as supporting infrastructure carries this label —
#: `registry_compose()` in `provision.py` is the one place that writes it. Identifying "cairn
#: made this" by label rather than by a project's *name* means an operator's own project can
#: never collide with it: `cairn-registry` is only the *default* name compose gives that
#: directory, never something cairn asserts or enforces.
CAIRN_MANAGED_LABEL = "com.datahenge.cairn.managed"

#: An override path looks like ``…/overrides/compose.<name>.yaml``; this recovers ``<name>``.
_OVERRIDE_RE = re.compile(r"overrides/compose\.(?P<name>[^/]+)\.ya?ml$")


@dataclass(frozen=True)
class Finding:
    """One fact `adopt` could not establish, and why.

    Carried rather than raised: a single unanswerable question should not deny the operator
    everything else that *was* discovered.
    """

    subject: str
    detail: str

    def render(self) -> str:
        return f"  {self.subject}: {self.detail}"


@dataclass
class Survey:
    """What the running deployment turned out to be."""

    project: str | None = None
    directory: Path | None = None
    overrides: tuple[str, ...] = ()
    env_file: Path | None = None
    sites: tuple[str, ...] = ()
    apps: tuple[str, ...] = ()
    image: str | None = None
    tag: str | None = None
    findings: list[Finding] = field(default_factory=list)

    @property
    def is_multi_site(self) -> bool:
        """Whether this host serves more than one site — a stop, not a warning.

        `BR-DEPLOY-014` gives an environment exactly one site, and `reconcile` sets ``SITES``
        from a descriptor naming one. Converging a multi-site host would drop the others from
        the proxy configuration.
        """
        return len(self.sites) > 1

    @property
    def site(self) -> str | None:
        return self.sites[0] if self.sites else None


def survey(project: str | None = None) -> Survey:
    """Inspect the running frappe_docker deployment on this host (`BR-CLI-020`)."""
    found = Survey()

    _survey_project(found, project)
    _survey_sites_and_apps(found)
    _survey_image(found)
    return found


def descriptor_for(found: Survey, environment: str) -> Descriptor:
    """Assemble a descriptor from *found*, or raise :class:`ValueError` if it cannot be.

    Raises rather than emitting a half-descriptor: the caller reports the findings and stops.
    `reconcile` refusing a malformed file later is a worse failure than refusing to write one
    now.
    """
    if found.image is None or found.tag is None:
        raise ValueError("the image and tag currently deployed could not be determined")
    if found.site is None:
        raise ValueError("no site could be found in the running stack")

    return Descriptor(
        environment=environment,
        image=found.image,
        tag=found.tag,
        site=found.site,
        compose=Compose(
            overrides=found.overrides,
            directory=found.directory,
            project=found.project,
            env_file=found.env_file,
        ),
        health=Health(),
    )


def render(found: Survey, environment: str) -> str:
    """Render *found* as a descriptor TOML, ready to be written by the operator.

    Hand-written rather than serialized by a library so the file carries the comments an
    operator needs — most importantly that the health URL is deliberately absent.
    """
    proposed = descriptor_for(found, environment)
    compose = proposed.compose

    lines = [
        "# Generated by `cairn-adopt examine` from the deployment running on this host.",
        "# Review it, then install it as /etc/cairn/adopt.toml.",
        "",
        f'environment = "{proposed.environment}"',
        f'image       = "{proposed.image}"',
        f'tag         = "{proposed.tag}"',
        f'site        = "{proposed.site}"',
        "",
        "[compose]",
    ]
    if compose.directory is not None:
        lines.append(f'directory = "{compose.directory}"')
    if compose.project:
        lines.append(f'project   = "{compose.project}"')
    if compose.env_file is not None:
        lines.append(f'env_file  = "{compose.env_file}"')
    lines.append(
        "# Layered in this order — compose applies later files over earlier ones."
        if compose.overrides
        else "# No overrides are layered by the running stack."
    )
    lines.append("overrides = [" + ", ".join(f'"{name}"' for name in compose.overrides) + "]")
    lines += [
        "",
        "[health]",
        f"timeout_seconds  = {proposed.health.timeout_seconds}",
        f"interval_seconds = {proposed.health.interval_seconds}",
        "# `url` is deliberately unset: reconcile probes it with curl from inside the backend",
        "# container, which the image may not carry. Unset means container health only.",
    ]
    return "\n".join(lines) + "\n"


def report(found: Survey, manifest: Manifest | None = None) -> list[str]:
    """Describe what was found, what was not, and what looks wrong (`BR-CLI-020`)."""
    lines = [
        f"Compose project   {found.project or '?'}",
        f"Compose files     {found.directory or '?'}"
        + (f" + {len(found.overrides)} override(s)" if found.overrides else ""),
        f"Sites             {', '.join(found.sites) or '?'}",
        f"Installed apps    {', '.join(found.apps) or '?'}",
        f"Running image     {found.image or '?'}:{found.tag or '?'}",
    ]

    if found.findings:
        lines.append("")
        lines.append("Could not determine:")
        lines += [finding.render() for finding in found.findings]

    if found.is_multi_site:
        lines += [
            "",
            f"STOP: this host serves {len(found.sites)} sites, and a descriptor names one. "
            f"Converging it would drop the others from the proxy configuration. Decide how "
            f"multiple sites should be handled before adopting this host.",
        ]

    if manifest is not None:
        lines += _app_mismatch(found, manifest)
    return lines


def _app_mismatch(found: Survey, manifest: Manifest) -> list[str]:
    """Compare the manifest's ordered app list with what the site actually has installed.

    The likeliest way a first deploy fails: `reconcile` runs `bench migrate` against an image
    whose apps differ from the site's, so the migration meets code the site does not expect.
    Frappe itself is excluded — it is supplied by build-arg and never appears in the manifest's
    app list (`BR-BUILD-004`), but it *is* installed on every site.
    """
    if not found.apps:
        return ["", "Apps could not be read, so the manifest was not cross-checked."]

    declared = [app.name for app in manifest.apps]
    installed = [app for app in found.apps if app != "frappe"]

    if declared == installed:
        return ["", f"Manifest matches the site's apps, in order: {', '.join(declared)}."]

    lines = ["", "WARNING: the manifest's apps do not match this site's."]
    lines.append(f"  manifest:  {', '.join(declared) or '(none)'}")
    lines.append(f"  installed: {', '.join(installed) or '(none)'}")

    if sorted(declared) == sorted(installed):
        lines.append(
            "  Same apps, different order. The list is an install sequence, so fix the order "
            "before building."
        )
    else:
        missing = [name for name in installed if name not in declared]
        extra = [name for name in declared if name not in installed]
        if missing:
            lines.append(f"  Installed but not in the manifest: {', '.join(missing)}")
        if extra:
            lines.append(f"  In the manifest but not installed: {', '.join(extra)}")
        lines.append(
            "  Deploying this image would migrate the site against apps it does not have, or "
            "drop apps it does. Reconcile the two before building."
        )
    return lines


# --- discovery ---------------------------------------------------------------


def _survey_project(found: Survey, wanted: str | None) -> None:
    """Read the compose project and, from its config files, the tree and overrides in use."""
    listing = _capture(["docker", "compose", "ls", "--format", "json"])
    if listing is None:
        found.findings.append(
            Finding("compose project", "`docker compose ls` did not answer; is Docker running?")
        )
        return

    try:
        projects = json.loads(listing)
    except json.JSONDecodeError:
        found.findings.append(Finding("compose project", "compose's project list was not JSON"))
        return
    if not isinstance(projects, list) or not projects:
        found.findings.append(
            Finding("compose project", "no compose project is running on this host")
        )
        return

    candidates = projects
    if wanted is None:
        # Auto-detection only — an operator naming a project explicitly is trusted as-is.
        managed = _cairn_managed_projects()
        own_site = [p for p in projects if isinstance(p, dict) and p.get("Name") not in managed]
        if not own_site:
            found.findings.append(
                Finding("compose project", "no compose project is running on this host")
            )
            return
        candidates = own_site

    chosen = _pick_project(candidates, wanted)
    if chosen is None:
        names = ", ".join(str(p.get("Name")) for p in projects if isinstance(p, dict))
        found.findings.append(
            Finding("compose project", f"'{wanted}' is not running; found: {names}")
        )
        return

    found.project = chosen.get("Name")
    files = [part for part in str(chosen.get("ConfigFiles", "")).split(",") if part.strip()]
    if not files:
        found.findings.append(
            Finding("compose files", "compose reported no config files for this project")
        )
        return

    found.directory = Path(files[0].strip()).parent
    found.overrides = tuple(
        match.group("name")
        for path in files
        if (match := _OVERRIDE_RE.search(path.strip())) is not None
    )
    env_file = found.directory / ".env"
    if env_file.is_file():
        found.env_file = env_file


def _pick_project(projects: list, wanted: str | None) -> dict | None:
    """Choose the project to adopt, refusing to guess between several."""
    running = [p for p in projects if isinstance(p, dict) and p.get("Name")]
    if wanted is not None:
        return next((p for p in running if p.get("Name") == wanted), None)
    return running[0] if len(running) == 1 else None


def _cairn_managed_projects() -> set[str]:
    """Compose projects with at least one container cairn itself stood up.

    Read from `docker ps`'s own compose labels rather than assumed from a name: any container
    matching `CAIRN_MANAGED_LABEL` already carries `com.docker.compose.project`, since compose
    applies that to everything it creates.
    """
    output = _capture(
        [
            "docker", "ps",
            "--filter", f"label={CAIRN_MANAGED_LABEL}=true",
            "--format", '{{.Label "com.docker.compose.project"}}',
        ]
    )
    if not output:
        return set()
    return {line.strip() for line in output.splitlines() if line.strip()}


def _survey_sites_and_apps(found: Survey) -> None:
    """Read the real sites from the filesystem, then installed apps from bench.

    A site is authoritatively a ``sites/<name>/site_config.json`` — the same test bench itself
    uses to recognize one — rather than anything parsed out of ``bench --site all list-apps``.
    That command's own formatting has varied across versions: recent Frappe (measured on
    16.26.1) omits the site-name header entirely when there is exactly one site, printing a
    flat, unindented app list — which older parsing here, keyed on indentation, misread as one
    "site" per app, with zero apps found at all. Filesystem enumeration has no such ambiguity.
    """
    if found.project is None:
        return

    listing = _capture(
        self_compose(
            found,
            ["exec", "-T", BENCH_SERVICE, "find", "sites", "-maxdepth", "2", "-name",
             "site_config.json"],
        )
    )
    if listing is None:
        found.findings.append(
            Finding("sites", "could not list `sites/`; is the backend container up?")
        )
        return

    sites = tuple(sorted({
        line.strip().split("/")[-2] for line in listing.splitlines() if line.strip()
    }))
    found.sites = sites
    if not sites:
        found.findings.append(
            Finding("sites", "no site_config.json was found under sites/; nothing to converge")
        )
        return

    output = _capture(
        self_compose(found, ["exec", "-T", BENCH_SERVICE, "bench", "--site", "all", "list-apps"])
    )
    if output is None:
        found.findings.append(
            Finding(
                "apps", "`bench --site all list-apps` did not answer; is the backend container up?"
            )
        )
        return
    found.apps = _parse_apps(output, sites)


def _parse_apps(output: str, sites: tuple[str, ...]) -> tuple[str, ...]:
    """Parse ``bench --site all list-apps`` output into installed apps.

    Every line names an app, except a line that is itself one of the *known* site names —
    some bench versions print a site-name header before that site's apps; the single-site case
    on recent Frappe omits it and prints a flat list instead. Filtering against the
    authoritative site list (from ``sites/*/site_config.json``) handles both without depending
    on indentation, which is exactly what varied between them.
    """
    apps: list[str] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            continue
        name = line.split()[0].rstrip(":")
        if name in sites:
            continue
        if name not in apps:
            apps.append(name)
    return tuple(apps)


def _survey_image(found: Survey) -> None:
    """Read the image the bench service is actually running, and split off its tag.

    Read from the running container rather than from ``.env``, because the two disagree the
    moment somebody edits one without recreating the other — and what is *running* is the fact
    a descriptor must record.
    """
    if found.project is None:
        return

    output = _capture(self_compose(found, ["ps", "--format", "json"]))
    if output is None:
        found.findings.append(Finding("running image", "`docker compose ps` did not answer"))
        return

    reference = _bench_image(output)
    if reference is None:
        found.findings.append(
            Finding("running image", f"no running '{BENCH_SERVICE}' service was found")
        )
        return

    base, _, tag = reference.rpartition(":")
    if not base or "/" in tag:
        found.findings.append(
            Finding("running image", f"'{reference}' carries no tag, so none can be watched")
        )
        return
    found.image, found.tag = base, tag


def _bench_image(output: str) -> str | None:
    """Pull the bench service's image out of ``compose ps`` JSON.

    Compose emits either one object per line or a single array, depending on its version; both
    are handled because a target's compose version is not ours to choose.
    """
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for service in entry if isinstance(entry, list) else [entry]:
            if not isinstance(service, dict):
                continue
            if service.get("Service") == BENCH_SERVICE and service.get("Image"):
                return str(service["Image"])
    return None


def self_compose(found: Survey, arguments: list[str]) -> list[str]:
    """A ``docker compose`` invocation scoped to the surveyed project.

    Deliberately addresses the project by **name** rather than by rebuilding its file list: the
    point is to ask the stack that is actually running, and a reconstructed `--file` set could
    describe a different one.
    """
    command = ["docker", "compose"]
    if found.project:
        command += ["--project-name", found.project]
    return command + arguments


def validate(rendered: str) -> None:
    """Confirm the emitted TOML parses and satisfies the descriptor's own rules.

    `adopt` must not print something `reconcile` would refuse. Parsed here rather than trusting
    the renderer, so a formatting mistake fails now instead of at the next deploy.
    """
    try:
        tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"the generated descriptor is not valid TOML — {exc}") from exc


def _capture(command: list[str]) -> str | None:
    """Run an informational command, returning stdout, or None if it failed.

    The single seam every probe funnels through, so tests substitute one function.
    """
    try:
        result = subprocess.run(
            command,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout if result.returncode == 0 else None


def command_line(command: list[str]) -> str:
    """Render a command for reporting, so an operator can rerun it by hand."""
    return shlex.join(command)
