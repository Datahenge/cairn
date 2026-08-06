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

* **The primary tag** (`BR-BUILD-008`) — ``<legible>-<inputhash>``, deterministic.
  ``inputhash`` alone guarantees uniqueness, and covers all resolved commits **plus the
  effective build args**, since two images built from identical sources but different
  Python versions are different images.

  ``legible`` exists purely so a tag is recognizable at a glance, and comes from the
  manifest's declared ``series`` (`ADR-032`, resolved 2026-07-25). It used to be derived
  from the declared Frappe *ref*, which made the tag depend on how the ref was **spelled**
  rather than on what was built: one commit reached by a branch and by a tag produced two
  names for one image, and following `BR-BUILD-005`'s own advice to pin to tags renamed
  every image though nothing about the content changed. A declared series is stable across
  re-pinning, which is the whole point.

  **The legible half never enters the input hash.** It is a label, not an input: changing
  ``series`` must rename future images, not invalidate existing ones or provoke a rebuild.
  Absent a declared ``series`` the old derivation still applies, so a manifest that has not
  adopted it keeps working.
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

#: Marks a build's own not-yet-shared local copy; stripped once a push of it succeeds
#: (`BR-BUILD-018`, `ADR-061`). Never pushed itself — it names a fact about local storage,
#: not a build artifact.
OWNED_TAG = "cairn-build-owned"

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


def legible_slug(frappe_ref: str, series: str | None = None) -> str:
    """Return the human-facing half of the primary tag (BR-BUILD-008, `ADR-032`).

    A declared *series* wins outright: it is the manifest stating, once, what this line of
    images is called, and it stays put when the Frappe ref is re-pinned from a branch to a
    tag.

    Absent one, fall back to deriving it from the declared ref — ``version-16`` → ``v16``,
    anything else sanitized into a tag-safe slug. That fallback is the old behaviour, kept so
    a manifest predating ``series`` keeps producing the names it always did.

    This half carries **no uniqueness guarantee** either way; ``inputhash`` alone does.
    """
    if series:
        return series

    match = _VERSION_REF_RE.match(frappe_ref)
    if match:
        return f"v{match.group(1)}"

    slug = _TAG_UNSAFE_RE.sub("-", frappe_ref).strip("-.")
    return slug or "image"


def primary_tag(
    resolution: Resolution, build_args: dict[str, Any], series: str | None = None
) -> str:
    """Return the deterministic ``<legible>-<inputhash>`` tag (BR-BUILD-008).

    Note that *series* reaches only the legible half — :func:`input_hash` never sees it, so
    renaming a line of images cannot orphan the images already built under the old name.
    """
    legible = legible_slug(resolution.frappe.ref, series)
    return f"{legible}-{input_hash(resolution, build_args)}"


def tags(
    resolution: Resolution, build_args: dict[str, Any], series: str | None = None
) -> tuple[str, str]:
    """Return ``(primary, moving)`` — the deterministic tag and ``latest`` (BR-BUILD-008)."""
    return primary_tag(resolution, build_args, series), MOVING_TAG


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
