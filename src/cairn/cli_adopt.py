"""`cairn-adopt` — the target CLI (`BR-CLI-001`, group B of `BR-CLI`).

Surveys an existing frappe_docker deployment into a descriptor (`examine`), converges a
target to its desired state (`reconcile`), and provisions a target machine. Never builds
or touches the registry's write path — that is `cairn-build`'s job (`ADR-046`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import __version__, adopt, config, descriptor, doctor, reconcile, systemd, timing
from .cli_support import done, note, report_timing, run, step, version_callback
from .errors import CairnError
from .provision import (
    ADOPT_STAGE_FUNCS,
    ADOPT_STAGES,
    ADOPT_TIMER_STAGE_FUNCS,
    TIMER_STAGES,
    Runner,
    SetupOptions,
    execute,
)

app = typer.Typer(
    name="cairn-adopt",
    help="Bring an existing frappe_docker deployment under cairn's management, and converge it.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback("cairn-adopt", __version__),
            is_eager=True,
            help="Show the cairn-adopt version and exit.",
        ),
    ] = False,
) -> None:
    """cairn-adopt — survey and converge a target deployment."""


@app.command(
    "reconcile",
    help=(
        "Converge this host to the image its environment's tag points at. Idempotent; "
        "never rolls back on failure — it stops and reports."
    ),
)
def reconcile_command(
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would converge, and change nothing.")
    ] = False,
    descriptor_path: Annotated[
        Path | None,
        typer.Option(
            "--descriptor",
            help="Read this descriptor instead of the host's.",
            hidden=True,
        ),
    ] = None,
) -> None:
    """Converge the target to its desired state (BR-CLI-008, BR-DEPLOY-003).

    Deliberately does **not** require a cairn project: a target has no manifest and no
    vendored tree, only the descriptor that says what it runs (`ADR-034`).
    """
    watch = timing.Stopwatch()
    try:
        environment = descriptor.load(descriptor_path)
        step(f"Environment {environment.environment} — site {environment.site}")

        with watch.phase("converge"):
            outcome = reconcile.run(environment, dry_run=dry_run, report=step)

        if outcome.changed:
            done(outcome.detail)
        else:
            note(outcome.detail)
        report_timing(watch)
        raise typer.Exit(0)
    except CairnError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        report_timing(watch)
        raise typer.Exit(2) from exc
    except KeyboardInterrupt:
        typer.secho("Interrupted.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(130) from None


@app.command(
    "examine",
    help=(
        "Read the running deployment and print an environment descriptor for it. Writes "
        "nothing; review it, then install it (or run `setup`)."
    ),
)
def examine_command(
    environment: Annotated[
        str, typer.Option("--environment", help="Name for this environment in the descriptor.")
    ] = "production",
    project: Annotated[
        str | None,
        typer.Option("--project", help="Compose project to read; default: the only one running."),
    ] = None,
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Cross-check this manifest's apps against the site."),
    ] = None,
) -> None:
    """Print a descriptor derived from the running deployment (BR-CLI-020).

    A host being examined has neither a cairn project nor a manifest yet, so this command
    needs neither — requiring either would make it useless exactly when it is needed. The
    manifest is read only when asked for, purely to cross-check.
    """
    try:
        found = adopt.survey(project)

        manifest = config.load_manifest(manifest_path) if manifest_path is not None else None
        for line in adopt.report(found, manifest):
            note(line)
        note("")

        if found.is_multi_site:
            raise CairnError(
                f"This host serves {len(found.sites)} sites and a descriptor names one. "
                f"No descriptor was generated — decide how multiple sites should be handled "
                f"first."
            )

        try:
            rendered = adopt.render(found, environment)
            adopt.validate(rendered)
        except ValueError as exc:
            raise CairnError(
                f"Not enough could be determined to describe this host: {exc}. The findings "
                f"above say what is missing."
            ) from exc

        typer.echo(rendered, nl=False)
        note(f"Review the above, then install it as {descriptor.DESCRIPTOR_PATH}.")
    except CairnError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc


@app.command(
    "systemd-units",
    help="Print the systemd service and timer for `cairn-adopt reconcile`. Installs nothing.",
)
def systemd_units_command(
    interval: Annotated[
        str, typer.Option("--interval", help="How often to poll, as a systemd time span.")
    ] = systemd.DEFAULT_INTERVAL,
    user: Annotated[str, typer.Option("--user", help="The user the service runs as.")] = "root",
) -> None:
    """Print the systemd units for `cairn-adopt reconcile` (BR-CLI-019)."""
    rendered = systemd.units(interval=interval, user=user)

    note("Assumed for this host:")
    for line in rendered.assumptions:
        note(f"  {line}")
    note("")

    typer.echo(rendered.render())

    for line in systemd.install_hint():
        note(line)


@app.command(
    "doctor",
    help="Check that this machine can converge: Docker + Compose, reconcile timer, registry tag.",
)
def doctor_command() -> None:
    """Check that this machine can converge: descriptor, Docker + Compose, registry.

    Reports every check before exiting non-zero on any failure (BR-CLI-007, BR-CLI-012).
    """
    run(lambda: doctor.run_target())


@app.command(
    "setup",
    help=(
        "Provision this machine to converge. Must be run with sudo; see `setup-timer` for "
        "reconcile automation."
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
        typer.Option("--only", help=f"Run one stage: {', '.join(ADOPT_STAGES)}."),
    ] = None,
    workdir: Annotated[
        Path,
        typer.Option("--workdir", help="Directory to record in reported paths."),
    ] = Path.cwd(),  # noqa: B008 - Typer evaluates defaults once, by design
    environment: Annotated[
        str, typer.Option("--environment", help="Name for this environment in the descriptor.")
    ] = "production",
    project: Annotated[
        str | None,
        typer.Option("--project", help="Compose project to adopt and back up."),
    ] = None,
    skip_backup: Annotated[
        bool,
        typer.Option("--skip-backup", help="Do not back up before changing anything."),
    ] = False,
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
    """Provision a target machine (BR-CLI-021, BR-DEPLOY-021).

    Root-gated: exits reporting the shortfall rather than attempting a partial run without
    the privilege its actions require. The descriptor stage calls straight into
    :mod:`cairn.adopt`, in-process (`ADR-046`).
    """
    options = SetupOptions(
        dry_run=dry_run,
        force=force,
        workdir=workdir,
        environment=environment,
        project=project,
        skip_backup=skip_backup,
        skip_disk_free=skip_disk_free,
        admin_group=None if no_admin_group else admin_group,
    )
    runner = Runner(dry_run=dry_run, force=force)
    raise typer.Exit(
        execute(runner, options, ADOPT_STAGE_FUNCS, ADOPT_STAGES, only, program="cairn-adopt")
    )


@app.command(
    "setup-timer",
    help="Install (but do not start) the reconcile-automation timer. Must be run with sudo.",
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
    interval: Annotated[str, typer.Option("--interval", help="Reconcile poll interval.")] = "5min",
) -> None:
    """Install the reconcile-automation timer only (BR-CLI-023, ADR-047).

    Root-gated the same way `setup` is — writing to `/etc/systemd/system` needs it, and
    this command has no preceding `preflight` stage of its own to have already checked.
    """
    options = SetupOptions(dry_run=dry_run, force=force, workdir=workdir, interval=interval)
    runner = Runner(dry_run=dry_run, force=force)
    raise typer.Exit(
        execute(
            runner,
            options,
            ADOPT_TIMER_STAGE_FUNCS,
            TIMER_STAGES,
            None,
            program="cairn-adopt",
            verb="setup-timer",
        )
    )


def main() -> None:
    """Console-script entry point for the ``cairn-adopt`` command."""
    app()


if __name__ == "__main__":
    main()
