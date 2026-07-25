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

from .build import LABEL_NAMESPACE
from .errors import ImageQueryError

#: The label that marks an image as cairn's, and names the inputs it was built from.
INPUT_HASH_LABEL = f"{LABEL_NAMESPACE}.input-hash"
APPS_LABEL = f"{LABEL_NAMESPACE}.apps"
FRAPPE_REF_LABEL = f"{LABEL_NAMESPACE}.frappe.ref"
FRAPPE_COMMIT_LABEL = f"{LABEL_NAMESPACE}.frappe.commit"
PIN_REF_LABEL = f"{LABEL_NAMESPACE}.frappe-docker.ref"

#: Ceiling on a listing probe; local storage queries are fast or broken, never slow.
QUERY_TIMEOUT_SECONDS = 60

#: Length of a commit shown in the human report.
SHORT_COMMIT = 8


@dataclass(frozen=True)
class LocalImage:
    """One image in local storage that cairn built."""

    image_id: str
    tags: tuple[str, ...]
    created: datetime | None
    size: int
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
    def short_id(self) -> str:
        return self.image_id.removeprefix("sha256:")[:12]


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


def render(groups: list[ImageGroup], others: int) -> str:
    """Return the human report: one block per input hash, superseded members marked."""
    if not groups:
        return "\n".join(_footer([], others))

    lines: list[str] = []
    for image_group in groups:
        newest = image_group.newest
        lines.append(f"input hash {image_group.input_hash}")
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
            lines.append(f"  frappe_docker {newest.vendor_pin}")

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
