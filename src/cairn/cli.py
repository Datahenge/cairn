"""cairn command-line interface — a single Typer application (BR-CLI-001).

Subcommands are added per requirement area. This module currently wires the ``vendor``
group (BR-CLI-006), ``doctor`` (BR-CLI-007), and ``build`` (BR-CLI-002); further commands
(``push``, ``retag``, …) are added as their modules land.

``build --push`` (`BR-CLI-002`) is deliberately absent until the push module exists — an
accepted flag that errors is worse than one that is not offered yet.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, build, config, doctor, resolve, vendor
from .errors import CairnError
from .project import find_project_root

app = typer.Typer(
    name="cairn",
    help="Reproducible ERPNext image builds and pull-based deploys.",
    no_args_is_help=True,
    add_completion=False,
)

vendor_app = typer.Typer(
    help="Manage the vendored, pinned frappe_docker tree (wraps ventwig).",
    no_args_is_help=True,
)
app.add_typer(vendor_app, name="vendor")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"cairn {__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=_version_callback,
            is_eager=True,
            help="Show the cairn version and exit.",
        ),
    ] = False,
) -> None:
    """cairn — reproducible ERPNext image builds and pull-based deploys."""


def _run_in_project(action: Callable[[Path], int]) -> None:
    """Resolve the project root, run ``action(root)``, and exit with its return code.

    A :class:`CairnError` is rendered as a clean, actionable message with exit code 2
    rather than a traceback (BR-CLI-015).
    """
    try:
        root = find_project_root()
        code = action(root)
    except CairnError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    raise typer.Exit(code)


@vendor_app.command("status")
def vendor_status(
    source: Annotated[
        str | None, typer.Argument(help="Check one source by name; default: all.")
    ] = None,
) -> None:
    """Report whether the vendored frappe_docker tree matches its lock (BR-CLI-006)."""
    _run_in_project(lambda root: vendor.status(root, source))


@vendor_app.command("sync")
def vendor_sync(
    source: Annotated[
        str | None, typer.Argument(help="Sync one source by name; default: all.")
    ] = None,
) -> None:
    """Re-materialize the vendored tree from its pinned ref (BR-CLI-006, BR-VEND-009)."""
    _run_in_project(lambda root: vendor.sync(root, source))


@app.command("build")
def build_command(
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml; default: discovered upward from cwd."),
    ] = None,
    no_cache: Annotated[
        bool, typer.Option("--no-cache", help="Ignore the layer cache (rarely needed).")
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run", help="Show what would be built, and build nothing."),
    ] = False,
) -> None:
    """Build the image declared by cairn.toml (BR-CLI-002).

    Default is build-only; publishing is a separate `cairn push` (BR-CLI-002).
    """

    def _action(root: Path) -> int:
        found = config.find_manifest(explicit=manifest_path)
        plan = build.plan(
            root,
            config.load_manifest(found),
            config.load_build_config(found),
            no_cache=no_cache,
        )
        _warn_moving_refs(plan)
        if dry_run:
            typer.echo(plan.render())
            return 0
        build.run(plan)
        for reference in plan.references:
            typer.secho(f"Built {reference}", fg=typer.colors.GREEN)
        return 0

    _run_in_project(_action)


def _warn_moving_refs(plan: build.BuildPlan) -> None:
    """Warn when the manifest pins to a moving branch (BR-BUILD-005).

    The manifest *should* pin to tags; a branch still builds, but the image it produces
    is not reproducible from the manifest alone — only from the recorded commits.
    """
    moving = resolve.moving_refs(plan.resolution)
    if not moving:
        return
    names = ", ".join(f"{ref.name}@{ref.ref}" for ref in moving)
    typer.secho(
        f"Warning: pinned to moving branch(es): {names}. "
        f"Tags are reproducible; branches are not (BR-BUILD-005).",
        fg=typer.colors.YELLOW,
        err=True,
    )


@app.command("doctor")
def doctor_command() -> None:
    """Check that this machine can build: Docker Engine v23+/buildx, vendored tree sound.

    Reports every check before exiting non-zero on any failure (BR-CLI-007, BR-CLI-012).
    """
    _run_in_project(doctor.run)


def run() -> None:
    """Console-script entry point for the ``cairn`` command."""
    app()
