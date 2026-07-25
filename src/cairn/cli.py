"""cairn command-line interface — a single Typer application (BR-CLI-001).

Subcommands are added per requirement area. This module currently wires the ``vendor``
group (BR-CLI-006), ``doctor`` (BR-CLI-007), ``build`` (BR-CLI-002), and ``push``
(BR-CLI-003); further commands (``new-tag``, ``retag``, ``images``, ``reconcile``) are
added as their modules land.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from . import (
    __version__,
    build,
    config,
    doctor,
    engine,
    push,
    resolve,
    timing,
    transcript,
    vendor,
)
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


def _step(message: str) -> None:
    """Report progress on stderr, keeping stdout clean for a command's actual result.

    Long operations must not look like nothing is happening (BR-CLI-011: nothing
    consequential is silent), and stderr is the right channel because it does not
    pollute output a caller may be parsing (BR-CLI-013). Progress is mirrored into the
    active transcript, if any, so the file records the whole run and not merely the
    engine's share of it (BR-CLI-016).
    """
    typer.secho(message, fg=typer.colors.BRIGHT_BLACK, err=True)
    transcript.record(message)


def _done(message: str) -> None:
    """Report a completed action on stdout — the command's actual result — and record it.

    stdout rather than stderr, per `_step`: progress is commentary, this is the outcome.
    """
    typer.secho(message, fg=typer.colors.GREEN)
    transcript.record(message)


def _run_in_project(action: Callable[[Path], int]) -> None:
    """Resolve the project root, run ``action(root)``, and exit with its return code.

    A :class:`CairnError` is rendered as a clean, actionable message with exit code 2
    rather than a traceback (BR-CLI-015). Anything else is re-raised with a note naming
    it as unexpected, so an unhandled failure is never mistaken for silent success.
    """
    try:
        root = find_project_root()
        code = action(root)
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


@vendor_app.command(
    "status",
    help="Report whether the vendored frappe_docker tree still matches its recorded lock.",
)
def vendor_status(
    source: Annotated[
        str | None, typer.Argument(help="Check one source by name; default: all.")
    ] = None,
) -> None:
    """Report whether the vendored frappe_docker tree matches its lock (BR-CLI-006)."""
    _run_in_project(lambda root: vendor.status(root, source))


@vendor_app.command(
    "sync",
    help=(
        "Re-materialize the vendored frappe_docker tree from its pinned ref. Upgrading the "
        "pin is a deliberate, reviewable act: bump the ref, sync, review, commit."
    ),
)
def vendor_sync(
    source: Annotated[
        str | None, typer.Argument(help="Sync one source by name; default: all.")
    ] = None,
) -> None:
    """Re-materialize the vendored tree from its pinned ref (BR-CLI-006, BR-VEND-009)."""
    _run_in_project(lambda root: vendor.sync(root, source))


@app.command(
    "build",
    help=(
        "Build the custom ERPNext image declared by cairn.toml. Resolves every app ref to "
        "a commit, tags the result immutably, and stamps provenance onto the image. "
        "Build-only by default; --push also uploads."
    ),
)
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
    push_after: Annotated[
        bool, typer.Option("--push", help="Also upload the built image to the registry.")
    ] = False,
    transcript_path: Annotated[
        Path | None,
        typer.Option(
            "--transcript",
            help="Write the build output to this file, in addition to the terminal.",
        ),
    ] = None,
    no_transcript: Annotated[
        bool,
        typer.Option("--no-transcript", help="Do not save the build output to a file."),
    ] = False,
) -> None:
    """Build the image declared by cairn.toml (BR-CLI-002, BR-CLI-016, BR-CLI-017).

    Default is **build-only**; `--push` also uploads, and is checked for a configured
    registry up front so a long build cannot succeed only to fail at the last step.

    At a terminal the whole run is also saved to a transcript, because nothing else is
    keeping it (`ADR-031`); under CI or systemd it is not, because something already is.
    """
    if transcript_path is not None and no_transcript:
        raise typer.BadParameter("--transcript and --no-transcript contradict each other.")

    def _action(root: Path) -> int:
        watch = timing.Stopwatch()
        found = config.find_manifest(explicit=manifest_path)
        build_config = config.load_build_config(found)
        manifest = config.load_manifest(found)

        keep = not dry_run and transcript.wanted(explicit=transcript_path, disabled=no_transcript)
        if not keep:
            return _build(root, found, manifest, build_config, watch)

        destination = transcript_path or transcript.path_for(
            transcript.resolve_dir(build_config.transcript_dir), manifest.image_name
        )
        with transcript.recording(destination) as recorder:
            _step(f"Transcript {destination}")
            try:
                return _build(root, found, manifest, build_config, watch, sink=recorder)
            finally:
                # Said a second time on the way out, success or failure: the first
                # mention scrolled past minutes of engine output long ago, and this is
                # where someone goes looking (BR-CLI-016).
                _step(f"Transcript {destination}")

    def _build(
        root: Path,
        found: Path,
        manifest: config.Manifest,
        build_config: config.BuildConfig,
        watch: timing.Stopwatch,
        *,
        sink: transcript.Transcript | None = None,
    ) -> int:
        try:
            return _steps(root, found, manifest, build_config, watch, sink)
        finally:
            # In a finally, because "it failed after nine minutes" is at least as worth
            # knowing as how long a success took (BR-CLI-017).
            if not dry_run:
                _report_timing(watch)

    def _steps(
        root: Path,
        found: Path,
        manifest: config.Manifest,
        build_config: config.BuildConfig,
        watch: timing.Stopwatch,
        sink: transcript.Transcript | None,
    ) -> int:
        _step(f"Manifest {found}")
        if push_after:
            push.assert_registry_configured(build_config)

        _step("Checking vendored tree and resolving refs (contacts each app's remote)…")
        with watch.phase("checks + ref resolution"):
            plan = build.plan(
                root,
                manifest,
                build_config,
                no_cache=no_cache,
                plain_progress=sink is not None,
            )
        for ref in plan.resolution.all_refs:
            _step(f"  {ref.name:<12} {ref.ref:<14} {ref.kind.value:<7} {ref.short_commit}")
        _warn_moving_refs(plan)

        if dry_run:
            typer.echo(plan.render())
            return 0

        _step(f"Building {plan.references[0]}")
        _step(
            f"  {plan.engine_name}, {len(plan.build_args)} build args, "
            f"{len(plan.labels)} labels, apps.json as a build secret "
            f"— `--dry-run` prints the full command. This takes several minutes."
        )
        with watch.phase("image build"):
            build.run(plan, sink)

        with watch.phase("verify image"):
            digest = build.assert_image_exists(plan)
        for reference in plan.references:
            _done(f"Built {reference}")
        _step(f"Image {digest}")

        if push_after:
            with watch.phase("push"):
                for reference in plan.references:
                    _step(f"Pushing {reference}…")
                    push.push(reference, plan.engine_name)
                    _done(f"Pushed {reference}")

        return 0

    _run_in_project(_action)


def _report_timing(watch: timing.Stopwatch) -> None:
    """Print the per-phase and overall elapsed times (BR-CLI-017)."""
    _step("Timing")
    for line in watch.summary():
        _step(line)


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
        f"Warning: pinned to moving branch(es): {names}. Tags are reproducible; branches are not.",
        fg=typer.colors.YELLOW,
        err=True,
    )


@app.command(
    "push",
    help=(
        "Upload a built image to the configured registry. Without --id, the manifest's "
        "refs are re-resolved so the tags pushed are exactly those `cairn build` would "
        "produce. Authentication is your container engine's: run `docker login` or "
        "`podman login` first — cairn stores no credentials."
    ),
)
def push_command(
    identifier: Annotated[
        str | None,
        typer.Option("--id", help="Push this tag; default: the current manifest's tags."),
    ] = None,
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml; default: discovered upward from cwd."),
    ] = None,
) -> None:
    """Upload a built image to the configured registry (BR-CLI-003).

    Without `--id`, the manifest's refs are re-resolved so the tags pushed are exactly
    those `cairn build` would produce for the current inputs.
    """

    def _action(root: Path) -> int:
        found = config.find_manifest(explicit=manifest_path)
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
        push.assert_registry_configured(build_config)

        engine_name = engine.detect(build_config.engine).name
        if identifier:
            targets: tuple[str, ...] = (push.reference(manifest, build_config, identifier),)
        else:
            targets = build.plan(root, manifest, build_config).references

        for target in targets:
            push.push(target, engine_name)
            typer.secho(f"Pushed {target}", fg=typer.colors.GREEN)
        return 0

    _run_in_project(_action)


@app.command(
    "doctor",
    help=(
        "Check that this machine can build: a usable container engine (Docker v23+ or "
        "podman v4+), git, a sound vendored tree, and valid configuration. Reports every "
        "check, then exits non-zero if any failed."
    ),
)
def doctor_command() -> None:
    """Check that this machine can build: Docker Engine v23+/buildx, vendored tree sound.

    Reports every check before exiting non-zero on any failure (BR-CLI-007, BR-CLI-012).
    """
    _run_in_project(doctor.run)


def run() -> None:
    """Console-script entry point for the ``cairn`` command."""
    app()
