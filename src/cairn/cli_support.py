"""Output/exit-code plumbing shared by `cairn-build` and `cairn-adopt` (`BR-CLI-021` group D).

Extracted from the single-binary `cli.py` when it split into two entry points (`ADR-046`):
both CLIs report progress and errors the same way, so the convention lives once, here,
rather than twice.
"""

from __future__ import annotations

from collections.abc import Callable

import typer

from . import timing, transcript
from .errors import CairnError


def step(message: str) -> None:
    """Report progress on stderr, keeping stdout clean for a command's actual result.

    Long operations must not look like nothing is happening (BR-CLI-011: nothing
    consequential is silent), and stderr is the right channel because it does not
    pollute output a caller may be parsing (BR-CLI-013). Progress is mirrored into the
    active transcript, if any, so the file records the whole run and not merely the
    engine's share of it (BR-CLI-016).

    Dimmed, because this is commentary that scrolls past. Anything a person is meant to
    stop and *read* belongs in :func:`note` instead — dim grey is the first thing to
    disappear under a muted colour scheme.
    """
    typer.secho(message, fg=typer.colors.BRIGHT_BLACK, err=True)
    transcript.record(message)


def note(message: str) -> None:
    """Report something on stderr that is meant to be read, not skimmed past.

    Timings, digests, and the transcript path are answers to questions the operator
    asked — they travel on stderr with progress, but at full contrast, because dimming
    them defeats the reason they are printed at all.
    """
    typer.secho(message, err=True)
    transcript.record(message)


def done(message: str) -> None:
    """Report a completed action on stdout — the command's actual result — and record it.

    stdout rather than stderr, per `step`: progress is commentary, this is the outcome.
    """
    typer.secho(message, fg=typer.colors.GREEN)
    transcript.record(message)


def run(action: Callable[[], int]) -> None:
    """Run *action*, and exit with its return code.

    A :class:`CairnError` is rendered as a clean, actionable message with exit code 2
    rather than a traceback (BR-CLI-015). Anything else is re-raised with a note naming
    it as unexpected, so an unhandled failure is never mistaken for silent success.
    """
    try:
        code = action()
    except CairnError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2) from exc
    except KeyboardInterrupt:
        typer.secho("Interrupted.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(130) from None
    except Exception as exc:
        typer.secho(
            f"Internal error ({type(exc).__name__}): {exc}\n"
            f"This is a bug in cairn; the traceback follows.",
            fg=typer.colors.RED,
            err=True,
        )
        raise
    raise typer.Exit(code)


def report_timing(watch: timing.Stopwatch) -> None:
    """Print the per-phase and overall elapsed times (BR-CLI-017).

    At full contrast: this block exists to be read after the fact, which is precisely
    what a dimmed colour defeats.
    """
    note("Timing")
    for line in watch.summary():
        note(line)


def version_callback(program: str, package_version: str) -> Callable[[bool], None]:
    """Build a `--version` callback that prints *program*'s own name, not the other CLI's."""

    def _callback(value: bool) -> None:
        if value:
            typer.echo(f"{program} {package_version}")
            raise typer.Exit()

    return _callback
