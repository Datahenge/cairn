"""`cairn-build` — the build/control CLI (`BR-CLI-001`, group A of `BR-CLI`).

Builds images, moves environment pointers, and provisions a build machine. Never touches a
running deployment — that is `cairn-adopt`'s job (`ADR-046`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from . import (
    __version__,
    build,
    config,
    doctor,
    engine,
    environments,
    images,
    prune,
    push,
    registry,
    resolve,
    timing,
    transcript,
)
from .cli_support import done, note, report_timing, run, step, version_callback
from .errors import CairnError
from .provision import (
    BUILD_STAGE_FUNCS,
    BUILD_STAGES,
    BUILD_TIMER_STAGE_FUNCS,
    TIMER_STAGES,
    Runner,
    SetupOptions,
    execute,
)

app = typer.Typer(
    name="cairn-build",
    help="Build ERPNext images and move environment pointers.",
    no_args_is_help=True,
    add_completion=False,
)


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            callback=version_callback("cairn-build", __version__),
            is_eager=True,
            help="Show the cairn-build version and exit.",
        ),
    ] = False,
) -> None:
    """cairn-build — reproducible ERPNext image builds and registry pointer moves."""


@app.command(
    "build",
    help=(
        "Build the ERPNext image declared by cairn.toml. Build-only by default; --push "
        "also uploads."
    ),
)
def build_command(
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
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
    assign_tag: Annotated[
        bool,
        typer.Option(
            "--assign-tag",
            help="Also point this manifest's declared environment at the pushed image.",
        ),
    ] = False,
    assume_yes: Annotated[
        bool, typer.Option("--yes", help="Do not ask for confirmation before --assign-tag.")
    ] = False,
) -> None:
    """Build the image declared by cairn.toml (BR-CLI-002, BR-CLI-002a, BR-CLI-016, BR-CLI-017).

    Default is **build-only**; `--push` also uploads, and is checked for a configured
    registry up front so a long build cannot succeed only to fail at the last step.
    `--assign-tag` additionally points this manifest's declared environment at whatever image
    resulted — freshly built or found already published — reusing the digest this command
    already resolved rather than re-checking from scratch (`ADR-052`).

    At a terminal the whole run is also saved to a transcript, because nothing else is
    keeping it (`ADR-031`); under CI or systemd it is not, because something already is.
    """
    if transcript_path is not None and no_transcript:
        raise typer.BadParameter("--transcript and --no-transcript contradict each other.")
    if assign_tag and not push_after:
        raise typer.BadParameter(
            "--assign-tag requires --push — there is nothing to retag until the image is "
            "pushed."
        )

    def _action() -> int:
        watch = timing.Stopwatch()
        found = config.find_manifest(explicit=manifest_path)
        build_config = config.load_build_config(found)
        manifest = config.load_manifest(found)

        keep = not dry_run and transcript.wanted(explicit=transcript_path, disabled=no_transcript)
        if not keep:
            return _build(found, manifest, build_config, watch)

        destination = transcript_path or transcript.path_for(
            transcript.resolve_dir(build_config.transcript_dir), manifest.image_name
        )
        with transcript.recording(destination) as recorder:
            note(f"Transcript {destination}")
            try:
                return _build(found, manifest, build_config, watch, sink=recorder)
            finally:
                # Said a second time on the way out, success or failure: the first
                # mention scrolled past minutes of engine output long ago, and this is
                # where someone goes looking (BR-CLI-016).
                note(f"Transcript {destination}")

    def _build(
        found: Path,
        manifest: config.Manifest,
        build_config: config.BuildConfig,
        watch: timing.Stopwatch,
        *,
        sink: transcript.Transcript | None = None,
    ) -> int:
        try:
            return _steps(found, manifest, build_config, watch, sink)
        finally:
            # In a finally, because "it failed after nine minutes" is at least as worth
            # knowing as how long a success took (BR-CLI-017).
            if not dry_run:
                report_timing(watch)

    def _steps(
        found: Path,
        manifest: config.Manifest,
        build_config: config.BuildConfig,
        watch: timing.Stopwatch,
        sink: transcript.Transcript | None,
    ) -> int:
        step(f"Manifest {found}")
        if push_after:
            push.assert_registry_configured(build_config)

        step("Checking build inputs and resolving refs (contacts each app's remote)…")
        with watch.phase("checks + ref resolution"):
            plan = build.plan(
                manifest,
                build_config,
                no_cache=no_cache,
                plain_progress=sink is not None,
            )
        if not dry_run:
            # --dry-run skips this: plan.render() (BR-BUILD-012)'s "resolved inputs:"
            # section below shows the same lines already, and repeating them first is
            # just noise.
            for ref in plan.resolution.all_refs:
                step(f"  {ref.name:<12} {ref.ref:<14} {ref.kind.value:<7} {ref.short_commit}")
        _warn_moving_refs(plan)

        if dry_run:
            typer.echo(plan.render())
            return 0

        digest: str | None = None

        if not rebuild and (held := build.existing_image(plan)):
            note(f"Image {held}")
            done(f"Already built {plan.references[0]}")
            step(
                "  These exact inputs were built before, so there is nothing to do. "
                "Rebuilding would produce an identical image under a new id and leave "
                "this one nameless — pass --rebuild to do it anyway."
            )
            digest = held
        elif not rebuild and build_config.registry and (
            remote := build.existing_in_registry(plan, build_config)
        ):
            note(f"Image {remote.digest}")
            done(f"Already published to {build_config.registry}: {plan.references[0]}")
            step("  Found in the registry; nothing to build.")
            digest = remote.digest
        else:
            step(f"Building {plan.references[0]}")
            step(
                f"  {plan.engine_name}, {len(plan.build_args)} build args, "
                f"{len(plan.labels)} labels, apps.json as a build secret "
                f"— `--dry-run` prints the full command. This takes several minutes."
            )
            with watch.phase("image build"):
                build.run(plan, sink)

            with watch.phase("verify image"):
                digest = build.assert_image_exists(plan)
            for reference in plan.references:
                done(f"Built {reference}")
            note(f"Image {digest}")

            if not no_cache_tag:
                _tag_cache_stage(plan, watch)

            if push_after:
                with watch.phase("push"):
                    for reference in plan.push_references:
                        step(f"Pushing {reference}…")
                        push.push(reference, plan.engine_name)
                        done(f"Pushed {reference}")
                    push.release_ownership(plan.image_base, plan.engine_name)

        if assign_tag:
            environment = environments.require(manifest, build_config)
            source_ref = registry.parse_ref(plan.references[0])
            assignment = environments.check_known(environment, source_ref, digest)
            return _apply_assignment(assignment, assume_yes=assume_yes)

        return 0

    run(_action)


@app.command(
    "images",
    help=(
        "Show images and what they were built from. Reads the registry by default; "
        "--local reads this machine instead."
    ),
)
def images_command(
    local: Annotated[
        bool,
        typer.Option("--local", help="Report this machine's images instead of the registry."),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Emit machine-readable output.")] = False,
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
) -> None:
    """Report images and their provenance, locally or from the registry (BR-CLI-005).

    Two genuinely different questions. ``--local`` asks what this machine holds and which of
    it is superseded; the default asks what the registry holds and which tags point where —
    read remotely, with nothing pulled.
    """

    def _action() -> int:
        found_manifest = config.find_manifest_or_none(explicit=manifest_path)
        build_config = config.load_build_config(found_manifest)

        if local:
            engine_name = engine.detect(build_config.engine).name
            held, others = images.inspect_local(engine_name)
            groups = images.group(held)
            typer.echo(images.as_json(groups, others) if as_json else images.render(groups, others))
            return 0

        base = _registry_repository(found_manifest, build_config)
        if not as_json:
            step(f"Reading {base.base} (one request per tag; nothing is pulled)…")
        remote, others = images.inspect_registry(base)
        grouped = images.group_registry(remote)

        typer.echo(
            images.registry_as_json(base, grouped, others)
            if as_json
            else images.render_registry(base, grouped, others)
        )
        return 0

    run(_action)


@app.command(
    "prune",
    help=(
        "Remove superseded images this machine built. Only untagged images are removed; "
        "the newest of each build is kept."
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
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
) -> None:
    """Remove superseded images on the build machine (BR-CLI-018, `ADR-032`)."""

    def _action() -> int:
        build_config = config.load_build_config(
            config.find_manifest_or_none(explicit=manifest_path)
        )
        engine_name = engine.detect(build_config.engine).name
        found, others = images.inspect_local(engine_name)
        plan = prune.select(images.group(found), keep)

        typer.echo(prune.render(plan, others))
        if plan.is_empty or dry_run:
            return 0

        if not assume_yes and not typer.confirm("Remove them?", default=False):
            note("Nothing was removed.")
            return 0

        removed, failures = prune.remove(engine_name, plan.removals)
        for failure in failures:
            typer.secho(f"Could not remove {failure}", fg=typer.colors.YELLOW, err=True)
        done(
            f"Removed {len(removed)} image(s), reclaiming "
            f"{prune.format_size(sum(image.size for image in removed))}."
        )
        return 1 if failures else 0

    run(_action)


def _tag_cache_stage(plan: build.BuildPlan, watch: timing.Stopwatch) -> None:
    """Name the reusable build layers so they are not mistaken for garbage (BR-BUILD-015).

    Reported rather than raised: the image is already built and verified, so failing to
    attach a courtesy name is not a reason to fail the command — but it is a reason to say
    so, since the protection the operator expects is then absent.
    """
    with watch.phase("name build cache"):
        named = build.tag_cache_stage(plan)

    if named:
        note(f"Cache {named}")
        step("  Named so it is not mistaken for a stale image; deleting it costs a slow rebuild.")
    elif plan.engine_name == engine.PODMAN:
        step("  Could not name the reusable build layers; they stay unnamed in image lists.")


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
        "Upload a built image to the configured registry. Requires `docker login` or "
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
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
) -> None:
    """Upload a built image to the configured registry (BR-CLI-003).

    Without `--id`, the manifest's refs are re-resolved so the tags pushed are exactly
    those `cairn-build build` would produce for the current inputs.
    """

    def _action() -> int:
        found = config.find_manifest(explicit=manifest_path)
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
        push.assert_registry_configured(build_config)

        engine_name = engine.detect(build_config.engine).name

        # `--id` names an explicit, arbitrary tag — not necessarily this manifest's current
        # build — so it MUST NOT touch the ownership marker (`BR-BUILD-018`).
        if identifier:
            target = push.reference(manifest, build_config, identifier)
            push.push(target, engine_name)
            typer.secho(f"Pushed {target}", fg=typer.colors.GREEN)
            return 0

        plan = build.plan(manifest, build_config)
        for target in plan.push_references:
            push.push(target, engine_name)
            typer.secho(f"Pushed {target}", fg=typer.colors.GREEN)
        push.release_ownership(plan.image_base, engine_name)
        return 0

    run(_action)


def _registry_repository(
    manifest_path: Path | None, build_config: config.BuildConfig
) -> registry.ImageRef:
    """The repository the registry commands act on, taken from the manifest and build config.

    The tag is a placeholder — every caller replaces it. What matters is the repository, which
    is composed exactly as `cairn-build build` composes it, so the images read here are the
    images built there.
    """
    if manifest_path is None:
        raise CairnError(
            "No manifest given, so cairn does not know which repository to read. Pass "
            "--manifest, set $CAIRN_MANIFEST, or use --local."
        )
    manifest = config.load_manifest(manifest_path)
    base = build_config.resolve_image_base(manifest.image_name)
    if not build_config.registry:
        raise CairnError(
            "No registry is configured, so images stay local and there is no registry to "
            "read. Set `registry` (and usually `namespace`) in /etc/cairn/builder.toml, "
            "or set $CAIRN_REGISTRY (and usually $CAIRN_NAMESPACE), or use --local."
        )
    return registry.parse_ref(f"{base}:latest")


def _apply_assignment(assignment: environments.Assignment, *, assume_yes: bool) -> int:
    """Report a checked :class:`~cairn.environments.Assignment`, and apply it if proven
    (`ADR-052`) — the shared body of ``assign-tag`` and ``build --assign-tag``.
    """
    typer.echo(assignment.render())
    if not assignment.found:
        return 0

    if assignment.is_noop:
        done(f"{assignment.environment.name} already points at {assignment.digest}")
        return 0

    # The production gate (BR-CLI-010), asked after the assignment is fully decided, so the
    # digest in the prompt is the digest that will be deployed. Applies whether this creates
    # production's pointer for the first time or moves it — both are equally consequential.
    creating = assignment.previous_digest is None
    verb = "Create" if creating else "Move"
    if (
        assignment.environment.is_production
        and not assume_yes
        and not typer.confirm(
            f"{verb} '{assignment.environment.name}' to this image?", default=False
        )
    ):
        note("The pointer was not moved.")
        return 0

    step(f"Pointing {assignment.environment.ref} at {assignment.digest}…")
    digest = environments.apply(assignment)
    if creating:
        done(f"{assignment.environment.name} did not exist — created it, now pointing at {digest}")
    else:
        done(f"{assignment.environment.name} moved to {digest}")
    step("  The target converges on its next poll; nothing was pulled or rebuilt.")
    return 0


@app.command(
    "assign-tag",
    help=(
        "Point this manifest's declared environment at a matching image already in the "
        "registry, if one exists. Never builds."
    ),
)
def assign_tag_command(
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show the result, and change nothing.")
    ] = False,
    assume_yes: Annotated[bool, typer.Option("--yes", help="Do not ask for confirmation.")] = False,
) -> None:
    """Resolve this manifest's own refs and retag onto a matching registry image, if one
    exists (BR-CLI-004, BR-CLI-009, BR-CLI-010, BR-DEPLOY-004, ADR-052).
    """

    def _action() -> int:
        found = config.find_manifest(explicit=manifest_path)
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)

        step("Resolving refs and checking the registry (contacts each app's remote)…")
        assignment = environments.check(manifest, build_config)

        if dry_run:
            typer.echo(assignment.render())
            return 0

        return _apply_assignment(assignment, assume_yes=assume_yes)

    run(_action)


@app.command(
    "retire",
    help="Decommission this manifest's environment from cairn. Touches no image or registry tag.",
)
def retire_command(
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
) -> None:
    """Decommission this manifest's environment at cairn's layer only (BR-CLI-009)."""

    def _action() -> int:
        found = config.find_manifest(explicit=manifest_path)
        manifest = config.load_manifest(found)
        build_config = config.load_build_config(found)
        retiring = environments.retire(manifest, build_config)

        typer.echo(
            "\n".join(
                [
                    f"Retire '{retiring.name}' by removing this line from {found}:",
                    f'  environment = "{retiring.name}"',
                ]
            )
        )
        typer.secho(
            f"Warning: the registry tag '{retiring.name}' will still exist and still resolve. "
            f"cairn does not delete it — a registry version can carry several tags, so "
            f"deleting it could destroy an image another environment still points at. Any "
            f"target still holding this descriptor will also keep converging to it; remove "
            f"its timer first.",
            fg=typer.colors.YELLOW,
            err=True,
        )
        return 0

    run(_action)


@app.command(
    "doctor",
    help="Check that this machine can build: container engine, git, build inputs, and config.",
)
def doctor_command(
    manifest_path: Annotated[
        Path | None,
        typer.Option("--manifest", help="Path to cairn.toml. Default: $CAIRN_MANIFEST."),
    ] = None,
) -> None:
    """Check that this machine can build: Docker Engine v23+/buildx, build inputs present.

    Reports every check before exiting non-zero on any failure (BR-CLI-007, BR-CLI-012).
    A missing manifest only warns here (`doctor` legitimately runs before one exists).
    """
    run(lambda: doctor.run_build(manifest_path=manifest_path))


@app.command(
    "setup",
    help=(
        "Provision this machine to build. Must be run with sudo; see `setup-timer` for "
        "build automation."
    ),
)
def setup_command(
    client: Annotated[
        str,
        typer.Option("--client", help="Client name; provisions /srv/cairn/<name>/."),
    ],
    environment: Annotated[
        str,
        typer.Option(
            "--environment", help="Environment this manifest is for; scaffolds cairn_<name>.toml."
        ),
    ],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Print every action, and change nothing.")
    ] = False,
    force: Annotated[
        bool, typer.Option("--force", help="Replace existing files (the old ones are kept).")
    ] = False,
    only: Annotated[
        str | None,
        typer.Option("--only", help=f"Run one stage: {', '.join(BUILD_STAGES)}."),
    ] = None,
    workdir: Annotated[
        Path,
        typer.Option("--workdir", help="Directory to record in reported paths."),
    ] = Path.cwd(),  # noqa: B008 - Typer evaluates defaults once, by design
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
    """Provision a build machine (BR-CLI-021, BR-CLI-022, BR-DEPLOY-021).

    Root-gated: exits reporting the shortfall rather than attempting a partial run without
    the privilege its actions require. Build automation lives in `setup-timer`, not here.
    """
    options = SetupOptions(
        dry_run=dry_run,
        force=force,
        workdir=workdir,
        skip_disk_free=skip_disk_free,
        admin_group=None if no_admin_group else admin_group,
        client=client,
        environment=environment,
    )
    runner = Runner(dry_run=dry_run, force=force)
    raise typer.Exit(
        execute(runner, options, BUILD_STAGE_FUNCS, BUILD_STAGES, only, program="cairn-build")
    )


@app.command(
    "setup-timer",
    help="Install (but do not start) the build-automation timer. Must be run with sudo.",
)
def setup_timer_command(
    manifest_path: Annotated[
        Path, typer.Option("--manifest", help="The manifest this build timer advances.")
    ],
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
    build_interval: Annotated[
        str, typer.Option("--build-interval", help="Build poll interval.")
    ] = "15min",
) -> None:
    """Install the build-automation timer only (BR-CLI-023, ADR-047, ADR-052).

    Root-gated the same way `setup` is — writing to `/etc/systemd/system` needs it, and
    this command has no preceding `preflight` stage of its own to have already checked. Takes
    no `--environment` — the manifest declares at most one (`BR-DEPLOY-009a`), so the timer's
    unit names and the environment its script advances are both read from *manifest_path*
    itself rather than typed a second time somewhere they could disagree with it.
    """
    manifest = config.load_manifest(manifest_path)
    if manifest.environment is None:
        raise typer.BadParameter(
            f"{manifest_path} declares no environment — add `[cairn] environment = \"...\"` "
            f"before installing a build timer for it."
        )
    options = SetupOptions(
        dry_run=dry_run,
        force=force,
        workdir=workdir,
        manifest=manifest_path,
        environment=manifest.environment,
        build_interval=build_interval,
    )
    runner = Runner(dry_run=dry_run, force=force)
    raise typer.Exit(
        execute(
            runner,
            options,
            BUILD_TIMER_STAGE_FUNCS,
            TIMER_STAGES,
            None,
            program="cairn-build",
            verb="setup-timer",
        )
    )


def main() -> None:
    """Console-script entry point for the ``cairn-build`` command."""
    app()


if __name__ == "__main__":
    main()
