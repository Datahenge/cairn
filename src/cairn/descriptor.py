"""The target's environment descriptor (`BR-DEPLOY-010`, `BR-DEPLOY-010a`, `ADR-034`).

One file, at one fixed path, describing the single environment this host runs:

    /etc/cairn/adopt.toml

It is the target half of `BR-DEPLOY-009`'s two-halves model, joined to the control half by
nothing but the tag name. Where the manifest says *what image to build*, this says *what this
box runs*: which image and which tag to watch, which frappe_docker overrides compose the
stack, the site, and the **name of the mechanism** holding secrets.

Three properties are load-bearing:

* **Fixed path, not searched.** `reconcile` runs unattended under a timer, where nobody is
  present to pass a flag and a search path is a way to silently converge the wrong
  environment. The override exists for tests, not for operators.
* **Its presence is the role signal.** A machine with this file is a target; that is how
  `cairn doctor` chooses which checks to run without being told (`ADR-028`).
* **No secret values, ever** (`BR-DEPLOY-011`). The descriptor names a mechanism and
  references what the operator provisioned. cairn never reads a secret's value, and this
  file is not where one would be found.

It is **host state, not deployment state** — describing this box, not the deployment — so it
is not committed with the manifest.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import DescriptorError

#: The one path (`ADR-034`). Not a search path, and not a default among several.
DESCRIPTOR_PATH = Path("/etc/cairn/adopt.toml")

#: Secret mechanisms cairn can wire. It handles no values either way (`BR-DEPLOY-013`).
SECRET_MECHANISMS = ("docker-secrets", "env-file", "none")

TOP_LEVEL_KEYS = {"environment", "image", "tag", "site", "compose", "secrets", "health"}


@dataclass(frozen=True)
class Compose:
    """Which frappe_docker overrides compose this stack, and where they are."""

    #: Override names, in the order they are layered onto the base compose file.
    overrides: tuple[str, ...] = ()
    #: Directory holding the compose files — the frappe_docker tree on this host.
    directory: Path | None = None
    #: Compose project name, so several stacks on one host cannot collide.
    project: str | None = None
    #: Extra environment file passed to compose, if the operator uses one.
    env_file: Path | None = None


@dataclass(frozen=True)
class Health:
    """How long to wait for the stack to come up, and what to ask (`BR-DEPLOY-017`)."""

    #: Ceiling on convergence before the deploy is declared failed.
    timeout_seconds: int = 600
    #: Seconds between health probes.
    interval_seconds: int = 5
    #: A URL to fetch to confirm the site answers; absent means container health only.
    url: str | None = None


@dataclass(frozen=True)
class Descriptor:
    """A validated environment descriptor (`BR-DEPLOY-010`)."""

    environment: str
    image: str
    tag: str
    site: str
    compose: Compose = field(default_factory=Compose)
    health: Health = field(default_factory=Health)
    secret_mechanism: str = "none"
    path: Path | None = None

    @property
    def reference(self) -> str:
        """The image reference this host watches — the desired-state pointer (`BR-DEPLOY-002`)."""
        return f"{self.image}:{self.tag}"

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"


def load(path: Path | None = None) -> Descriptor:
    """Read and validate the descriptor, or raise :class:`DescriptorError`.

    *path* exists for tests. In production this is called with nothing, because the location
    is fixed on purpose (`BR-DEPLOY-010a`).
    """
    target = path or DESCRIPTOR_PATH
    if not target.is_file():
        raise DescriptorError(
            f"No environment descriptor at {target}, so cairn does not know what this host "
            f"runs. Create it, declaring at least the image, the tag to watch, and the site."
        )

    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise DescriptorError(f"{target}: not valid TOML — {exc}") from exc
    except OSError as exc:
        raise DescriptorError(f"{target}: cannot be read — {exc}") from exc

    _reject_unknown(target, "the descriptor", set(data), TOP_LEVEL_KEYS)
    return Descriptor(
        environment=_required(target, data, "environment"),
        image=_required(target, data, "image"),
        tag=_required(target, data, "tag"),
        site=_required(target, data, "site"),
        compose=_compose(target, data.get("compose", {})),
        health=_health(target, data.get("health", {})),
        secret_mechanism=_secret_mechanism(target, data.get("secrets", {})),
        path=target,
    )


def exists(path: Path | None = None) -> bool:
    """Whether this host has a descriptor — i.e. whether it is a target (`ADR-028`)."""
    return (path or DESCRIPTOR_PATH).is_file()


def _compose(path: Path, section: object) -> Compose:
    if not isinstance(section, dict):
        raise DescriptorError(f"{path}: [compose] must be a table.")
    _reject_unknown(
        path, "[compose]", set(section), {"overrides", "directory", "project", "env_file"}
    )

    overrides = section.get("overrides", [])
    if not isinstance(overrides, list) or not all(isinstance(name, str) for name in overrides):
        raise DescriptorError(
            f"{path}: [compose] overrides must be a list of override names, in the order "
            f"they are layered, e.g. [\"mariadb\", \"redis\", \"https\"]."
        )

    return Compose(
        overrides=tuple(overrides),
        directory=_optional_path(path, section, "directory"),
        project=_optional_string(path, "[compose]", section, "project"),
        env_file=_optional_path(path, section, "env_file"),
    )


def _health(path: Path, section: object) -> Health:
    if not isinstance(section, dict):
        raise DescriptorError(f"{path}: [health] must be a table.")
    _reject_unknown(path, "[health]", set(section), {"timeout_seconds", "interval_seconds", "url"})

    defaults = Health()
    timeout = section.get("timeout_seconds", defaults.timeout_seconds)
    interval = section.get("interval_seconds", defaults.interval_seconds)
    for name, value in (("timeout_seconds", timeout), ("interval_seconds", interval)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise DescriptorError(f"{path}: [health] {name} must be a whole number of seconds.")
    if interval > timeout:
        raise DescriptorError(
            f"{path}: [health] interval_seconds ({interval}) exceeds timeout_seconds "
            f"({timeout}), so the stack would never be checked before giving up."
        )
    return Health(
        timeout_seconds=timeout,
        interval_seconds=interval,
        url=_optional_string(path, "[health]", section, "url"),
    )


def _secret_mechanism(path: Path, section: object) -> str:
    if not isinstance(section, dict):
        raise DescriptorError(f"{path}: [secrets] must be a table.")
    _reject_unknown(path, "[secrets]", set(section), {"mechanism"})

    mechanism = section.get("mechanism", "none")
    if mechanism not in SECRET_MECHANISMS:
        raise DescriptorError(
            f"{path}: [secrets] mechanism '{mechanism}' is not one cairn can wire; "
            f"expected one of {', '.join(SECRET_MECHANISMS)}."
        )
    return str(mechanism)


def _required(path: Path, data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DescriptorError(f"{path}: '{key}' is required and must be a non-empty string.")
    return value


def _optional_string(path: Path, where: str, section: dict, key: str) -> str | None:
    value = section.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise DescriptorError(f"{path}: {where} {key} must be a non-empty string when set.")
    return value


def _optional_path(path: Path, section: dict, key: str) -> Path | None:
    value = _optional_string(path, "[compose]", section, key)
    return Path(value).expanduser() if value else None


def _reject_unknown(path: Path, where: str, keys: set[str], allowed: set[str]) -> None:
    """Fail on unrecognized keys, so a typo surfaces here and not as a wrong deploy."""
    unknown = keys - allowed
    if unknown:
        raise DescriptorError(
            f"{path}: {where} has unknown key(s) {', '.join(sorted(unknown))}; "
            f"expected any of {', '.join(sorted(allowed))}."
        )
