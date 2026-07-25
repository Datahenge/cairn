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
    descriptor,
    doctor,
    engine,
    environments,
    images,
    prune,
    push,
    reconcile,
    registry,
    resolve,
    systemd,
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

    Dimmed, because this is commentary that scrolls past. Anything a person is meant to
    stop and *read* belongs in :func:`_note` instead — dim grey is the first thing to
    disappear under a muted colour scheme.
    """
    typer.secho(message, fg=typer.colors.BRIGHT_BLACK, err=True)
    transcript.record(message)


def _note(message: str) -> None:
    """Report something on stderr that is meant to be read, not skimmed past.

    Timings, digests, and the transcript path are answers to questions the operator
    asked — they travel on stderr with progress, but at full contrast, because dimming
    them defeats the reason they are printed at all.
    """
    typer.secho(message, err=True)
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
    rebuild: Annotated[
        bool,
        typer.Option(
            "--rebuild",
            help="Build again even if these exact inputs were already built.",
        ),
    ] = False,
    no_cache_tag: Annotated[
        bool,
        typer.Option(
            "--no-cache-tag",
            help="Leave the reusable build layers unnamed in the engine's image list.",
        ),
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
            _note(f"Transcript {destination}")
            try:
                return _build(root, found, manifest, build_config, watch, sink=recorder)
            finally:
                # Said a second time on the way out, success or failure: the first
                # mention scrolled past minutes of engine output long ago, and this is
                # where someone goes looking (BR-CLI-016).
                _note(f"Transcript {destination}")

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

        if not rebuild and (held := build.existing_image(plan)):
            _note(f"Image {held}")
            _done(f"Already built {plan.references[0]}")
            _step(
                "  These exact inputs were built before, so there is nothing to do. "
                "Rebuilding would produce an identical image under a new id and leave "
                "this one nameless — pass --rebuild to do it anyway."
            )
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
        _note(f"Image {digest}")

        if not no_cache_tag:
            _tag_cache_stage(plan, watch)

        if push_after:
            with watch.phase("push"):
                for reference in plan.references:
                    _step(f"Pushing {reference}…")
                    push.push(reference, plan.engine_name)
                    _done(f"Pushed {reference}")

        return 0

    _run_in_project(_action)


@app.command(
    "images",
    help=(
        "Show images and what they were built from. With --local, reports this machine's "
        "own images grouped by their build inputs, so superseded builds are visible rather "
        "than nameless. Images cairn did not build are counted but never listed."
    ),
)
def images_command(
    local: Annotated[
        bool,
        typer.Option("--local", help="Report this machine's images instead of the registry."),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable output.")] = False,
) -> None:
    """Report images and their provenance, locally or from the registry (BR-CLI-005).

    Two genuinely different questions. ``--local`` asks what this machine holds and which of
    it is superseded; the default asks what the registry holds and which tags point where —
    read remotely, with nothing pulled.
    """

    def _action(root: Path) -> int:
        found_manifest = config.find_manifest_or_none()
        build_config = config.load_build_config(found_manifest)

        if local:
            engine_name = engine.detect(build_config.engine).name
            held, others = images.inspect_local(engine_name)
            groups = images.group(held)
            typer.echo(images.as_json(groups, others) if as_json else images.render(groups, others))
            return 0

        base = _registry_repository(found_manifest, build_config)
        if not as_json:
            _step(f"Reading {base.base} (one request per tag; nothing is pulled)…")
        remote, others = images.inspect_registry(base)
        grouped = images.group_registry(remote)

        typer.echo(
            images.registry_as_json(base, grouped, others)
            if as_json
            else images.render_registry(base, grouped, others)
        )
        return 0

    _run_in_project(_action)


@app.command(
    "prune",
    help=(
        "Remove superseded images this machine built. Only cairn's own images are ever "
        "considered, only untagged ones are removed, and the newest of each build is kept "
        "— so build-cache layers, which make rebuilds fast, are never touched."
    ),
)
def prune_command(
    keep: Annotated[
        int,
        typer.Option("--keep", min=1, help="Images to keep per set of build inputs."),
    ] = 1,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show what would be removed, and remove nothing.")
    ] = False,
    assume_yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Remove superseded images on the build machine (BR-CLI-018, `ADR-032`)."""

    def _action(root: Path) -> int:
        build_config = config.load_build_config(config.find_manifest_or_none())
        engine_name = engine.detect(build_config.engine).name
        found, others = images.inspect_local(engine_name)
        plan = prune.select(images.group(found), keep)

        typer.echo(prune.render(plan, others))
        if plan.is_empty or dry_run:
            return 0

        if not assume_yes and not typer.confirm("Remove them?", default=False):
            _note("Nothing was removed.")
            return 0

        removed, failures = prune.remove(engine_name, plan.removals)
        for failure in failures:
            typer.secho(f"Could not remove {failure}", fg=typer.colors.YELLOW, err=True)
        _done(
            f"Removed {len(removed)} image(s), reclaiming "
            f"{prune.format_size(sum(image.size for image in removed))}."
        )
        return 1 if failures else 0

    _run_in_project(_action)


def _tag_cache_stage(plan: build.BuildPlan, watch: timing.Stopwatch) -> None:
    """Name the reusable build layers so they are not mistaken for garbage (BR-BUILD-015).

    Reported rather than raised: the image is already built and verified, so failing to
    attach a courtesy name is not a reason to fail the command — but it is a reason to say
    so, since the protection the operator expects is then absent.
    """
    with watch.phase("name build cache"):
        named = build.tag_cache_stage(plan)

    if named:
        _note(f"Cache {named}")
        _step("  Named so it is not mistaken for a stale image; deleting it costs a slow rebuild.")
    elif plan.engine_name == engine.PODMAN:
        _step("  Could not name the reusable build layers; they stay unnamed in image lists.")


def _report_timing(watch: timing.Stopwatch) -> None:
    """Print the per-phase and overall elapsed times (BR-CLI-017).

    At full contrast: this block exists to be read after the fact, which is precisely
    what a dimmed colour defeats.
    """
    _note("Timing")
    for line in watch.summary():
        _note(line)


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


def _registry_repository(
    manifest_path: Path | None, build_config: config.BuildConfig
) -> registry.ImageRef:
    """The repository the registry commands act on, taken from the manifest and build config.

    The tag is a placeholder — every caller replaces it. What matters is the repository, which
    is composed exactly as `cairn build` composes it, so the images read here are the images
    built there.
    """
    if manifest_path is None:
        raise CairnError(
            "No manifest found, so cairn does not know which repository to read. Run this "
            "from a deployment directory, or pass --manifest."
        )
    manifest = config.load_manifest(manifest_path)
    base = build_config.resolve_image_base(manifest.image_name)
    if not build_config.registry and not build_config.image_base:
        raise CairnError(
            "No registry is configured, so images stay local and there is no registry to "
            "read. Set `registry` (and usually `namespace`) in ~/.config/cairn/config.toml "
            "or cairn.local.toml, or use --local."
        )
    return registry.parse_ref(f"{base}:latest")


def _pointer_move(
    name: str,
    *,
    creating: bool,
    latest: bool,
    previous: bool,
    identifier: str | None,
    from_env: str | None,
    manifest_path: Path | None,
    dry_run: bool,
    assume_yes: bool,
) -> int:
    """Create or move an environment pointer — the shared body of ``new-tag`` and ``retag``.

    One function because deploy, promote, and rollback are one operation (`BR-DEPLOY-004`);
    the only difference between the two commands is which pre-existing state is an error.
    """
    selector, source_name = _selector(latest, previous, identifier, from_env)

    found = config.find_manifest(explicit=manifest_path)
    manifest = config.load_manifest(found)
    build_config = config.load_build_config(found)

    environment = environments.require(manifest, build_config, name)
    source_environment = (
        environments.require(manifest, build_config, source_name) if source_name else None
    )

    candidates = None
    if selector in (environments.Selector.LATEST, environments.Selector.PREVIOUS):
        _step(f"Reading {environment.ref.base} to find the image…")
        held, _ = images.inspect_registry(environment.ref)
        candidates = [
            registry.RemoteImage(
                ref=environment.ref.with_tag(image.tags[0]),
                digest=image.digest,
                media_type="",
                size=image.size,
                labels=image.labels,
            )
            for image in held
            if image.tags
        ]

    move = environments.plan_move(
        environment,
        selector=selector,
        identifier=identifier,
        source_environment=source_environment,
        candidates=candidates,
    )
    environments.assert_creating(move) if creating else environments.assert_moving(move)

    typer.echo(move.render())
    if dry_run:
        return 0

    if move.is_noop:
        _done(f"{environment.name} already points at {move.source.digest}")
        return 0

    # The production gate (BR-CLI-010). Asked after the move is fully decided, so the digest
    # in the prompt is the digest that will be deployed.
    if (
        environment.is_production
        and not assume_yes
        and not typer.confirm(f"Move '{environment.name}' to this image?", default=False)
    ):
        _note("The pointer was not moved.")
        return 0

    _step(f"Pointing {environment.ref} at {move.source.digest}…")
    digest = environments.apply(move)
    _done(f"{environment.name} now points at {digest}")
    _step("  The target converges on its next poll; nothing was pulled or rebuilt.")
    return 0


def _selector(
    latest: bool, previous: bool, identifier: str | None, from_env: str | None
) -> tuple[environments.Selector, str | None]:
    """Validate that exactly one selector was given, and return it (`BR-CLI-004`)."""
    chosen = [
        (environments.Selector.LATEST, latest),
        (environments.Selector.PREVIOUS, previous),
        (environments.Selector.IDENTIFIER, identifier is not None),
        (environments.Selector.FROM_ENV, from_env is not None),
    ]
    given = [selector for selector, present in chosen if present]

    if not given:
        raise typer.BadParameter(
            "Choose which image to point at: --latest, --previous, --id <tag>, or --from <env>."
        )
    if len(given) > 1:
        raise typer.BadParameter(
            "Only one of --latest, --previous, --id, and --from may be given — they each "
            "name a different image."
        )
    return given[0], from_env


@app.command(
    "new-tag",
    help=(
        "Create an environment's registry pointer for the first time. The environment must "
        "already be declared in cairn.toml; cairn never invents one. Nothing is rebuilt or "
        "pulled — the pointer is written in the registry and the target converges on its "
        "next poll."
    ),
)
def new_tag_command(
    environment: Annotated[str, typer.Argument(help="The declared environment to point.")],
    latest: Annotated[bool, typer.Option("--latest", help="The newest image cairn built.")] = False,
    previous: Annotated[
        bool, typer.Option("--previous", help="The image before the one running now.")
    ] = False,
    identifier: Annotated[
        str | None, typer.Option("--id", help="A specific tag already in the registry.")
    ] = None,
    from_env: Annotated[
        str | None, typer.Option("--from", help="Whatever another environment runs now.")
    ] = None,
    manifest_path: Annotated[
        Path | None, typer.Option("--manifest", help="Path to cairn.toml.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the move, and make none.")
    ] = False,
    assume_yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Create an environment's pointer (BR-CLI-004, BR-CLI-009, BR-DEPLOY-004)."""
    _run_in_project(
        lambda root: _pointer_move(
            environment,
            creating=True,
            latest=latest,
            previous=previous,
            identifier=identifier,
            from_env=from_env,
            manifest_path=manifest_path,
            dry_run=dry_run,
            assume_yes=assume_yes,
        )
    )


@app.command(
    "retag",
    help=(
        "Move an environment's pointer to another image. Deploy, promote, and rollback are "
        "all this one command — nothing is rebuilt and nothing is pulled. Moving production "
        "asks first."
    ),
)
def retag_command(
    environment: Annotated[str, typer.Argument(help="The declared environment to move.")],
    latest: Annotated[bool, typer.Option("--latest", help="The newest image cairn built.")] = False,
    previous: Annotated[
        bool, typer.Option("--previous", help="The image before the one running now.")
    ] = False,
    identifier: Annotated[
        str | None, typer.Option("--id", help="A specific tag already in the registry.")
    ] = None,
    from_env: Annotated[
        str | None, typer.Option("--from", help="Whatever another environment runs now.")
    ] = None,
    manifest_path: Annotated[
        Path | None, typer.Option("--manifest", help="Path to cairn.toml.")
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the move, and make none.")
    ] = False,
    assume_yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Move an environment's pointer (BR-CLI-004, BR-CLI-010, BR-DEPLOY-004)."""
    _run_in_project(
        lambda root: _pointer_move(
            environment,
            creating=False,
            latest=latest,
            previous=previous,
            identifier=identifier,
            from_env=from_env,
            manifest_path=manifest_path,
            dry_run=dry_run,
            assume_yes=assume_yes,
        )
    )


@app.command(
    "retire",
    help=(
        "Decommission an environment from cairn. No image is touched and no registry tag is "
        "deleted — this reports what to remove from cairn.toml, and what will remain behind."
    ),
)
def retire_command(
    environment: Annotated[str, typer.Argument(help="The declared environment to retire.")],
    manifest_path: Annotated[
        Path | None, typer.Option("--manifest", help="Path to cairn.toml.")
    ] = None,
) -> None:
    """Decommission an environment at cairn's layer only (BR-CLI-009)."""

    def _action(root: Path) -> int:
        found = config.find_manifest(explicit=manifest_path)
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
        retiring = environments.retire(manifest, build_config, environment)

        typer.echo(
            "\n".join(
                [
                    f"Retire '{retiring.name}' by removing this line from {found}:",
                    f'  [cairn.environments]  {retiring.name} = "{retiring.tag}"',
                ]
            )
        )
        typer.secho(
            f"Warning: the registry tag '{retiring.tag}' will still exist and still resolve. "
            f"cairn does not delete it — a registry version can carry several tags, so "
            f"deleting it could destroy an image another environment still points at. Any "
            f"target still holding this descriptor will also keep converging to it; remove "
            f"its timer first.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return 0

    _run_in_project(_action)


@app.command(
    "reconcile",
    help=(
        "Converge this host to the image its environment's tag points at. Idempotent and "
        "safe to run repeatedly: with nothing changed it does nothing. Reads "
        "/etc/cairn/environment.toml, and never rolls back on failure — it stops and reports."
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
        _step(f"Environment {environment.environment} — site {environment.site}")

        with watch.phase("converge"):
            outcome = reconcile.run(environment, dry_run=dry_run, report=_step)

        if outcome.changed:
            _done(outcome.detail)
        else:
            _note(outcome.detail)
        _report_timing(watch)
        raise typer.Exit(0)
    except CairnError as exc:
        typer.secho(f"Error: {exc}", fg=typer.colors.RED, err=True)
        _report_timing(watch)
        raise typer.Exit(2) from exc
    except KeyboardInterrupt:
        typer.secho("Interrupted.", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(130) from None


@app.command(
    "systemd-units",
    help=(
        "Print a systemd service and timer that run `cairn reconcile` on this host. cairn "
        "prints them and installs nothing — review them, then install them yourself."
    ),
)
def systemd_units_command(
    interval: Annotated[
        str, typer.Option("--interval", help="How often to poll, as a systemd time span.")
    ] = systemd.DEFAULT_INTERVAL,
    user: Annotated[str, typer.Option("--user", help="The user the service runs as.")] = "root",
) -> None:
    """Print the systemd units for `cairn reconcile` (BR-CLI-019)."""
    rendered = systemd.units(interval=interval, user=user)

    _note("Assumed for this host:")
    for line in rendered.assumptions:
        _note(f"  {line}")
    _note("")

    typer.echo(rendered.render())

    for line in systemd.install_hint():
        _note(line)


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
