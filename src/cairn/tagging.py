"""Derive the cache bust and the image tags from resolved inputs.

Both values are pure functions of the resolution (`resolve.Resolution`) plus the
effective build args, so the same declared inputs always produce the same tag — cairn's
input-determinism guarantee (`BR-BUILD-013`).

* **`CACHE_BUST`** (`BR-BUILD-007`) — a hash of **all** resolved commits, Frappe and every
  app. It exists because a build secret's contents are excluded from the layer cache key
  by design, so editing ``apps.json`` alone will not invalidate the ``bench init`` layer;
  and because ``FRAPPE_BRANCH`` enters the cache key by *name*, so a branch that moves
  would otherwise reuse a stale layer. Build args are deliberately **not** included: they
  are ordinary build-args and already participate in the cache key natively.

* **The primary tag** (`BR-BUILD-008`) — ``<legible>-<inputhash>``, immutable. ``legible``
  is a slug of the Frappe ref (``version-16`` → ``v16``) for human recognition only;
  ``inputhash`` alone guarantees uniqueness, and covers all resolved commits **plus the
  effective build args**, since two images built from identical sources but different
  Python versions are different images.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from .resolve import Resolution

#: Length of the short hex digest carried in tags and CACHE_BUST.
DIGEST_LENGTH = 12

#: The moving convenience tag applied alongside the immutable one (`BR-BUILD-008`).
MOVING_TAG = "latest"

_VERSION_REF_RE = re.compile(r"^version-(\d+)$")
_TAG_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def cache_bust(resolution: Resolution) -> str:
    """Return the ``CACHE_BUST`` build-arg value for *resolution* (BR-BUILD-007)."""
    return _digest(_commit_lines(resolution))


def input_hash(resolution: Resolution, build_args: dict[str, Any]) -> str:
    """Return the short hash of every resolved input (BR-BUILD-008).

    Covers the resolved commits and the **effective** build args — including values that
    came from Containerfile defaults rather than the manifest (`BR-BUILD-010`), so an
    upstream default change yields a different tag.
    """
    lines = [*_commit_lines(resolution), *_build_arg_lines(build_args)]
    return _digest(lines)


def legible_slug(frappe_ref: str) -> str:
    """Return the human-facing half of the primary tag (BR-BUILD-008).

    ``version-16`` → ``v16``; any other ref is sanitized into a tag-safe slug. This half
    carries no uniqueness guarantee — it exists so a tag is recognizable at a glance.
    """
    match = _VERSION_REF_RE.match(frappe_ref)
    if match:
        return f"v{match.group(1)}"

    slug = _TAG_UNSAFE_RE.sub("-", frappe_ref).strip("-.")
    return slug or "image"


def primary_tag(resolution: Resolution, build_args: dict[str, Any]) -> str:
    """Return the immutable ``<legible>-<inputhash>`` tag (BR-BUILD-008)."""
    return f"{legible_slug(resolution.frappe.ref)}-{input_hash(resolution, build_args)}"


def tags(resolution: Resolution, build_args: dict[str, Any]) -> tuple[str, str]:
    """Return ``(primary, moving)`` — the immutable tag and ``latest`` (BR-BUILD-008)."""
    return primary_tag(resolution, build_args), MOVING_TAG


def _commit_lines(resolution: Resolution) -> list[str]:
    """Render resolved commits as stable ``name=commit`` lines, in manifest order.

    Order is fixed by the manifest (`BR-BUILD-003`), and the name is included so that
    swapping two apps' URLs changes the hash even when the commit set is unchanged.
    """
    return [f"{ref.name}={ref.commit}" for ref in resolution.all_refs]


def _build_arg_lines(build_args: dict[str, Any]) -> list[str]:
    """Render build args as sorted ``key=value`` lines.

    Sorted because the manifest's ``[cairn.build]`` table is a mapping, not a sequence:
    reordering keys in the TOML must not change the image identity.
    """
    return [f"{key}={build_args[key]}" for key in sorted(build_args)]


def _digest(lines: list[str]) -> str:
    """Return a short, stable digest of *lines*.

    Lines are newline-joined and the list is terminated, so no combination of values can
    be re-partitioned into a different list with the same digest.
    """
    payload = "".join(f"{line}\n" for line in lines)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
