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
    if not build_config.registry:
        raise PushError(
            "No registry configured, so images remain local. Set `registry` (and usually "
            "`namespace`) in /etc/cairn/builder.toml, or set $CAIRN_REGISTRY (and usually "
            "$CAIRN_NAMESPACE)."
        )


def push(image: str, engine_name: str) -> None:
    """Push one image reference with *engine_name*, or raise :class:`PushError`.

    Invoked with the engine's own ``--quiet`` (`BR-CLI-003`, `BR-CLI-011`): unquieted,
    both engines print one line per layer ("Pushed", "Layer already exists"), which is
    the engine's internal transfer bookkeeping, not something cairn computed — noise
    at best, and read by a newcomer as an error at worst when a second push of the same
    digest under `latest` (`BR-BUILD-008`) reports every layer as already present.
    `--quiet` suppresses only that per-layer progress on both engines at cairn's
    documented floors (Docker v23+, podman v4+, `ADR-027`); it does not suppress errors
    or exit codes — Docker's `--quiet` briefly did (docker/cli#2284) but that was fixed
    in 20.10.0, well below cairn's floor. cairn's own `Pushing …` / `Pushed …` framing
    around the call already carries the reference; the digest was already reported once
    after the build (`BR-BUILD-011`).
    """
    command = [engine_name, "push", "--quiet", image]
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError as exc:
        raise PushError(f"`{engine_name}` not found on PATH.") from exc

    if result.returncode != 0:
        raise PushError(
            f"Pushing {image} failed with exit code {result.returncode}. If this is an "
            f"authentication failure, run `{engine_name} login {registry_host(image)}` — "
            f"cairn never stores registry credentials. The command was:\n"
            f"  {shlex.join(command)}"
        )


def registry_host(image: str) -> str:
    """Return the registry host of *image*, for a useful `login` hint.

    A first path component containing a dot or a colon is a registry host; anything else
    is a namespace on the engine's default registry.
    """
    head = image.split("/", 1)[0]
    return head if ("." in head or ":" in head) else "<registry>"
