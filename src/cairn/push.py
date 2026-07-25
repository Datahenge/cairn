"""Upload a built image to the configured registry (BR-CLI-003, BR-CFG-009/010/011).

Deliberately thin: cairn composes the reference and shells out to the engine's ``push``.
It owns nothing about transport, retries, or credentials.

**cairn never handles credentials** (`BR-CFG-010`). Authentication is the engine's job —
the operator runs ``docker login`` / ``podman login`` once and the engine's own credential
store is consulted thereafter. `BR-CFG-010` *permits* a transient login from an
environment variable; that is not implemented, because naming an environment variable is a
published interface and no need has arisen. Build config carries only the non-secret
registry and namespace.

**Absent a registry the image stays local** (`BR-CFG-011`), so pushing is refused with an
error naming the fix rather than inferring a default registry — cairn is registry-agnostic
and never assumes Docker Hub (`BR-CFG-009`).
"""

from __future__ import annotations

import shlex
import subprocess

from .config import BuildConfig, Manifest
from .errors import PushError


def reference(manifest: Manifest, build_config: BuildConfig, tag: str) -> str:
    """Return the fully-qualified ``<base>:<tag>`` reference (`BR-CFG-011`).

    Used by ``--id``, which names a tag directly and so needs no ref resolution. The
    default path pushes the tags a fresh :class:`~cairn.build.BuildPlan` computed.
    """
    return f"{build_config.resolve_image_base(manifest.image_name)}:{tag}"


def assert_registry_configured(build_config: BuildConfig) -> None:
    """Refuse to push when no registry is configured (`BR-CFG-011`).

    Without one the image base is the local ``cairn/<image_name>``; pushing that would
    fail obscurely, or — worse — reach an inferred default registry.
    """
    if not build_config.registry and not build_config.image_base:
        raise PushError(
            "No registry configured, so images remain local. Set `registry` (and usually "
            "`namespace`) in ~/.config/cairn/config.toml or cairn.local.toml."
        )


def push(image: str, engine_name: str) -> None:
    """Push one image reference with *engine_name*, or raise :class:`PushError`."""
    command = [engine_name, "push", image]
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError as exc:
        raise PushError(f"`{engine_name}` not found on PATH.") from exc

    if result.returncode != 0:
        raise PushError(
            f"Pushing {image} failed with exit code {result.returncode}. If this is an "
            f"authentication failure, run `{engine_name} login {registry_host(image)}` — "
            f"cairn never stores registry credentials (BR-CFG-010). The command was:\n"
            f"  {shlex.join(command)}"
        )


def registry_host(image: str) -> str:
    """Return the registry host of *image*, for a useful `login` hint.

    A first path component containing a dot or a colon is a registry host; anything else
    is a namespace on the engine's default registry.
    """
    head = image.split("/", 1)[0]
    return head if ("." in head or ":" in head) else "<registry>"
