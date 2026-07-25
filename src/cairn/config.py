"""The manifest (``cairn.toml``) and local build configuration.

Two orthogonal files, deliberately kept apart (`BR-CFG-008`):

* **`cairn.toml`** — the portable manifest. *What image to build*: one
  environment-agnostic image, its Frappe source, its ordered app list, and the build
  knobs (`BR-BUILD-001/002/003`). Shareable; carries no registry or machine settings.
* **build config** — `~/.config/cairn/config.toml`, optionally overridden key-by-key by
  a `cairn.local.toml` beside the manifest. *Where and how this machine builds*: engine
  (`ADR-027`), registry, namespace (`BR-CFG-009/011`). Never committed with a shared
  deployment.

Discovery precedence is `BR-CFG-012`; the manifest root is resolved independently of
cairn's own project root (`ADR-029`).

Validation is strict on purpose: every table but ``[cairn.build]`` rejects unknown keys,
so a typo fails at parse time with a message naming the key rather than producing a
subtly wrong image an hour later. ``[cairn.build]`` is the documented exception —
`BR-BUILD-002` grants it passthrough for the long tail (``debian_base``,
``wkhtmltopdf_*``).
"""

from __future__ import annotations

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
LOCAL_CONFIG_NAME = "cairn.local.toml"
USER_CONFIG_PATH = Path("~/.config/cairn/config.toml")

#: Build knobs cairn maps to named build-args; anything else rides the passthrough.
KNOWN_BUILD_KNOBS = ("python_version", "node_version", "install_chromium")

#: Recognized build-config keys. Builder/cache settings land with the BUILD module.
BUILD_CONFIG_KEYS = ("engine", "registry", "namespace", "image_base", "transcript_dir")

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

    ``environments`` is the declared environment list (`BR-DEPLOY-009a`, `ADR-033`): the
    control-side source of truth for which environments exist, mapping environment name to
    the registry tag that serves as its desired-state pointer. No build reads it, and no
    environment name reaches the image — the image is promoted between environments, not
    built per environment.
    """

    image_name: str
    frappe: Frappe
    apps: tuple[App, ...]
    build: dict[str, Any] = field(default_factory=dict)
    series: str | None = None
    environments: dict[str, str] = field(default_factory=dict)
    path: Path | None = None


@dataclass(frozen=True)
class BuildConfig:
    """Machine-local build settings; absent values fall back to documented defaults."""

    engine: str | None = None
    registry: str | None = None
    namespace: str | None = None
    image_base: str | None = None
    transcript_dir: str | None = None
    sources: tuple[Path, ...] = ()

    def resolve_image_base(self, image_name: str) -> str:
        """Return the image base for *image_name* (`BR-CFG-011`, `BR-BUILD-008`).

        An explicit ``image_base`` wins. With a registry configured the base is
        ``<registry>/<namespace>/<image_name>``; absent one the image stays local as
        ``cairn/<image_name>``.
        """
        if self.image_base:
            return self.image_base
        if self.registry:
            parts = [self.registry, *([self.namespace] if self.namespace else []), image_name]
            return "/".join(parts)
        return f"{LOCAL_IMAGE_PREFIX}/{image_name}"


# --- discovery (BR-CFG-012) -------------------------------------------------


def find_manifest(start: Path | None = None, explicit: Path | None = None) -> Path:
    """Locate the manifest: *explicit* if given, else the nearest ``cairn.toml`` upward.

    Searching upward from the working directory — not from cairn's own project root —
    is what lets a `pip install`-ed cairn operate on a deployment directory (`ADR-029`).
    """
    if explicit is not None:
        path = explicit.expanduser()
        if not path.is_file():
            raise ManifestNotFoundError(f"No manifest at {path}.")
        return path

    start = (start or Path.cwd()).resolve()
    for directory in (start, *start.parents):
        candidate = directory / MANIFEST_NAME
        if candidate.is_file():
            return candidate
    raise ManifestNotFoundError(
        f"No {MANIFEST_NAME} found at or above {start}. "
        f"Create one, or point at it with --manifest <path>."
    )


def find_manifest_or_none(start: Path | None = None) -> Path | None:
    """Return the nearest manifest, or None where a command does not require one.

    Machine-scoped commands (`BR-CLI-005`'s ``--local``) still want build config, whose
    lower layer is the user file and whose upper layer is a ``cairn.local.toml`` beside a
    manifest. Missing the manifest costs only that upper layer, not the command.
    """
    try:
        return find_manifest(start)
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
        {"image_name", "frappe", "apps", "build", "series", "registry", "environments"},
    )
    return Manifest(
        image_name=_image_name(path, root),
        frappe=_frappe(path, root),
        apps=_apps(path, root),
        build=_build_knobs(path, root),
        series=_series(path, root),
        environments=_environments(path, root),
        path=path,
    )


def load_build_config(manifest_path: Path | None = None) -> BuildConfig:
    """Layer machine defaults, the manifest's registry, then ``cairn.local.toml``.

    Three layers, lowest precedence first (`BR-CFG-012`, `ADR-039`):

    1. ``~/.config/cairn/config.toml`` — machine-wide defaults, e.g. the engine.
    2. the manifest's ``[cairn.registry]`` — **where this deployment's images belong**.
       Committed with the deployment, because under `BR-CFG-013` that registry is usually
       the *client's*, and a coordinate known only to one laptop is a coordinate the client
       cannot take over.
    3. ``cairn.local.toml`` beside the manifest — the deliberate local override, for
       experiments and for publishing a client's deployment somewhere else temporarily.

    All three are optional; with none present the config is all-defaults and images stay
    local (`BR-CFG-011`). Every override is key-by-key, so a local file naming only
    ``namespace`` keeps the engine from layer 1 and the host from layer 2.
    """
    merged: dict[str, Any] = {}
    sources: list[Path] = []

    user_config = USER_CONFIG_PATH.expanduser()
    if _readable(user_config):
        merged.update(_build_config_values(user_config))
        sources.append(user_config)

    if manifest_path is not None:
        # The registry layer needs the manifest itself; the local file needs only its
        # directory. Keeping these separate matters: `cairn.local.toml` beside a manifest
        # that does not exist yet is still the machine's configuration for that directory.
        if _readable(manifest_path) and (registry := _manifest_registry(manifest_path)):
            merged.update(registry)
            sources.append(manifest_path)

        local = manifest_path.parent / LOCAL_CONFIG_NAME
        if _readable(local):
            merged.update(_build_config_values(local))
            sources.append(local)

    return BuildConfig(
        engine=merged.get("engine"),
        registry=merged.get("registry"),
        namespace=merged.get("namespace"),
        image_base=merged.get("image_base"),
        transcript_dir=merged.get("transcript_dir"),
        sources=tuple(sources),
    )


def _manifest_registry(manifest_path: Path) -> dict[str, str]:
    """Read the manifest's ``[cairn.registry]`` table (`BR-CFG-014`, `ADR-039`).

    Read directly from the file rather than from a parsed :class:`Manifest`, so that build
    config does not depend on full manifest validation — a manifest with a bad app list
    should still let ``cairn doctor`` report the engine it would use.

    Only ``host`` and ``namespace`` live here. ``engine``, ``image_base`` and
    ``transcript_dir`` stay machine-local, because they describe *this machine*, not the
    deployment (`BR-CFG-008`).
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
            f"letters, digits, and separators (-, _, .), e.g. 'erpnext-btu-v16'."
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


def _environments(path: Path, root: dict) -> dict[str, str]:
    """Validate the optional ``[cairn.environments]`` table (`BR-DEPLOY-009a`, `ADR-033`).

    Environment name → registry tag. Absent or empty means **no environment exists**, which
    is a fact the pointer verbs act on rather than a gap they fill (`BR-CLI-009`).

    Two environments pointing at one tag is rejected: the tag *is* the desired-state pointer
    (`BR-DEPLOY-002`), so sharing one would make two environments impossible to move
    independently — a retag of either would silently deploy to both.
    """
    section = root.get("environments", {})
    if not isinstance(section, dict):
        raise ManifestInvalidError(
            f"{path}: [cairn.environments] must be a table mapping environment name to "
            f"registry tag, e.g. production = \"production\"."
        )

    environments: dict[str, str] = {}
    claimed: dict[str, str] = {}
    for name, tag in section.items():
        if not isinstance(tag, str) or not tag.strip():
            raise ManifestInvalidError(
                f"{path}: [cairn.environments] '{name}' must name a registry tag as a "
                f"non-empty string."
            )
        if not _TAG_RE.match(tag):
            raise ManifestInvalidError(
                f"{path}: [cairn.environments] '{name}' tag '{tag}' is not a valid image "
                f"tag — use letters, digits, and separators (-, _, .), up to 128 characters."
            )
        if tag in claimed:
            raise ManifestInvalidError(
                f"{path}: [cairn.environments] '{name}' and '{claimed[tag]}' both point at "
                f"the tag '{tag}'. Each environment needs its own tag — the tag is what a "
                f"target watches, so sharing one would deploy to both at once."
            )
        claimed[tag] = name
        environments[name] = tag
    return environments


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
