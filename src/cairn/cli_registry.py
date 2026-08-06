"""`cairn-registry` — the registry-host CLI (`BR-CLI-001`, group C of `BR-CLI`, `ADR-048`).

Provisions and operates a local OCI registry: lifecycle (`status`/`start`/`stop`/`restart`),
introspection (`images`), retention (`prune`), and garbage collection (`gc`). Independent of
the other two roles — reads no manifest and no `[cairn] environment` (`BR-REG-001`); every
decision comes from `/etc/cairn/registry.toml` and the registry's own API.
"""

from __future__ import annotations

import fnmatch
import json
import shutil
import subprocess
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, images, registry, registry_config, registry_provision, registry_retention
from .cli_support import done, note, run, step, version_callback
from .errors import CairnError, RegistryError
from .setup_runner import Aborted, Runner, SetupOptions, execute

app = typer.Typer(
    name="cairn-registry",
    help=(
        "Provision and operate a local OCI registry: lifecycle, introspection, retention, "
        "and garbage collection."
    ),
    no_args_is_help=True,
    add_completion=False,
)

#: Doctor's disk-headroom floor for the registry's own data directory — a much smaller
#: number than a build machine's (`setup_runner.MINIMUM_DISK_GB`, 30 GB): a registry holds
#: layers, not a builder stage, a build context, and BuildKit's own cache all at once.
_MINIMUM_DISK_GB = 5


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback("cairn-registry", __version__),
            is_eager=True,
            help="Show the cairn-registry version and exit.",
        ),
    ] = False,
) -> None:
    """cairn-registry — provision and operate a local OCI registry."""


# --- lifecycle (BR-CLI-024, BR-REG-004) --------------------------------------


@app.command("status", help="Show the registry container's own compose status.")
def status_command() -> None:
    typer.echo(registry_provision.status(Runner(dry_run=False, force=False)))


@app.command("start", help="Start the registry (docker compose up -d).")
def start_command() -> None:
    raise typer.Exit(_run_lifecycle(registry_provision.start))


@app.command("stop", help="Stop the registry (docker compose stop). Data is untouched.")
def stop_command() -> None:
    raise typer.Exit(_run_lifecycle(registry_provision.stop))


@app.command("restart", help="Restart the registry (docker compose restart).")
def restart_command() -> None:
    raise typer.Exit(_run_lifecycle(registry_provision.restart))


def _run_lifecycle(action) -> int:
    runner = Runner(dry_run=False, force=False)
    try:
        action(runner)
    except Aborted as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        return 2
    for line in runner.report.done:
        done(line)
    return 0


# --- introspection (BR-CLI-024, BR-REG-005) ----------------------------------


@app.command(
    "images",
    help=(
        "List cairn-built images across a registry, read remotely with no pull. Defaults to "
        "this machine's own registry; --host points elsewhere. --namespace/--image narrow "
        "which repositories are read; an exact --namespace + --image reads that one repository "
        "directly, which is what reaches an authenticated remote like GHCR."
    ),
)
def images_command(
    host: Annotated[
        str | None,
        typer.Option(
            "--host", help="Registry host:port to query. Default: this machine's own registry."
        ),
    ] = None,
    namespace: Annotated[
        str | None,
        typer.Option("--namespace", help="Only repositories directly under this namespace."),
    ] = None,
    image: Annotated[
        str | None,
        typer.Option(
            "--image", help="Only this image name; a glob (e.g. 'erpnext-*') matches several."
        ),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Machine-readable output.")] = False,
) -> None:
    def _action() -> int:
        target_host = host or registry_config.load().host

        if namespace is not None and image is not None and not _is_glob(image):
            # One named repository — read it directly (`registry.tags`/`inspect`'s
            # anonymous-then-bearer-token flow), never the catalog. This is what reaches an
            # authenticated remote registry (GHCR and similar), which the catalog endpoint
            # below cannot (`BR-REG-005`, `ADR-069`).
            repositories = [f"{namespace}/{image}"]
        else:
            repositories = [
                name for name in registry.catalog(target_host) if _matches(name, namespace, image)
            ]
            if not repositories:
                note(f"No repositories found in {target_host}.")
                return 0

        reports: list[tuple[registry.ImageRef, list, int]] = []
        empty = 0
        for name in repositories:
            base = registry.ImageRef(target_host, name, "")
            found, others = images.inspect_registry(base)
            if not found:
                empty += 1
                continue
            reports.append((base, images.group_registry(found), others))

        if as_json:
            payload = {
                "registry": target_host,
                "repositories": [
                    images.registry_payload(base, grouped, others)
                    for base, grouped, others in reports
                ],
                "repositories_without_cairn_images": empty,
            }
            typer.echo(json.dumps(payload, indent=2))
            return 0

        if not reports:
            note(
                f"No images cairn built were found among {len(repositories)} "
                f"repositories in {target_host}."
            )
            return 0

        # Registry printed once, separately from each repository — the same split a target
        # descriptor's `registry_host`/`image` now makes, rather than one glued-together
        # string repeated on every line.
        note(f"Registry {target_host}")
        note("")
        for base, grouped, others in reports:
            note(f"Repository {base.base}")
            note(images.render_registry(base, grouped, others))
        if empty:
            note(f"{empty} other repositories in {target_host} hold no images cairn built.")
        return 0

    run(_action)


def _matches(name: str, namespace: str | None, image_pattern: str | None) -> bool:
    """Whether catalog repository *name* satisfies the optional filters (`BR-REG-005`)."""
    repo_namespace, _, image_name = name.rpartition("/")
    if namespace is not None and repo_namespace != namespace:
        return False
    return image_pattern is None or fnmatch.fnmatchcase(image_name, image_pattern)


def _is_glob(pattern: str) -> bool:
    """Whether *pattern* uses an `fnmatch` metacharacter, rather than naming one exact image."""
    return any(ch in pattern for ch in "*?[")


# --- retention (BR-CLI-025, BR-REG-006/007/008) ------------------------------


@app.command(
    "prune",
    help=(
        "Report registry digests beyond the retention window; deletes them only if "
        "retention.enabled is true."
    ),
)
def prune_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report only; delete nothing.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Skip the confirmation prompt.")] = False,
) -> None:
    def _action() -> int:
        config = registry_config.load()
        repositories = registry.catalog(config.host)
        if not repositories:
            note(f"No repositories found in {config.host}.")
            return 0

        total_deleted = 0
        total_failed = 0
        for name in repositories:
            base = registry.ImageRef(config.host, name, "")
            plan = registry_retention.select(
                registry_retention.candidates(base),
                keep_last=config.retention.keep_last,
                max_age_days=config.retention.max_age_days,
            )
            note(f"{name}:")
            note(registry_retention.render(plan))

            if plan.is_empty or dry_run:
                continue
            if not config.retention.enabled:
                note("  registry.toml's retention.enabled is false — nothing deleted.")
                continue
            if not yes and not typer.confirm(
                f"Delete {len(plan.deletions)} digest(s) in {name}?", default=False
            ):
                note("  Skipped.")
                continue

            deleted, failures = registry_retention.delete(base, plan)
            total_deleted += len(deleted)
            total_failed += len(failures)
            for failure in failures:
                note(f"  FAILED: {failure}")

        if total_deleted or total_failed:
            done(f"Deleted {total_deleted} digest(s); {total_failed} failure(s).")
        return 1 if total_failed else 0

    run(_action)


@app.command(
    "gc",
    help=(
        "Reclaim blob storage for digests `prune` already deleted. Briefly makes the "
        "registry read-only; requires --yes or --dry-run."
    ),
)
def gc_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Report the read-only window, then stop.")
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", help="Confirm running gc now.")] = False,
) -> None:
    def _action() -> int:
        step("gc briefly makes the registry read-only: pulls continue, pushes are refused.")
        if dry_run:
            note("--dry-run: nothing was run.")
            return 0
        if not yes:
            raise CairnError(
                "Refusing to run without --yes or --dry-run — gc briefly blocks pushes."
            )

        runner = Runner(dry_run=False, force=False)
        try:
            registry_provision.gc(runner)
        except Aborted as exc:
            raise CairnError(str(exc)) from exc
        for line in runner.report.done:
            done(line)
        for line in runner.report.warnings:
            note(line)
        return 0

    run(_action)


# --- doctor (BR-CLI-007, BR-REG-011) ------------------------------------------


@app.command(
    "doctor",
    help="Check that this registry is reachable, its certificate is valid, and it has disk room.",
)
def doctor_command() -> None:
    run(_run_doctor)


def _run_doctor() -> int:
    config = registry_config.load()
    checks = [_check_reachable(config), _check_certificate(), _check_disk_headroom(config)]

    for label, ok, detail in checks:
        mark = "OK   " if ok else "FAIL "
        typer.secho(mark, fg=typer.colors.GREEN if ok else typer.colors.RED, bold=True, nl=False)
        typer.echo(f"{label:<16}{detail}")

    failures = [c for c in checks if not c[1]]
    if failures:
        typer.secho(
            f"\n{len(failures)} of {len(checks)} checks failed.", fg=typer.colors.RED, err=True
        )
        return 1
    typer.secho(f"\nAll {len(checks)} checks passed.", fg=typer.colors.GREEN)
    return 0


def _check_reachable(config: registry_config.RegistryConfig) -> tuple[str, bool, str]:
    try:
        repositories = registry.catalog(config.host)
    except RegistryError as exc:
        return "reachable", False, str(exc).splitlines()[0]
    return "reachable", True, f"{config.host} — {len(repositories)} repositor(y/ies)"


def _check_certificate() -> tuple[str, bool, str]:
    crt = registry_provision.CERT_DIR / "registry.crt"
    if not crt.is_file():
        return "certificate", False, f"{crt} not found — run `cairn-registry setup`"
    try:
        result = subprocess.run(
            ["openssl", "x509", "-checkend", "0", "-noout", "-in", str(crt)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return "certificate", False, f"could not check {crt} ({exc})"
    if result.returncode != 0:
        return "certificate", False, f"{crt} has expired — re-run `cairn-registry setup`"
    return "certificate", True, f"{crt} valid"


def _check_disk_headroom(config: registry_config.RegistryConfig) -> tuple[str, bool, str]:
    label = "disk headroom"
    try:
        path = config.data_dir if config.data_dir.exists() else config.data_dir.parent
        free_gb = shutil.disk_usage(path).free / 1_000_000_000
    except OSError as exc:
        return label, False, f"{config.data_dir} cannot be checked ({exc})"
    ok = free_gb >= _MINIMUM_DISK_GB
    detail = f"{free_gb:.0f} GB free at {config.data_dir}"
    if not ok:
        detail += f" — needs {_MINIMUM_DISK_GB} GB"
    return label, ok, detail


# --- setup / setup-timer (BR-CLI-021/023/027, BR-DEPLOY-021, BR-REG-003/010) -


@app.command(
    "setup",
    help=(
        "Provision this machine as a registry host. Must be run with sudo; see "
        "`setup-timer` for maintenance automation."
    ),
)
def setup_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print every action, and change nothing.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Replace existing files (the old ones are kept).")
    ] = False,
    only: Annotated[
        str | None,
        typer.Option(
            "--only", help=f"Run one stage: {', '.join(registry_provision.REGISTRY_STAGES)}."
        ),
    ] = None,
    private_ip: Annotated[
        str | None,
        typer.Option("--private-ip", help="Also put this IP in the registry certificate."),
    ] = None,
    skip_disk_free: Annotated[
        bool,
        typer.Option(
            "--skip-disk-free", help="Proceed even if free disk space is below the minimum."
        ),
    ] = False,
    admin_group: Annotated[
        str, typer.Option("--admin-group", help="Group /etc/cairn is shared with.")
    ] = "cairn-admins",
    no_admin_group: Annotated[
        bool,
        typer.Option(
            "--no-admin-group", help="Skip sharing /etc/cairn with a group; leave it as found."
        ),
    ] = False,
) -> None:
    """Provision a registry host (BR-CLI-021, BR-REG-003, BR-DEPLOY-021).

    Root-gated: exits reporting the shortfall rather than attempting a partial run without
    the privilege its actions require. No `--workdir`: unlike `cairn-build`/`cairn-adopt setup`,
    none of this command's three stages read it — there is no manifest to resolve relative to it
    (`BR-REG-001`) — so offering the flag would promise a relevance it doesn't have.

    A real (non-dry-run) run that actually brought the registry up — the whole run, or
    `--only registry` on its own — finishes by running `doctor` and adopting its exit code:
    the installer's own `--- summary ---` is a log of actions taken, not a health verdict, and
    `doctor` is the fuller one (certificate validity, disk headroom, not just "the container
    started"). Skipped for `--dry-run` (nothing to check yet) and for `--only preflight`/
    `--only admin-group` (the registry container was never touched by either).
    """
    options = SetupOptions(
        dry_run=dry_run,
        force=force,
        private_ip=private_ip,
        skip_disk_free=skip_disk_free,
        admin_group=None if no_admin_group else admin_group,
    )
    runner = Runner(dry_run=dry_run, force=force)
    code = execute(
        runner,
        options,
        registry_provision.REGISTRY_STAGE_FUNCS,
        registry_provision.REGISTRY_STAGES,
        only,
        program="cairn-registry",
        show_workdir=False,
    )
    if code == 0 and not dry_run and only in (None, "registry"):
        step("setup complete — verifying with `cairn-registry doctor`:")
        code = _run_doctor()
    raise typer.Exit(code)


@app.command(
    "setup-timer",
    help="Install (but do not start) the prune/gc maintenance timer. Must be run with sudo.",
)
def setup_timer_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print every action, and change nothing.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Replace existing files (the old ones are kept).")
    ] = False,
    workdir: Annotated[
        Path,
        typer.Option("--workdir", help="Directory to record in reported paths."),
    ] = Path.cwd(),  # noqa: B008 - Typer evaluates defaults once, by design
) -> None:
    """Install the maintenance-automation timer only (BR-CLI-027, BR-REG-010, ADR-063).

    Root-gated the same way `setup` is — writing to `/etc/systemd/system` needs it, and
    this command has no preceding `preflight` stage of its own to have already checked. The
    generated script is written to `/opt/cairn-registry`, not this command's `--workdir` —
    that stays a durable, non-user-specific home regardless of where `setup-timer` happens
    to be invoked from.
    """
    options = SetupOptions(dry_run=dry_run, force=force, workdir=workdir)
    runner = Runner(dry_run=dry_run, force=force)
    raise typer.Exit(
        execute(
            runner,
            options,
            registry_provision.REGISTRY_TIMER_STAGE_FUNCS,
            registry_provision.TIMER_STAGES,
            None,
            program="cairn-registry",
            verb="setup-timer",
        )
    )


def main() -> None:
    """Console-script entry point for the ``cairn-registry`` command."""
    app()


if __name__ == "__main__":
    main()
