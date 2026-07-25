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

    @property
    def references(self) -> tuple[str, str]:
        """The two fully-qualified image references this build produces."""
        return f"{self.image_base}:{self.primary_tag}", f"{self.image_base}:{self.moving_tag}"

    def command(self, apps_json: Path) -> list[str]:
        """Return the exact engine invocation, with *apps_json* mounted as a secret."""
        command = [self.engine_name, "build"]
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


def run(build_plan: BuildPlan) -> None:
    """Execute *build_plan*, raising :class:`BuildError` if the engine fails (BR-BUILD-009)."""
    with appsjson.written(build_plan.apps_json) as apps_json:
        command = build_plan.command(apps_json)
        result = subprocess.run(command, check=False)
    if result.returncode != 0:
        raise BuildError(
            f"{build_plan.engine_name} build failed with exit code {result.returncode}. "
            f"The command was:\n  {shlex.join(command)}"
        )


def _as_arg(value: Any) -> str:
    """Render a manifest value as a build-arg string; TOML booleans become true/false."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
