"""Machine-local config for the registry role (`BR-REG-002`, `ADR-048`).

One file, one fixed path:

    /etc/cairn/registry.toml

Read the same way `builder.toml`/`adopt.toml` are — no directory search (`ADR-042`'s
discovery model) — but unlike those, **entirely optional**: `cairn-registry setup` runs
against documented built-in defaults when the file is absent, since a first-time operator
should get a working registry before ever hand-writing TOML.

This module MUST NOT import `config.py` or `environments.py` (`BR-REG-001`) — registry
lifecycle and retention decisions are derived only from this file and from the registry's own
API, never from a manifest or a declared environment list.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .errors import RegistryConfigError

#: The one path (mirrors `ADR-034`'s fixed-path model for `adopt.toml`).
CONFIG_PATH = Path("/etc/cairn/registry.toml")

_TOP_LEVEL_KEYS = {"registry"}
_REGISTRY_KEYS = {"port", "bind_address", "data_dir", "retention", "gc"}
_RETENTION_KEYS = {"enabled", "keep_last", "max_age_days"}
_GC_KEYS = {"schedule"}

_DEFAULT_PORT = 5000
_DEFAULT_BIND_ADDRESS = "127.0.0.1"
_DEFAULT_DATA_DIR = Path("/var/lib/cairn-registry")
_DEFAULT_KEEP_LAST = 10
_DEFAULT_MAX_AGE_DAYS = 90
_DEFAULT_SCHEDULE = "weekly"


@dataclass(frozen=True)
class Retention:
    """`[registry.retention]` — off by default; deleting nothing is always the safe default."""

    enabled: bool = False
    keep_last: int = _DEFAULT_KEEP_LAST
    max_age_days: int = _DEFAULT_MAX_AGE_DAYS


@dataclass(frozen=True)
class Gc:
    """`[registry.gc]` — `schedule` is a systemd `OnCalendar=` value (`BR-REG-010`)."""

    schedule: str = _DEFAULT_SCHEDULE


@dataclass(frozen=True)
class RegistryConfig:
    """A validated `/etc/cairn/registry.toml`, or the built-in defaults if none exists."""

    port: int = _DEFAULT_PORT
    bind_address: str = _DEFAULT_BIND_ADDRESS
    data_dir: Path = _DEFAULT_DATA_DIR
    retention: Retention = field(default_factory=Retention)
    gc: Gc = field(default_factory=Gc)
    path: Path | None = None

    @property
    def host(self) -> str:
        """The `host:port` the registry listens on and is addressed by."""
        return f"{self.bind_address}:{self.port}"


def load(path: Path | None = None) -> RegistryConfig:
    """Read and validate the registry config, or raise :class:`RegistryConfigError`.

    *path* exists for tests. In production this is called with nothing — absence at the fixed
    path is not an error, it means "use the documented defaults" (`BR-REG-002`).
    """
    target = path or CONFIG_PATH
    if not target.is_file():
        return RegistryConfig()

    try:
        with target.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise RegistryConfigError(f"{target}: not valid TOML — {exc}") from exc
    except OSError as exc:
        raise RegistryConfigError(f"{target}: cannot be read — {exc}") from exc

    _reject_unknown(target, "the config", set(data), _TOP_LEVEL_KEYS)
    section = data.get("registry", {})
    if not isinstance(section, dict):
        raise RegistryConfigError(f"{target}: [registry] must be a table.")
    _reject_unknown(target, "[registry]", set(section), _REGISTRY_KEYS)

    return RegistryConfig(
        port=_port(target, section),
        bind_address=_bind_address(target, section),
        data_dir=_data_dir(target, section),
        retention=_retention(target, section.get("retention", {})),
        gc=_gc(target, section.get("gc", {})),
        path=target,
    )


def _port(path: Path, section: dict) -> int:
    value = section.get("port", _DEFAULT_PORT)
    if not isinstance(value, int) or isinstance(value, bool) or not (1 <= value <= 65535):
        raise RegistryConfigError(f"{path}: [registry] port must be an integer 1-65535.")
    return value


def _bind_address(path: Path, section: dict) -> str:
    value = section.get("bind_address", _DEFAULT_BIND_ADDRESS)
    if not isinstance(value, str) or not value.strip():
        raise RegistryConfigError(f"{path}: [registry] bind_address must be a non-empty string.")
    return value


def _data_dir(path: Path, section: dict) -> Path:
    value = section.get("data_dir", str(_DEFAULT_DATA_DIR))
    if not isinstance(value, str) or not value.strip():
        raise RegistryConfigError(f"{path}: [registry] data_dir must be a non-empty string.")
    resolved = Path(value).expanduser()
    if not resolved.is_absolute():
        raise RegistryConfigError(
            f"{path}: [registry] data_dir '{value}' must be an absolute path — it names where "
            f"registry blobs are bind-mounted on this host."
        )
    return resolved


def _retention(path: Path, section: object) -> Retention:
    if not isinstance(section, dict):
        raise RegistryConfigError(f"{path}: [registry.retention] must be a table.")
    _reject_unknown(path, "[registry.retention]", set(section), _RETENTION_KEYS)

    enabled = section.get("enabled", False)
    if not isinstance(enabled, bool):
        raise RegistryConfigError(f"{path}: [registry.retention] enabled must be true or false.")

    keep_last = _positive_int(
        path, "[registry.retention]", section, "keep_last", _DEFAULT_KEEP_LAST
    )
    max_age_days = _positive_int(
        path, "[registry.retention]", section, "max_age_days", _DEFAULT_MAX_AGE_DAYS
    )
    return Retention(enabled=enabled, keep_last=keep_last, max_age_days=max_age_days)


def _gc(path: Path, section: object) -> Gc:
    if not isinstance(section, dict):
        raise RegistryConfigError(f"{path}: [registry.gc] must be a table.")
    _reject_unknown(path, "[registry.gc]", set(section), _GC_KEYS)

    schedule = section.get("schedule", _DEFAULT_SCHEDULE)
    if not isinstance(schedule, str) or not schedule.strip():
        raise RegistryConfigError(f"{path}: [registry.gc] schedule must be a non-empty string.")
    return Gc(schedule=schedule)


def _positive_int(path: Path, where: str, section: dict, key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RegistryConfigError(f"{path}: {where} {key} must be a positive integer.")
    return value


def _reject_unknown(path: Path, where: str, keys: set[str], allowed: set[str]) -> None:
    """Fail on unrecognized keys, so a typo surfaces here and not as a silent no-op."""
    unknown = keys - allowed
    if unknown:
        raise RegistryConfigError(
            f"{path}: {where} has unknown key(s) {', '.join(sorted(unknown))}; "
            f"expected any of {', '.join(sorted(allowed))}."
        )
