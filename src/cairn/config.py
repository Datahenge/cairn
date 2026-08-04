"""The manifest (``cairn.toml``) and local build configuration.

Two orthogonal files, deliberately kept apart (`BR-CFG-008`):

* **`cairn.toml`** — the portable manifest. *What image to build*: one
  environment-agnostic image, its Frappe source, its ordered app list, and the build
  knobs (`BR-BUILD-001/002/003`). Shareable; carries no registry or machine settings.
  Never discovered implicitly — an invocation always names it, via ``--manifest`` or
  ``$CAIRN_MANIFEST`` (`ADR-042`).
* **build config** — `/etc/cairn/builder.toml`, optionally overridden key-by-key by
  ``CAIRN_*`` environment variables. *Where and how this machine builds*: engine
  (`ADR-027`), registry, namespace (`BR-CFG-009/011`). Never committed with a shared
  deployment. Named for the **Builder** role (`ADR-041`) — only builder-side commands
  and `doctor` ever read it. It lives under `/etc/cairn`, not a per-user home directory
  (`ADR-042`): a shared multi-operator host has no single home directory to hold a fact
  every operator needs identically.

Discovery precedence is `BR-CFG-012`. There is no filesystem search of any kind — not
for the manifest, not for build config (`ADR-042`, superseding `ADR-029`'s walk-up):
a shared host or a container has no working directory or home directory that means
anything reliable, and an implicit "nearest match" is exactly the kind of silent
per-directory drift `BR-CFG-013` already forbids for registry defaults.

Validation is strict on purpose: every table but ``[cairn.build]`` rejects unknown keys,
so a typo fails at parse time with a message naming the key rather than producing a
subtly wrong image an hour later. ``[cairn.build]`` is the documented exception —
`BR-BUILD-002` grants it passthrough for the long tail (``debian_base``,
``wkhtmltopdf_*``).
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import (
    BuildConfigInvalidError,
    ManifestInvalidError,
    ManifestNotFoundError,
)

MANIFEST_NAME = "cairn.toml"
MANIFEST_ENV_VAR = "CAIRN_MANIFEST"
BUILDER_CONFIG_PATH = Path("/etc/cairn/builder.toml")

#: Prefix for the per-key build-config override (`ADR-042`): ``CAIRN_ENGINE``,
#: ``CAIRN_REGISTRY``, and so on, one per `BUILD_CONFIG_KEYS` entry.
BUILD_CONFIG_ENV_PREFIX = "CAIRN_"

#: Build knobs cairn maps to named build-args; anything else rides the passthrough.
KNOWN_BUILD_KNOBS = ("python_version", "node_version", "install_chromium")

#: Recognized build-config keys. Builder/cache settings land with the BUILD module.
BUILD_CONFIG_KEYS = ("engine", "registry", "namespace", "transcript_dir")

#: Image names become OCI repository path components, which are lowercase-only.
_IMAGE_NAME_RE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")

#: A full-length hex string is unambiguously a commit — rejected by BR-BUILD-005.
_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

#: The OCI grammar for a tag: alphanumeric first, then word characters, dots and dashes.
_TAG_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127}$")

#: A tag's legible half. As `_TAG_RE`, minus the hyphen that separates it from the hash.
_SERIES_RE = re.compile(r"^[a-zA-Z0-9_][a-zA-Z0-9._]{0,63}$")

#: Fallback image base when no registry is configured (BR-BUILD-008, BR-CFG-011).
LOCAL_IMAGE_PREFIX = "cairn"


@dataclass(frozen=True)
class App:
    """One entry of the **ordered** ``[[cairn.apps]]`` list (BR-BUILD-002/003)."""

    name: str
    url: str
    ref: str


@dataclass(frozen=True)
class Frappe:
    """The ``[cairn.frappe]`` section, driving ``FRAPPE_PATH``/``FRAPPE_BRANCH``.

    Frappe is supplied via build-args and never appears in ``apps.json``
    (`BR-BUILD-004`).
    """

    url: str
    ref: str


@dataclass(frozen=True)
class Manifest:
    """A validated ``cairn.toml`` — exactly one environment-agnostic image (BR-BUILD-001).

    ``series`` names the human-readable half of the image tag (`BR-BUILD-008`, `ADR-032`) —
    e.g. ``"v16"``, yielding tags like ``v16-1b019793dc20``. Declaring it is what makes that
    half stable when the Frappe ref is re-pinned from a branch to a tag; absent it, the half
    is derived from the declared ref as it always was. It is a **label, not an input**: it
    never enters the input hash, so changing it renames future images without orphaning
    existing ones.

    ``environment`` is this manifest's single declared environment (`BR-DEPLOY-009a`,
    `ADR-052`) — at most one per manifest, and its name **is** its registry tag (no separate
    name/tag mapping). No build reads or writes it by default; a build only points it when
    explicitly asked to (`build --assign-tag`, `BR-CLI-002a`) or via the standalone `assign-tag`
    command, both of which resolve this manifest's own refs and check the registry before
    writing anything — no environment name ever reaches the image itself.
    """

    image_name: str
    frappe: Frappe
    apps: tuple[App, ...]
    build: dict[str, Any] = field(default_factory=dict)
    series: str | None = None
    environment: str | None = None
    path: Path | None = None


@dataclass(frozen=True)
class BuildConfig:
    """Machine-local build settings; absent values fall back to documented defaults."""

    engine: str | None = None
    registry: str | None = None
    namespace: str | None = None
    transcript_dir: str | None = None
    sources: tuple[str, ...] = ()

    def resolve_image_base(self, image_name: str) -> str:
        """Return the image base for *image_name* (`BR-CFG-011`, `BR-BUILD-008`).

        With a registry configured the base is ``<registry>/<namespace>/<image_name>``;
        absent one the image stays local as ``cairn/<image_name>``.
        """
        if self.registry:
            parts = [self.registry, *([self.namespace] if self.namespace else []), image_name]
            return "/".join(parts)
        return f"{LOCAL_IMAGE_PREFIX}/{image_name}"


# --- discovery (BR-CFG-012, ADR-042) -----------------------------------------


def find_manifest(explicit: Path | None = None) -> Path:
    """Locate the manifest: *explicit* if given, else ``$CAIRN_MANIFEST``. Nothing else.

    No directory is ever searched (`ADR-042`). An invocation always states which
    deployment it means, one of two ways — the second exists for the case a flag can't
    reach, like a systemd unit's ``Environment=`` or a container's own environment.
    """
    if explicit is not None:
        path = explicit.expanduser()
        if not path.is_file():
            raise ManifestNotFoundError(f"No manifest at {path}.")
        return path

    env_value = os.environ.get(MANIFEST_ENV_VAR)
    if env_value:
        path = Path(env_value).expanduser()
        if not path.is_file():
            raise ManifestNotFoundError(f"${MANIFEST_ENV_VAR} names {path}, but it is not a file.")
        return path

    raise ManifestNotFoundError(
        f"No manifest given. Pass --manifest <path>, or set ${MANIFEST_ENV_VAR}."
    )


def find_manifest_or_none(explicit: Path | None = None) -> Path | None:
    """Return the resolved manifest, or None where a command does not require one.

    Machine-scoped commands (`BR-CLI-005`'s ``--local``) still want build config, whose
    base layer is `builder.toml` and whose override layer is ``CAIRN_*`` environment
    variables — neither depends on a manifest existing.
    """
    try:
        return find_manifest(explicit)
    except ManifestNotFoundError:
        return None


def load_manifest(path: Path) -> Manifest:
    """Parse and validate *path* as a manifest (BR-BUILD-001/002/003/005)."""
    data = _load_toml(path, ManifestInvalidError)
    root = data.get("cairn")
    if not isinstance(root, dict):
        raise ManifestInvalidError(f"{path}: missing the required [cairn] table.")

    _reject_unknown(
        path,
        "[cairn]",
        root,
        {"image_name", "frappe", "apps", "build", "series", "registry", "environment"},
    )
    return Manifest(
        image_name=_image_name(path, root),
        frappe=_frappe(path, root),
        apps=_apps(path, root),
        build=_build_knobs(path, root),
        series=_series(path, root),
        environment=_environment(path, root),
        path=path,
    )


def load_build_config(manifest_path: Path | None = None) -> BuildConfig:
    """Layer machine defaults, the manifest's registry, then ``CAIRN_*`` env vars.

    Three layers, lowest precedence first (`BR-CFG-012`, `ADR-039`, `ADR-042`):

    1. ``/etc/cairn/builder.toml`` — machine-wide defaults, e.g. the engine. Shared by
       every login on the host; who may write it is a matter of its own filesystem
       permissions, not something cairn assumes (`ADR-042`, `ADR-043`).
    2. the manifest's ``[cairn.registry]`` — **where this deployment's images belong**.
       Committed with the deployment, because under `BR-CFG-013` that registry is usually
       the *client's*, and a coordinate known only to one machine is a coordinate the
       client cannot take over.
    3. ``CAIRN_ENGINE`` / ``CAIRN_REGISTRY`` / ``CAIRN_NAMESPACE`` /
       ``CAIRN_TRANSCRIPT_DIR`` — the deliberate override, for experiments and for
       publishing a client's deployment somewhere else temporarily. Replaces what used to
       be a ``cairn.local.toml`` file (`ADR-042`): the same one-invocation-or-session
       override, without a file to create, gitignore, or forget beside the manifest.

    All three are optional; with none present the config is all-defaults and images stay
    local (`BR-CFG-011`). Every override is key-by-key, so setting only
    ``CAIRN_NAMESPACE`` keeps the engine from layer 1 and the host from layer 2.
    """
    merged: dict[str, Any] = {}
    sources: list[str] = []

    if _readable(BUILDER_CONFIG_PATH):
        merged.update(_build_config_values(BUILDER_CONFIG_PATH))
        sources.append(str(BUILDER_CONFIG_PATH))

    if (
        manifest_path is not None
        and _readable(manifest_path)
        and (registry := _manifest_registry(manifest_path))
    ):
        merged.update(registry)
        sources.append(str(manifest_path))

    env_overrides = _build_config_env()
    if env_overrides:
        merged.update(env_overrides)
        sources.append(f"environment ({', '.join(sorted(env_overrides))})")

    return BuildConfig(
        engine=merged.get("engine"),
        registry=merged.get("registry"),
        namespace=merged.get("namespace"),
        transcript_dir=merged.get("transcript_dir"),
        sources=tuple(sources),
    )


def _build_config_env() -> dict[str, str]:
    """Read ``CAIRN_<KEY>`` for each of `BUILD_CONFIG_KEYS` (`ADR-042`).

    An unset or empty variable is absent, same as a key missing from a file — no
    validation beyond that is needed, since only recognized keys are ever read.
    """
    values: dict[str, str] = {}
    for key in BUILD_CONFIG_KEYS:
        raw = os.environ.get(f"{BUILD_CONFIG_ENV_PREFIX}{key.upper()}")
        if raw:
            values[key] = raw
    return values


def _manifest_registry(manifest_path: Path) -> dict[str, str]:
    """Read the manifest's ``[cairn.registry]`` table (`BR-CFG-014`, `ADR-039`).

    Read directly from the file rather than from a parsed :class:`Manifest`, so that build
    config does not depend on full manifest validation — a manifest with a bad app list
    should still let ``cairn doctor`` report the engine it would use.

    Only ``host`` and ``namespace`` live here. ``engine`` and ``transcript_dir`` stay
    machine-local, because they describe *this machine*, not the deployment (`BR-CFG-008`).
    """
    data = _load_toml(manifest_path, ManifestInvalidError)
    root = data.get("cairn")
    section = root.get("registry") if isinstance(root, dict) else None
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise ManifestInvalidError(
            f"{manifest_path}: [cairn.registry] must be a table with 'host' and optionally "
            f"'namespace'."
        )

    _reject_unknown(manifest_path, "[cairn.registry]", section, {"host", "namespace"})
    values = {
        "registry": _required_string(manifest_path, "[cairn.registry]", section, "host"),
    }
    if "namespace" in section:
        values["namespace"] = _required_string(
            manifest_path, "[cairn.registry]", section, "namespace"
        )
    return values


def _readable(path: Path) -> bool:
    """Whether *path* is a file we can stat, treating an unreadable one as absent.

    A permission error here must not become a traceback: an unreadable config is the same
    practical fact as a missing one, and the defaults are documented.
    """
    try:
        return path.is_file()
    except OSError:
        return False


def _build_config_values(path: Path) -> dict[str, Any]:
    """Read one build-config file, rejecting unknown or non-string values."""
    data = _load_toml(path, BuildConfigInvalidError)
    unknown = set(data) - set(BUILD_CONFIG_KEYS)
    if unknown:
        raise BuildConfigInvalidError(
            f"{path}: unknown key(s) {', '.join(sorted(unknown))}; "
            f"expected any of {', '.join(BUILD_CONFIG_KEYS)}."
        )
    for key, value in data.items():
        if not isinstance(value, str) or not value.strip():
            raise BuildConfigInvalidError(f"{path}: '{key}' must be a non-empty string.")
    return data


# --- manifest section validation --------------------------------------------


def _image_name(path: Path, root: dict) -> str:
    name = root.get("image_name")
    if not isinstance(name, str) or not name.strip():
        raise ManifestInvalidError(
            f"{path}: [cairn] image_name is required and must be a non-empty string."
        )
    if not _IMAGE_NAME_RE.match(name):
        raise ManifestInvalidError(
            f"{path}: image_name '{name}' is not a valid image name — use lowercase "
            f"letters, digits, and separators (-, _, .), e.g. 'erpnext-v16'."
        )
    return name


def _frappe(path: Path, root: dict) -> Frappe:
    section = root.get("frappe")
    if not isinstance(section, dict):
        raise ManifestInvalidError(
            f"{path}: missing the required [cairn.frappe] table with 'url' and 'ref'."
        )
    _reject_unknown(path, "[cairn.frappe]", section, {"url", "ref"})
    url = _required_string(path, "[cairn.frappe]", section, "url")
    ref = _required_string(path, "[cairn.frappe]", section, "ref")
    _reject_commit_sha(path, "[cairn.frappe]", ref)
    return Frappe(url=url, ref=ref)


def _apps(path: Path, root: dict) -> tuple[App, ...]:
    """Validate ``[[cairn.apps]]``, preserving manifest order verbatim (BR-BUILD-003)."""
    entries = root.get("apps", [])
    if not isinstance(entries, list):
        raise ManifestInvalidError(f"{path}: [[cairn.apps]] must be a list of tables.")

    apps: list[App] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"[[cairn.apps]] #{index + 1}"
        if not isinstance(entry, dict):
            raise ManifestInvalidError(f"{path}: {where} must be a table.")
        _reject_unknown(path, where, entry, {"name", "url", "ref"})
        name = _required_string(path, where, entry, "name")
        ref = _required_string(path, where, entry, "ref")
        _reject_commit_sha(path, where, ref)
        if name in seen:
            raise ManifestInvalidError(
                f"{path}: app '{name}' is listed more than once; each app must appear "
                f"exactly once — the list is an ordered install sequence."
            )
        seen.add(name)
        apps.append(App(name=name, url=_required_string(path, where, entry, "url"), ref=ref))
    return tuple(apps)


def _series(path: Path, root: dict) -> str | None:
    """Validate the optional ``[cairn] series`` (`BR-BUILD-008`, `ADR-032`).

    It becomes part of an image tag, so it must be a legal tag fragment — and it must not
    contain a hyphen, because the tag is ``<series>-<inputhash>`` and the input hash is read
    back by splitting on the *last* hyphen. A series of its own containing one would still
    parse, but it makes the tag ambiguous to a human, which defeats the only purpose the
    legible half has.
    """
    value = root.get("series")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestInvalidError(
            f"{path}: [cairn] series must be a non-empty string naming this line of images, "
            f'e.g. series = "v16".'
        )
    if not _SERIES_RE.match(value):
        raise ManifestInvalidError(
            f"{path}: [cairn] series '{value}' cannot be used in an image tag. Use letters, "
            f"digits, dots and underscores — no hyphens, since the tag reads as "
            f"'<series>-<hash>'."
        )
    return value


def _environment(path: Path, root: dict) -> str | None:
    """Validate the optional ``[cairn] environment`` (`BR-DEPLOY-009a`, `ADR-052`).

    At most one per manifest — its name *is* its registry tag, so it must be a valid one.
    Absent means **this manifest declares no environment**, which is a fact `assign-tag`/
    `retire` act on rather than a gap they fill (`BR-CLI-009`).
    """
    value = root.get("environment")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ManifestInvalidError(
            f"{path}: [cairn] environment must be a non-empty string naming this manifest's "
            f'registry tag, e.g. environment = "production".'
        )
    if not _TAG_RE.match(value):
        raise ManifestInvalidError(
            f"{path}: [cairn] environment '{value}' is not a valid image tag — use letters, "
            f"digits, and separators (-, _, .), up to 128 characters."
        )
    return value


def _build_knobs(path: Path, root: dict) -> dict[str, Any]:
    """Return ``[cairn.build]`` verbatim — known knobs type-checked, the rest passed through."""
    section = root.get("build", {})
    if not isinstance(section, dict):
        raise ManifestInvalidError(f"{path}: [cairn.build] must be a table.")

    expected_types: dict[str, type | tuple[type, ...]] = {
        "python_version": str,
        "node_version": str,
        "install_chromium": bool,
    }
    for key, expected in expected_types.items():
        if key in section and not isinstance(section[key], expected):
            raise ManifestInvalidError(
                f"{path}: [cairn.build] {key} must be a {expected.__name__}."  # type: ignore[union-attr]
            )
    return dict(section)


# --- shared helpers ---------------------------------------------------------


def _load_toml(path: Path, error: type[Exception]) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise error(f"{path}: not valid TOML — {exc}") from exc
    except OSError as exc:
        raise error(f"{path}: cannot be read — {exc}") from exc


def _required_string(path: Path, where: str, section: dict, key: str) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManifestInvalidError(f"{path}: {where} requires '{key}' as a non-empty string.")
    return value


def _reject_unknown(path: Path, where: str, section: dict, allowed: set[str]) -> None:
    """Fail on unrecognized keys so typos surface here, not as a subtly wrong image."""
    unknown = set(section) - allowed
    if unknown:
        raise ManifestInvalidError(
            f"{path}: {where} has unknown key(s) {', '.join(sorted(unknown))}; "
            f"expected any of {', '.join(sorted(allowed))}."
        )


def _reject_commit_sha(path: Path, where: str, ref: str) -> None:
    """Refs pin by branch or tag only; a raw commit SHA is unsupported (BR-BUILD-005)."""
    if _COMMIT_SHA_RE.match(ref):
        raise ManifestInvalidError(
            f"{path}: {where} ref '{ref}' looks like a commit SHA. Pin to a branch or "
            f"tag — cairn resolves it to a commit at build time."
        )
