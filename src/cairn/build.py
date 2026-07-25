"""Assemble and run the image build (BR-BUILD-009/010/011/012).

The pipeline, in order: enforce the vendored-tree preconditions, resolve every ref, work
out the effective build args, derive the cache bust and tags, render ``apps.json`` to a
private temporary file, and invoke the selected engine with provenance labels attached.

Three things this module is careful about:

* **Preconditions first** (`BR-BUILD-009`). Drift, nested git metadata, and missing build
  inputs are checked before anything expensive happens — drift is a hard stop with no
  override (`BR-VEND-005`).
* **Effective, not declared, build args** (`BR-BUILD-010`). The Containerfile's own ``ARG``
  defaults are read and the manifest's knobs layered over them, so provenance records what
  the build actually used and the input hash covers it. A vendored-pin bump that moves a
  default therefore changes the tag even with an unchanged manifest — intended, see
  `BR-BUILD-008`.
* **`apps.json` only ever as a secret** (`BR-BUILD-006`). It is never a build-arg, and the
  file holding it is owner-only and removed on the way out.

``--dry-run`` (`BR-BUILD-012`) produces the same :class:`BuildPlan` and renders it without
invoking anything, so it needs no container engine and stays CI-safe.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import __version__, appsjson, engine, resolve, tagging, vendor
from .config import BuildConfig, Manifest
from .errors import BuildError, ProjectRootNotFoundError
from .project import read_vendor_sources
from .resolve import Resolution
from .transcript import Transcript

#: ventwig's committed anchor — the synced commit/tree of the vendored tree (`BR-VEND-003`).
LOCK_NAME = ".ventwig.lock"

#: Manifest knob -> Containerfile build-arg (`BR-BUILD-002`, `BR-BUILD-010`).
KNOB_TO_BUILD_ARG = {
    "python_version": "PYTHON_VERSION",
    "node_version": "NODE_VERSION",
    "install_chromium": "INSTALL_CHROMIUM",
    "debian_base": "DEBIAN_BASE",
    "wkhtmltopdf_version": "WKHTMLTOPDF_VERSION",
    "wkhtmltopdf_distro": "WKHTMLTOPDF_DISTRO",
}

#: Derived at build time, so it is not an *input* — excluded from the recorded args.
CACHE_BUST_ARG = "CACHE_BUST"

#: Frappe's source, supplied as build-args rather than via apps.json (`BR-BUILD-004`).
FRAPPE_PATH_ARG = "FRAPPE_PATH"
FRAPPE_BRANCH_ARG = "FRAPPE_BRANCH"

LABEL_NAMESPACE = "com.datahenge.cairn"
OCI_NAMESPACE = "org.opencontainers.image"

#: The vendored Containerfile's expensive intermediate stage (`BR-BUILD-015`).
CACHE_STAGE_TARGET = "builder"

#: Repository the cache stage is named under, so a listing explains itself.
CACHE_STAGE_REPOSITORY = "cairn-cache"

#: Ceiling on the tagging pass. Against a warm cache it takes under a second; this only
#: bounds the pathological case where the stage has somehow gone and it starts rebuilding.
CACHE_TAG_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class BuildPlan:
    """Everything a build will do, decided before anything is invoked.

    Rendering this without running it is exactly what ``--dry-run`` is (`BR-BUILD-012`).
    """

    image_base: str
    primary_tag: str
    moving_tag: str
    build_args: dict[str, str]
    cache_bust: str
    labels: dict[str, str]
    resolution: Resolution
    apps_json: str
    context: Path
    containerfile: Path
    engine_name: str
    no_cache: bool = False
    plain_progress: bool = False

    @property
    def references(self) -> tuple[str, str]:
        """The two fully-qualified image references this build produces."""
        return f"{self.image_base}:{self.primary_tag}", f"{self.image_base}:{self.moving_tag}"

    def command(self, apps_json: Path) -> list[str]:
        """Return the exact engine invocation, with *apps_json* mounted as a secret."""
        command = [self.engine_name, "build"]
        if self.plain_progress and self.engine_name == engine.DOCKER:
            command.append("--progress=plain")
        if self.no_cache:
            command.append("--no-cache")
        for key, value in self.build_args.items():
            command += ["--build-arg", f"{key}={value}"]
        command += ["--build-arg", f"{CACHE_BUST_ARG}={self.cache_bust}"]
        for key, value in self.labels.items():
            command += ["--label", f"{key}={value}"]
        command += ["--secret", f"id={appsjson.SECRET_ID},src={apps_json}"]
        for reference in self.references:
            command += ["--tag", reference]
        command += ["--file", str(self.containerfile), str(self.context)]
        return command

    @property
    def local_name(self) -> str:
        """The manifest's image name, without any registry or namespace."""
        return self.image_base.rpartition("/")[2]

    @property
    def cache_stage_reference(self) -> str:
        """The name given to the build-cache stage (`BR-BUILD-015`)."""
        return f"{CACHE_STAGE_REPOSITORY}/{self.local_name}:{CACHE_STAGE_TARGET}"

    def cache_stage_command(self, apps_json: Path) -> list[str]:
        """Return the pass that *names* the cache stage rather than building anything.

        Deliberately omits two things the real build has. **Labels**, because they belong
        to the finished image and a stage is not one. And **``--no-cache``**, even when the
        build itself used it: this pass exists to name what that build just produced, so
        ignoring the cache would rebuild the very layer it is trying to point at.
        """
        command = [self.engine_name, "build", "--target", CACHE_STAGE_TARGET]
        for key, value in self.build_args.items():
            command += ["--build-arg", f"{key}={value}"]
        command += ["--build-arg", f"{CACHE_BUST_ARG}={self.cache_bust}"]
        command += ["--secret", f"id={appsjson.SECRET_ID},src={apps_json}"]
        command += ["--tag", self.cache_stage_reference]
        command += ["--file", str(self.containerfile), str(self.context)]
        return command

    def render(self) -> str:
        """Return the human-readable dry-run report (`BR-BUILD-012`)."""
        lines = [
            "apps.json (build secret, never a build-arg):",
            *(f"  {line}" for line in self.apps_json.rstrip().splitlines()),
            "",
            "resolved inputs:",
            *(
                f"  {r.name:<12} {r.ref:<14} {r.kind.value:<7} {r.short_commit}"
                + ("  (moving)" if r.is_moving else "")
                for r in self.resolution.all_refs
            ),
            "",
            "tags:",
            *(f"  {reference}" for reference in self.references),
            "",
            "provenance labels:",
            *(f"  {key}={value}" for key, value in self.labels.items()),
            "",
            "build command:",
            "  " + shlex.join(self.command(Path("<apps.json>"))),
        ]
        return "\n".join(lines)


def plan(
    root: Path,
    manifest: Manifest,
    build_config: BuildConfig,
    *,
    no_cache: bool = False,
    engine_name: str | None = None,
    plain_progress: bool = False,
) -> BuildPlan:
    """Resolve everything and decide the whole build, without invoking anything.

    Enforces the `VEND` preconditions first (`BR-BUILD-009`), then resolves refs, so a
    drifted tree fails before any network work.
    """
    vendor.assert_clean(root)
    vendor.assert_no_nested_git(root)
    vendor.assert_build_inputs(root)

    containerfile = vendor.containerfile_path(root)
    selected = engine_name or engine.detect(build_config.engine).name
    resolution = resolve.resolve_manifest(manifest)

    build_args = effective_build_args(manifest, containerfile, resolution)
    recorded = {key: value for key, value in build_args.items() if key != CACHE_BUST_ARG}
    primary, moving = tagging.tags(resolution, recorded)

    return BuildPlan(
        image_base=build_config.resolve_image_base(manifest.image_name),
        primary_tag=primary,
        moving_tag=moving,
        build_args=build_args,
        cache_bust=tagging.cache_bust(resolution),
        labels=provenance_labels(root, manifest, resolution, recorded, primary, moving),
        resolution=resolution,
        apps_json=appsjson.render(manifest),
        context=vendor.build_context(root),
        containerfile=containerfile,
        engine_name=selected,
        no_cache=no_cache,
        plain_progress=plain_progress,
    )


def effective_build_args(
    manifest: Manifest, containerfile: Path, resolution: Resolution
) -> dict[str, str]:
    """Return the build args the build will actually use (BR-BUILD-010).

    Containerfile defaults first, the manifest's ``[cairn.build]`` knobs over them, then
    Frappe's source. ``CACHE_BUST`` is dropped: it is derived from the resolution, not an
    input, and carrying it here would put a value into provenance that merely restates the
    commits already recorded.
    """
    args = {
        key: value
        for key, value in vendor.containerfile_arg_defaults(containerfile).items()
        if key != CACHE_BUST_ARG
    }
    for knob, value in manifest.build.items():
        args[KNOB_TO_BUILD_ARG.get(knob, knob.upper())] = _as_arg(value)

    args[FRAPPE_PATH_ARG] = resolution.frappe.url
    args[FRAPPE_BRANCH_ARG] = resolution.frappe.ref
    return args


def provenance_labels(
    root: Path,
    manifest: Manifest,
    resolution: Resolution,
    build_args: dict[str, str],
    primary_tag: str,
    moving_tag: str,
) -> dict[str, str]:
    """Return the OCI labels stamped onto the image (BR-BUILD-011, `ADR-030`).

    ``org.opencontainers.image.vendor`` is deliberately unset: the distributing entity of
    the operator's image is theirs to declare, not cairn's.
    """
    pin = vendor_pin(root)
    return {
        f"{OCI_NAMESPACE}.created": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        f"{OCI_NAMESPACE}.title": manifest.image_name,
        f"{OCI_NAMESPACE}.version": primary_tag,
        f"{OCI_NAMESPACE}.revision": resolution.frappe.commit,
        f"{LABEL_NAMESPACE}.version": __version__,
        f"{LABEL_NAMESPACE}.input-hash": primary_tag.rpartition("-")[2],
        f"{LABEL_NAMESPACE}.tag.primary": primary_tag,
        f"{LABEL_NAMESPACE}.tag.moving": moving_tag,
        f"{LABEL_NAMESPACE}.frappe.url": resolution.frappe.url,
        f"{LABEL_NAMESPACE}.frappe.ref": resolution.frappe.ref,
        f"{LABEL_NAMESPACE}.frappe.commit": resolution.frappe.commit,
        f"{LABEL_NAMESPACE}.apps": json.dumps(
            [
                {"name": app.name, "url": app.url, "ref": app.ref, "commit": app.commit}
                for app in resolution.apps
            ],
            separators=(",", ":"),
        ),
        f"{LABEL_NAMESPACE}.build-args": json.dumps(
            build_args, sort_keys=True, separators=(",", ":")
        ),
        f"{LABEL_NAMESPACE}.frappe-docker.ref": pin.get("ref", ""),
        f"{LABEL_NAMESPACE}.frappe-docker.commit": pin.get("commit", ""),
    }


def vendor_pin(root: Path, source_name: str = vendor.FRAPPE_DOCKER_SOURCE) -> dict[str, str]:
    """Return the vendored upstream's pin: declared ``ref`` plus synced ``commit``.

    The two halves live in different files by design — ``pyproject.toml`` declares the
    immutable-intent ref (`BR-VEND-002`) while ``.ventwig.lock`` records what was actually
    synced (`BR-VEND-003`) — so provenance records both. Missing values degrade to empty
    strings rather than failing a build: the integrity check that matters is
    `BR-VEND-005`, already enforced before this is called.
    """
    try:
        sources = read_vendor_sources(root)
    except ProjectRootNotFoundError:
        sources = []
    ref = next((s.ref or "" for s in sources if s.name == source_name), "")

    try:
        with (root / LOCK_NAME).open("rb") as handle:
            locked = tomllib.load(handle).get(source_name, {})
    except (OSError, tomllib.TOMLDecodeError):
        locked = {}

    return {"ref": ref, "commit": str(locked.get("synced_commit", ""))}


def run(build_plan: BuildPlan, sink: Transcript | None = None) -> None:
    """Execute *build_plan*, raising :class:`BuildError` if the engine fails (BR-BUILD-009).

    Without a *sink* the engine's output is inherited rather than captured, so a long
    build reports progress live at no cost. With one — attended use (`BR-CLI-016`) — the
    output is teed: still live on the terminal, and simultaneously into the transcript.
    On failure the exact command is quoted back, since that is what makes the failure
    reproducible by hand (`BR-CLI-015`).
    """
    with appsjson.written(build_plan.apps_json) as apps_json:
        command = build_plan.command(apps_json)
        try:
            returncode = (
                _tee(command, sink) if sink else subprocess.run(command, check=False).returncode
            )
        except FileNotFoundError as exc:
            raise BuildError(
                f"`{build_plan.engine_name}` not found on PATH when starting the build."
            ) from exc

    if returncode != 0:
        raise BuildError(
            f"{build_plan.engine_name} build failed with exit code {returncode}.\n"
            f"Command:\n  {shlex.join(command)}"
        )


def _tee(command: list[str], sink: Transcript) -> int:
    """Run *command*, streaming its output to stderr and *sink* at once.

    stderr is merged into stdout so the transcript preserves interleaving exactly as the
    terminal showed it — two separately-drained pipes would reorder the two streams
    against each other. Lines are flushed as they arrive, so an interrupted build still
    leaves a transcript that ends where the build stopped.
    """
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    )
    assert process.stdout is not None  # guaranteed by stdout=PIPE
    with process.stdout as stream:
        for line in stream:
            sys.stderr.write(line)
            sys.stderr.flush()
            sink.write(line)
    return process.wait()


def tag_cache_stage(build_plan: BuildPlan) -> str | None:
    """Name the build-cache stage, returning its reference, or None (BR-BUILD-015).

    **Call only immediately after a build that actually ran.** A tag is a pointer, so this
    is free — measured at 0.762s, every step a cache hit, no new image — but *only* against
    a warm cache. Run it when the stage has since been pruned and the identical command is a
    full ``bench init`` instead. The moment after a real build is the one moment the stage
    is guaranteed to exist.

    Podman only: docker keeps its cache in a separate store, so there is no stage to name
    and asking for one would make BuildKit materialize several gigabytes that otherwise
    never exist (`ADR-027`, amended).

    Best-effort by design. The image is already built and verified; failing to attach a
    courtesy name must not turn a successful build into a failed command.
    """
    if build_plan.engine_name != engine.PODMAN:
        return None

    with appsjson.written(build_plan.apps_json) as apps_json:
        command = build_plan.cache_stage_command(apps_json)
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=CACHE_TAG_TIMEOUT_SECONDS,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return None

    return build_plan.cache_stage_reference if result.returncode == 0 else None


def existing_image(build_plan: BuildPlan) -> str | None:
    """Return the digest already holding this build's primary tag, or None (BR-BUILD-014).

    The primary tag is a deterministic function of every resolved input, so finding it
    already present proves the inputs are unchanged and the build is redundant. Rebuilding
    would not merely waste time: it would mint a second digest, move the tag onto it, and
    leave the first image nameless — which is how a build machine accumulates orphaned
    multi-gigabyte images under a name that never changed (`ADR-032`).
    """
    reference = build_plan.references[0]
    command = [build_plan.engine_name, "image", "inspect", "--format", "{{.Id}}", reference]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise BuildError(f"`{build_plan.engine_name}` not found on PATH.") from exc

    return result.stdout.strip() if result.returncode == 0 else None


def assert_image_exists(build_plan: BuildPlan) -> str:
    """Confirm the engine really produced the tagged image, returning its digest.

    An engine that exits 0 without building anything would otherwise be reported as
    success — the worst possible outcome, since nothing downstream would notice until a
    deploy pulled a tag that does not exist. Verifying the post-condition converts that
    into an immediate, explicable failure (`BR-CLI-011`: nothing consequential is silent).
    """
    reference = build_plan.references[0]
    command = [build_plan.engine_name, "image", "inspect", "--format", "{{.Id}}", reference]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise BuildError(f"`{build_plan.engine_name}` not found on PATH.") from exc

    if result.returncode != 0:
        raise BuildError(
            f"{build_plan.engine_name} reported success but {reference} does not exist "
            f"locally. Something went wrong inside the engine — re-run with the command "
            f"printed above to see its output."
        )
    return result.stdout.strip()


def _as_arg(value: Any) -> str:
    """Render a manifest value as a build-arg string; TOML booleans become true/false."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
