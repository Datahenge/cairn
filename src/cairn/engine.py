"""Build-engine detection: `docker build` or `podman build` (`ADR-027`).

The build machine and the deploy target are different machines, and the only artifact
crossing between them is an OCI image in a registry — so the build engine is a property
of the build machine alone. `DEPLOY` remains Docker regardless of what is selected here.

Preference order is docker, then podman; an explicit choice from local build config
(`BR-CFG-008`) overrides detection. Engine floors are `ADR-027`'s: Docker v23+ (BuildKit
is the default builder from 23.0) and podman v4+ (documented floor for
``--mount=type=secret``, which `BR-BUILD-006` depends on).

The two engines are probed differently on purpose. Docker's
``docker version --format {{.Server.Version}}`` reports the *server* version and so
doubles as a daemon-reachability check. Podman is daemonless — there is no server to
reach — so its version comes from ``podman --version`` and usability is confirmed
separately with ``podman info``, which is what fails when a rootless install cannot claim
its subuid range.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from .errors import BuildEngineError

DOCKER = "docker"
PODMAN = "podman"

#: Detection order when build config expresses no preference (`ADR-027`).
PREFERENCE: tuple[str, ...] = (DOCKER, PODMAN)

#: Minimum major version per engine (`ADR-027`).
MIN_MAJOR: dict[str, int] = {DOCKER: 23, PODMAN: 4}

#: Ceiling on any single probe, so an unresponsive daemon cannot hang the caller.
PROBE_TIMEOUT_SECONDS = 15


@dataclass(frozen=True)
class BuildEngine:
    """A usable build engine: which binary, and the version that satisfied the floor."""

    name: str
    version: str

    @property
    def needs_buildx(self) -> bool:
        """Whether this engine's builds go through the separate buildx plugin.

        Docker routes ``docker build`` through buildx/BuildKit; podman builds with
        buildah in-process and has no equivalent plugin to check for.
        """
        return self.name == DOCKER


def detect(preferred: str | None = None) -> BuildEngine:
    """Return the build engine to use, or raise :class:`BuildEngineError`.

    *preferred* comes from local build config (`BR-CFG-008`); when given, only that
    engine is considered, so an explicit choice fails loudly rather than silently
    falling back to the other one.
    """
    if preferred and preferred not in MIN_MAJOR:
        raise BuildEngineError(
            f"Unknown build engine {preferred!r}; expected one of {', '.join(MIN_MAJOR)}."
        )

    failures: list[str] = []
    for name in (preferred,) if preferred else PREFERENCE:
        try:
            return check(name)
        except BuildEngineError as exc:
            failures.append(str(exc))

    detail = " ".join(failures)
    if preferred:
        raise BuildEngineError(f"Build engine '{preferred}' is unusable. {detail}")
    raise BuildEngineError(
        f"No usable build engine found — install Docker Engine v{MIN_MAJOR[DOCKER]}+ "
        f"or podman v{MIN_MAJOR[PODMAN]}+. {detail}"
    )


def check(name: str) -> BuildEngine:
    """Probe one engine and return it, or raise :class:`BuildEngineError` explaining why not."""
    version = _version(name)
    major = _major(version)
    if major is None:
        raise BuildEngineError(f"Cannot parse {name} version {version!r}.")
    if major < MIN_MAJOR[name]:
        raise BuildEngineError(
            f"{name} v{version} is too old; cairn requires {name} v{MIN_MAJOR[name]}+."
        )
    if name == PODMAN:
        _assert_podman_usable()
    return BuildEngine(name=name, version=version)


def _version(name: str) -> str:
    """Return *name*'s version string, raising :class:`BuildEngineError` if unobtainable."""
    if name == DOCKER:
        result = _run([DOCKER, "version", "--format", "{{.Server.Version}}"])
        if result.returncode != 0:
            raise BuildEngineError(
                "Docker daemon not reachable "
                f"({_first_line(result.stderr) or 'docker version failed'}); is it running?"
            )
        return result.stdout.strip()

    result = _run([PODMAN, "--version"])
    if result.returncode != 0:
        raise BuildEngineError(
            f"`podman --version` failed ({_first_line(result.stderr) or 'unknown error'})."
        )
    return result.stdout.strip().rsplit(maxsplit=1)[-1]  # "podman version 5.4.2"


def _assert_podman_usable() -> None:
    """Confirm podman can actually reach its storage, not merely report a version.

    A rootless install that cannot claim its subuid range answers ``--version`` happily
    and then fails every real command with a bare ``permission denied``.
    """
    result = _run([PODMAN, "info"])
    if result.returncode != 0:
        detail = _first_line(result.stderr) or "podman info failed"
        raise BuildEngineError(
            f"podman is installed but unusable ({detail}); check rootless setup — "
            "/etc/subuid and /etc/subgid entries and the newuidmap helpers."
        )


def buildx_version() -> str:
    """Return the ``docker buildx version`` banner, or raise :class:`BuildEngineError`.

    Only meaningful for docker; see :attr:`BuildEngine.needs_buildx`.
    """
    result = _run([DOCKER, "buildx", "version"])
    if result.returncode != 0:
        raise BuildEngineError(
            "docker buildx is unavailable; install the buildx plugin "
            "(package `docker-buildx-plugin`)."
        )
    return result.stdout.strip()


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run *command*, translating "could not run it at all" into :class:`BuildEngineError`."""
    try:
        return subprocess.run(
            command, capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as exc:
        raise BuildEngineError(f"`{command[0]}` not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise BuildEngineError(
            f"`{' '.join(command)}` timed out after {PROBE_TIMEOUT_SECONDS}s."
        ) from exc


def _major(version: str) -> int | None:
    match = re.match(r"\s*v?(\d+)", version)
    return int(match.group(1)) if match else None


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""
