"""cairn command-line interface — a single Typer application (BR-CLI-001).

Subcommands are added per requirement area. This module currently wires the ``vendor``
group (BR-CLI-006); further groups (``build``, ``push``, ``retag``, …) are added as their
modules land.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from . import __version__, vendor
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


def run() -> None:
    """Console-script entry point for the ``cairn`` command."""
    app()
