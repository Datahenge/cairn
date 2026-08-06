"""Reclaim disk on the build machine, without touching the build cache (BR-CLI-018).

Repeat builds of one manifest used to leave a trail of nameless multi-gigabyte images —
the condition `BR-BUILD-014` now prevents at the source. This command clears what is
already there, and what a deliberate `--rebuild` produces later.

**Three concentric restrictions, and the order matters.**

1. *Only images cairn built.* Candidates come from :func:`cairn.images.inspect_local`,
   which admits an image only if it carries cairn's own provenance labels. Since `--label`
   values are applied at the **final** commit, a multi-stage *stage* image never has them —
   so the owned Containerfile's `builder` stage, the thing that lets a rebuild skip
   `bench init`, is outside this command's reach by construction rather than by care
   (lessons §12). This is why the selection is never written against "dangling": on podman
   an untagged image may be cache, and deleting it silently converts every later build into
   a cold one.
2. *Never an image that has been shared.* An image carrying any tag other than the
   ``cairn-build-owned`` marker (`BR-BUILD-018`) has been pushed — or predates the marker,
   treated the same way out of caution — and is never this command's to remove. Everything
   else is eligible: an image still carrying only the owned marker (built here, shared
   nowhere), and a fully untagged image (an orphaned duplicate rebuild whose tags, marker
   included, already moved to a newer image under the same input hash). Removing an eligible
   image never needs the engine's ``--force`` — cairn never passes it — but a still-owned
   image usually carries several live tags at once (primary, moving, marker), and engines
   refuse to remove a multiply-tagged image by id without forcing it; so removal drops each
   tag reference in turn, the last one being what actually frees the disk (`ADR-061`).
3. *Only beyond the newest `keep` of each input hash.* A grace window for a build that
   might still be pushed any moment, not rollback headroom — build-machine storage carries
   no such guarantee; a registry is what that promise belongs to. `keep` counts a group's
   newest members regardless of ownership status, so a stale-but-recent orphan still gets
   the same grace a stale-but-recent owned image does. Applied per input hash because images
   under different hashes are different images and not each other's history.

Volumes and containers are never touched under any option (`ADR-022`).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

from .errors import ImageQueryError
from .images import ImageGroup, LocalImage, format_size

#: Ceiling on one removal; deleting a layer tree is disk-bound but not unbounded.
REMOVE_TIMEOUT_SECONDS = 300


@dataclass(frozen=True)
class PrunePlan:
    """What a prune would remove, and what it deliberately would not."""

    removals: tuple[LocalImage, ...]
    kept: tuple[LocalImage, ...]
    protected: tuple[LocalImage, ...]

    @property
    def reclaimable(self) -> int:
        return sum(image.size for image in self.removals)

    @property
    def is_empty(self) -> bool:
        return not self.removals


def select(groups: list[ImageGroup], keep: int) -> PrunePlan:
    """Decide what to remove: never-shared images beyond the newest *keep* of their group.

    *keep* counts a group's newest members regardless of ownership status, so ``--keep 2``
    leaves the current image plus one predecessor as a grace window before either is
    considered stale enough to reclaim (`BR-BUILD-018`, `ADR-061`).
    """
    if keep < 1:
        raise ValueError("keep must be at least 1")

    removals: list[LocalImage] = []
    kept: list[LocalImage] = []
    protected: list[LocalImage] = []

    for group in groups:
        for position, image in enumerate(group.images):
            if position < keep:
                kept.append(image)
            elif not image.is_owned and image.tags:
                protected.append(image)  # pushed and kept, or predates the marker
            else:
                removals.append(image)  # still owned, or a fully untagged orphan

    return PrunePlan(removals=tuple(removals), kept=tuple(kept), protected=tuple(protected))


def render(plan: PrunePlan, others: int) -> str:
    """Return the report shown before anything is removed (`BR-CLI-011`)."""
    if plan.is_empty:
        return "\n".join(
            [
                f"Nothing to remove: {len(plan.kept)} image(s) kept, none stale and unshared.",
                *_safety_note(plan, others),
            ]
        )

    lines = [f"Will remove {len(plan.removals)} image(s) never shared to a registry:"]
    lines += [
        f"  {image.short_id}  {format_size(image.size):>9}  input hash {image.input_hash}  "
        f"{', '.join(image.tags) if image.tags else 'no tags'}"
        for image in plan.removals
    ]
    lines.append(f"Reclaims {format_size(plan.reclaimable)}.")
    lines.append("")
    lines += [f"Keeping {len(plan.kept)} image(s) within the grace window."]
    lines += _safety_note(plan, others)
    return "\n".join(lines)


def _safety_note(plan: PrunePlan, others: int) -> list[str]:
    """State plainly what is being left alone, so the omission is never a surprise."""
    lines: list[str] = []
    if plan.protected:
        lines.append(
            f"{len(plan.protected)} older image(s) have already been pushed (or predate "
            f"cairn's ownership marker) and are left alone."
        )
    if others:
        lines.append(
            f"{others} image(s) cairn did not build are never considered — this includes "
            f"build-cache layers, which is why removing them here would make later builds "
            f"start from nothing."
        )
    return lines


def remove(engine_name: str, doomed: tuple[LocalImage, ...]) -> tuple[list[LocalImage], list[str]]:
    """Remove *doomed* one at a time, returning (removed, failure messages).

    One image per invocation so a single refusal — an image held by a stopped container,
    say — costs only that image rather than aborting the rest. The engine's ``--force`` is
    never passed: a removal that needs forcing is one cairn should report, not perform.

    A still-owned removal candidate usually carries several live tags at once (primary,
    moving, the ownership marker — `BR-BUILD-008`, `BR-BUILD-018`), and both engines refuse
    ``image rm <id>`` on a multiply-tagged image without ``--force``: removing "the image" by
    id when several names still point at it is treated as ambiguous. So each of an image's
    own tag references is removed in turn instead — the last one is what actually frees the
    disk — falling back to id-based removal only for an image with no tags at all
    (`ADR-061`).
    """
    removed: list[LocalImage] = []
    failures: list[str] = []

    for image in doomed:
        refs = image.tags or (image.image_id,)
        failure: str | None = None

        for ref in refs:
            command = [engine_name, "image", "rm", ref]
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=REMOVE_TIMEOUT_SECONDS,
                    check=False,
                )
            except FileNotFoundError as exc:
                raise ImageQueryError(f"`{engine_name}` not found on PATH.") from exc
            except subprocess.TimeoutExpired:
                failure = f"{image.short_id}: timed out after {REMOVE_TIMEOUT_SECONDS}s"
                break

            if result.returncode != 0:
                detail = result.stderr.strip().splitlines()
                failure = f"{image.short_id}: {detail[0] if detail else 'removal failed'}"
                break

        if failure:
            failures.append(failure)
        else:
            removed.append(image)

    return removed, failures
