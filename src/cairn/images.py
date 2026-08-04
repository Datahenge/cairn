"""Local image introspection — what this machine holds, and why (BR-CLI-005, `ADR-032`).

An engine's own listing answers repository, tag, id, age and size. Those five facts cannot
distinguish a superseded build from a build-cache stage from an unrelated orphan, which is
how a build machine accumulates nameless multi-gigabyte images nobody can account for.

Everything needed to account for them is already on the images. `BR-BUILD-011` stamps the
input hash, both tags, the resolved Frappe and app commits, the effective build args, and
the vendored pin onto every image cairn builds. This module reads them back and groups by
**input hash**, so supersession becomes something you can see rather than infer: several
images under one hash are, by definition, the same declared image built more than once.

Two consequences of `--label` semantics are load-bearing here:

* Labels are applied at the **final** commit only, so a multi-stage *stage* image never
  carries them. Identifying cairn's images by label therefore also excludes the build
  cache — the property `BR-CLI-018` depends on to prune without going cold (lessons §12).
* Images cairn did not build are excluded but **counted**, so this is never mistaken for a
  complete inventory of local storage.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from . import registry
from .build import LABEL_NAMESPACE
from .errors import ImageQueryError, RegistryError
from .tagging import MOVING_TAG

#: The label that marks an image as cairn's, and names the inputs it was built from.
INPUT_HASH_LABEL = f"{LABEL_NAMESPACE}.input-hash"
APPS_LABEL = f"{LABEL_NAMESPACE}.apps"
FRAPPE_REF_LABEL = f"{LABEL_NAMESPACE}.frappe.ref"
FRAPPE_COMMIT_LABEL = f"{LABEL_NAMESPACE}.frappe.commit"
PIN_REF_LABEL = f"{LABEL_NAMESPACE}.frappe-docker.ref"

#: The standard OCI creation timestamp (`ADR-030`) — the only clock a registry read has.
CREATED_LABEL = "org.opencontainers.image.created"

#: Sort floor for images whose creation label is absent or unparseable.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)

#: Ceiling on a listing probe; local storage queries are fast or broken, never slow.
QUERY_TIMEOUT_SECONDS = 60

#: Length of a commit shown in the human report.
SHORT_COMMIT = 8


class Provenance:
    """Reads `BR-BUILD-011`'s labels off an image, wherever the image was found.

    Shared by the local and registry reports so the two answer "why does this exist" from
    exactly the same label keys. A label absent is reported as unknown rather than guessed:
    an image cairn did not build has none of these, which is what identifies it as not
    cairn's in the first place.
    """

    labels: dict[str, str]

    @property
    def input_hash(self) -> str:
        return self.labels.get(INPUT_HASH_LABEL, "")

    @property
    def frappe_ref(self) -> str:
        return self.labels.get(FRAPPE_REF_LABEL, "")

    @property
    def frappe_commit(self) -> str:
        return self.labels.get(FRAPPE_COMMIT_LABEL, "")

    @property
    def vendor_pin(self) -> str:
        return self.labels.get(PIN_REF_LABEL, "")

    @property
    def apps(self) -> list[dict[str, str]]:
        """The recorded app list, or empty when the label is absent or unreadable."""
        try:
            parsed = json.loads(self.labels.get(APPS_LABEL, "[]"))
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []

    @property
    def built_at(self) -> datetime | None:
        """When the image was built, per its own label.

        The registry does not report a creation time — only the image does, and only because
        `BR-BUILD-011` stamps it. This is what orders `--latest` and `--previous`.
        """
        return _parse_timestamp(self.labels.get(CREATED_LABEL))


@dataclass(frozen=True)
class LocalImage(Provenance):
    """One image in local storage that cairn built."""

    image_id: str
    tags: tuple[str, ...]
    created: datetime | None
    size: int
    labels: dict[str, str]

    @property
    def short_id(self) -> str:
        return self.image_id.removeprefix("sha256:")[:12]


@dataclass(frozen=True)
class RegistryImage(Provenance):
    """One image in a registry that cairn built, read without pulling (`BR-DEPLOY-005`).

    Keyed by **digest**, not by tag: several tags routinely point at one image — its
    deterministic primary tag, its moving tag, and every environment currently running it —
    and conflating them would report one image several times and make "which environments
    run this" unanswerable.
    """

    digest: str
    tags: tuple[str, ...]
    size: int
    labels: dict[str, str]

    @property
    def short_digest(self) -> str:
        return self.digest.removeprefix("sha256:")[:12]


@dataclass(frozen=True)
class ImageGroup:
    """Every image built from one set of resolved inputs.

    More than one member means the same declared image was built more than once — the
    condition `BR-BUILD-014` exists to prevent.
    """

    input_hash: str
    images: tuple[LocalImage, ...]

    @property
    def newest(self) -> LocalImage:
        return self.images[0]

    @property
    def superseded(self) -> tuple[LocalImage, ...]:
        """Members that no longer hold any tag — former builds, still occupying disk."""
        return tuple(image for image in self.images if not image.tags)

    @property
    def reclaimable(self) -> int:
        return sum(image.size for image in self.superseded)


def inspect_local(engine_name: str) -> tuple[list[LocalImage], int]:
    """Return (cairn's images, count of images cairn did not build).

    Two calls rather than one: engines agree on ``images --quiet`` and on ``image inspect``
    accepting many ids and answering with a JSON array, but disagree on what their listing
    formats include — podman carries labels there, docker does not. Inspecting is the
    portable way to ask the same question of both (`ADR-027`).
    """
    identifiers = _list_ids(engine_name)
    if not identifiers:
        return [], 0

    images = [_from_inspection(entry) for entry in _inspect(engine_name, identifiers)]
    ours = [image for image in images if image.input_hash]
    return _newest_first(ours), len(images) - len(ours)


def group(images: list[LocalImage]) -> list[ImageGroup]:
    """Group *images* by input hash, newest group first, newest member first."""
    buckets: dict[str, list[LocalImage]] = {}
    for image in images:
        buckets.setdefault(image.input_hash, []).append(image)
    return [
        ImageGroup(input_hash=input_hash, images=tuple(_newest_first(members)))
        for input_hash, members in buckets.items()
    ]


def _group_header(tags: tuple[str, ...], input_hash: str) -> str:
    """Return the line identifying one input-hash group (`BR-CLI-005`).

    Leads with a tag — the deterministic primary one if present, since that is what an
    operator recognizes, not a hash — and folds the input hash in parenthetically rather
    than repeating it as the whole line: it is usually already visible as the tag's own
    suffix (`<series>-<hash>`), so restating it up front said little on its own.
    """
    # Local tags are full "repo:tag" refs; registry tags are bare. `rpartition` reads the
    # tag half of either uniformly, so the moving tag is recognized in both.
    primary = next((tag for tag in tags if tag.rpartition(":")[2] != MOVING_TAG), None)
    label = primary or (tags[0] if tags else None)
    if label is None:
        return f"(no current tag — input hash {input_hash})"
    return f"{label}  (input hash {input_hash})"


def render(groups: list[ImageGroup], others: int) -> str:
    """Return the human report: one block per input hash, superseded members marked."""
    if not groups:
        return "\n".join(_footer([], others))

    lines: list[str] = []
    for image_group in groups:
        newest = image_group.newest
        lines.append(_group_header(newest.tags, image_group.input_hash))
        lines.append(
            f"  frappe       {newest.frappe_ref or '?':<16} "
            f"{newest.frappe_commit[:SHORT_COMMIT] or '?'}"
        )
        for app in newest.apps:
            lines.append(
                f"  {app.get('name', '?'):<12} {app.get('ref', '?'):<16} "
                f"{str(app.get('commit', ''))[:SHORT_COMMIT] or '?'}"
            )
        if newest.vendor_pin:
            lines.append(f"  built with vendored base {newest.vendor_pin}")

        for image in image_group.images:
            names = ", ".join(image.tags) if image.tags else "no tags — superseded"
            lines.append(
                f"    {image.short_id}  {format_size(image.size):>9}  "
                f"{format_age(image.created):>8}  {names}"
            )
        lines.append("")

    return "\n".join([*lines, *_footer(groups, others)])


def _footer(groups: list[ImageGroup], others: int) -> list[str]:
    """Summarize totals, and say plainly what this listing does not cover."""
    reclaimable = sum(image_group.reclaimable for image_group in groups)
    superseded = sum(len(image_group.superseded) for image_group in groups)
    built = sum(len(image_group.images) for image_group in groups)

    lines = [
        f"{built} image(s) built by cairn across {len(groups)} input hash(es); "
        f"{superseded} superseded, holding {format_size(reclaimable)}."
    ]
    if others:
        lines.append(
            f"{others} other image(s) in local storage are not cairn's and are not listed "
            f"— including build-cache stages, which must not be deleted."
        )
    return lines


def as_json(groups: list[ImageGroup], others: int) -> str:
    """Return the machine-readable report (`BR-CLI-013`)."""
    return json.dumps(
        {
            "groups": [
                {
                    "input_hash": image_group.input_hash,
                    "frappe": {
                        "ref": image_group.newest.frappe_ref,
                        "commit": image_group.newest.frappe_commit,
                    },
                    "apps": image_group.newest.apps,
                    "images": [
                        {
                            "id": image.image_id,
                            "tags": list(image.tags),
                            "created": image.created.isoformat() if image.created else None,
                            "size": image.size,
                            "superseded": not image.tags,
                        }
                        for image in image_group.images
                    ],
                }
                for image_group in groups
            ],
            "other_images": others,
        },
        indent=2,
    )


# --- the registry (BR-CLI-005 default mode, BR-DEPLOY-005) ------------------


def inspect_registry(base: registry.ImageRef) -> tuple[list[RegistryImage], int]:
    """Return (cairn's images in *base*'s repository, count of images cairn did not build).

    One request per tag, because a tag is the only handle the registry offers and provenance
    lives in each image's config. Tags that resolve to the same digest are folded into one
    image carrying all of them. Nothing is pulled (`BR-DEPLOY-005`).

    A tag that cannot be read is skipped rather than fatal: a repository shared with another
    tool may hold manifests cairn has no business understanding, and one of them must not
    prevent reporting the rest.
    """
    by_digest: dict[str, RegistryImage] = {}
    others = 0

    for tag in registry.tags(base):
        try:
            remote = registry.inspect(base.with_tag(tag))
        except RegistryError:
            others += 1
            continue

        if not remote.labels.get(INPUT_HASH_LABEL):
            others += 1
            continue

        held = by_digest.get(remote.digest)
        tags = (*held.tags, tag) if held else (tag,)
        by_digest[remote.digest] = RegistryImage(
            digest=remote.digest,
            tags=tuple(sorted(tags)),
            size=remote.size,
            labels=remote.labels,
        )

    return _newest_built_first(list(by_digest.values())), others


def group_registry(images: list[RegistryImage]) -> list[tuple[str, list[RegistryImage]]]:
    """Group registry images by input hash, newest group first, newest member first."""
    buckets: dict[str, list[RegistryImage]] = {}
    for image in images:
        buckets.setdefault(image.input_hash, []).append(image)
    return [
        (input_hash, _newest_built_first(members)) for input_hash, members in buckets.items()
    ]


def render_registry(base: registry.ImageRef, groups, others: int) -> str:
    """Return the human report for a registry (`BR-CLI-005`).

    Deliberately not the same report as ``--local``. There is no notion of a *superseded*
    image here: an untagged manifest in a registry is unreferenced, not sitting on someone's
    disk, so what matters remotely is which tags point at which digest — that is what a
    target watches and what a rollback moves.
    """
    if not groups:
        return f"No images cairn built were found in {base.base}."

    lines: list[str] = []
    for input_hash, members in groups:
        newest = members[0]
        lines.append(_group_header(newest.tags, input_hash))
        lines.append(
            f"  frappe       {newest.frappe_ref or '?':<16} "
            f"{newest.frappe_commit[:SHORT_COMMIT] or '?'}"
        )
        for app in newest.apps:
            lines.append(
                f"  {app.get('name', '?'):<12} {app.get('ref', '?'):<16} "
                f"{str(app.get('commit', ''))[:SHORT_COMMIT] or '?'}"
            )
        if newest.vendor_pin:
            lines.append(f"  built with vendored base {newest.vendor_pin}")

        for image in members:
            lines.append(
                f"    {image.short_digest}  {format_size(image.size):>9}  "
                f"{format_age(image.built_at):>8}  {', '.join(image.tags)}"
            )
        lines.append("")

    total = sum(len(members) for _, members in groups)
    lines.append(
        f"{total} image(s) built by cairn in {base.base} across {len(groups)} input hash(es)."
    )
    if others:
        lines.append(f"{others} other tag(s) in the repository are not cairn's and are not listed.")
    lines.append("Sizes are the download size from the registry, not unpacked size on disk.")
    return "\n".join(lines)


def registry_as_json(base: registry.ImageRef, groups, others: int) -> str:
    """Return the machine-readable registry report (`BR-CLI-013`)."""
    return json.dumps(
        {
            "repository": base.base,
            "groups": [
                {
                    "input_hash": input_hash,
                    "frappe": {
                        "ref": members[0].frappe_ref,
                        "commit": members[0].frappe_commit,
                    },
                    "apps": members[0].apps,
                    "images": [
                        {
                            "digest": image.digest,
                            "tags": list(image.tags),
                            "created": image.built_at.isoformat() if image.built_at else None,
                            "size": image.size,
                        }
                        for image in members
                    ],
                }
                for input_hash, members in groups
            ],
            "other_tags": others,
        },
        indent=2,
    )


def _newest_built_first(images: list[RegistryImage]) -> list[RegistryImage]:
    """Order by the image's own creation label; images without one sort last.

    A registry read has no other clock — the registry itself does not say when a manifest was
    written, and tag order is explicitly not meaningful.
    """
    return sorted(
        images,
        key=lambda image: (image.built_at is None, -(image.built_at or _EPOCH).timestamp()),
    )


def format_size(size: int) -> str:
    """Render bytes in the **decimal** units the container engines use.

    Base 1000, not 1024. Both ``podman image list`` and ``docker image ls`` report decimal
    GB, and this command exists to be read alongside them — reporting a binary GB showed
    2.57 where the engine showed 2.75 for the same image, which reads as a bug in whichever
    tool you trust less. Three significant digits matches their output too.
    """
    value = float(size)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.3g} {unit}"
        value /= 1000
    return f"{value:.3g} TB"


def format_age(created: datetime | None) -> str:
    """Render how long ago *created* was, coarsely — precision is not the point here."""
    if created is None:
        return "?"
    seconds = (datetime.now(UTC) - created).total_seconds()
    if seconds < 60:
        return f"{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


# --- engine plumbing --------------------------------------------------------


def _list_ids(engine_name: str) -> list[str]:
    """Return every non-intermediate local image id.

    Intermediate images are excluded by both engines' defaults, and are excluded here for
    the same reason `BR-CLI-018` refuses to prune them: they are cache, not artifacts.
    """
    result = _run([engine_name, "images", "--quiet", "--no-trunc"])
    return list(dict.fromkeys(line.strip() for line in result.stdout.splitlines() if line.strip()))


def _inspect(engine_name: str, identifiers: list[str]) -> list[dict[str, Any]]:
    """Return the engine's inspection of *identifiers* as a list of records."""
    result = _run([engine_name, "image", "inspect", *identifiers])
    try:
        parsed = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise ImageQueryError(
            f"Could not read the image details {engine_name} returned ({exc})."
        ) from exc
    return parsed if isinstance(parsed, list) else [parsed]


def _from_inspection(entry: dict[str, Any]) -> LocalImage:
    """Build a :class:`LocalImage` from one engine inspection record.

    The two engines expose labels in different places — podman at the top level, docker
    under ``Config`` — and both spell ids and sizes slightly differently, so every field is
    read defensively rather than assumed.
    """
    config = entry.get("Config") or {}
    labels = config.get("Labels") or entry.get("Labels") or {}
    tags = entry.get("RepoTags") or []

    return LocalImage(
        image_id=str(entry.get("Id") or entry.get("ID") or ""),
        tags=tuple(tag for tag in tags if tag and not tag.endswith(":<none>")),
        created=_parse_timestamp(entry.get("Created")),
        size=int(entry.get("Size") or 0),
        labels={str(key): str(value) for key, value in labels.items()},
    )


def _parse_timestamp(value: Any) -> datetime | None:
    """Parse an engine timestamp, tolerating nanosecond precision and a trailing Z.

    :func:`datetime.fromisoformat` accepts at most microseconds, while both engines may
    report nanoseconds; the fractional part is truncated rather than the value discarded.
    """
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, tz=UTC)
    if not isinstance(value, str) or not value.strip():
        return None

    text = value.strip().replace("Z", "+00:00")
    if "." in text:
        head, _, tail = text.partition(".")
        digits = "".join(ch for ch in tail if ch.isdigit())[:6]
        suffix = tail[len(digits) :].lstrip("0123456789")
        text = f"{head}.{digits}{suffix}" if digits else f"{head}{suffix}"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _newest_first(images: list[LocalImage]) -> list[LocalImage]:
    """Sort newest first, with undated images last rather than dropped."""
    return sorted(
        images,
        key=lambda image: image.created or datetime.min.replace(tzinfo=UTC),
        reverse=True,
    )


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run *command*, translating every failure mode into :class:`ImageQueryError`."""
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=QUERY_TIMEOUT_SECONDS, check=False
        )
    except FileNotFoundError as exc:
        raise ImageQueryError(f"`{command[0]}` not found on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ImageQueryError(
            f"`{' '.join(command)}` timed out after {QUERY_TIMEOUT_SECONDS}s."
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise ImageQueryError(
            f"`{' '.join(command)}` failed: {detail[0] if detail else 'no output'}."
        )
    return result
