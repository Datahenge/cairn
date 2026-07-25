"""Reclaim disk on the build machine, without touching the build cache (BR-CLI-018).

Repeat builds of one manifest used to leave a trail of nameless multi-gigabyte images —
the condition `BR-BUILD-014` now prevents at the source. This command clears what is
already there, and what a deliberate `--rebuild` produces later.

**Three concentric restrictions, and the order matters.**

1. *Only images cairn built.* Candidates come from :func:`cairn.images.inspect_local`,
   which admits an image only if it carries cairn's own provenance labels. Since `--label`
   values are applied at the **final** commit, a multi-stage *stage* image never has them —
   so the vendored Containerfile's `builder` stage, the thing that lets a rebuild skip
   `bench init`, is outside this command's reach by construction rather than by care
   (lessons §12). This is why the selection is never written against "dangling": on podman
   an untagged image may be cache, and deleting it silently converts every later build into
   a cold one.
2. *Only untagged images.* A tag is a name something else may be relying on — a deploy, a
   push, a rollback. Removing a tagged image would also need the engine's ``--force``,
   which is precisely the flag that makes an accident possible; cairn never passes it.
3. *Only beyond the newest `keep` of each input hash.* Mirrors `BR-DEPLOY-006`'s
   keep-last-N rollback headroom, applied per input hash rather than globally, because
   images under different hashes are different images and not each other's history.

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
    """Decide what to remove: untagged images beyond the newest *keep* of their group.

    *keep* counts a group's newest members regardless of whether they carry tags, so
    ``--keep 2`` leaves the current image plus one predecessor as rollback headroom.
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
            elif image.tags:
                protected.append(image)
            else:
                removals.append(image)

    return PrunePlan(removals=tuple(removals), kept=tuple(kept), protected=tuple(protected))


def render(plan: PrunePlan, others: int) -> str:
    """Return the report shown before anything is removed (`BR-CLI-011`)."""
    if plan.is_empty:
        return "\n".join(
            [
                f"Nothing to remove: {len(plan.kept)} image(s) kept, none superseded.",
                *_safety_note(plan, others),
            ]
        )

    lines = [f"Will remove {len(plan.removals)} superseded image(s):"]
    lines += [
        f"  {image.short_id}  {format_size(image.size):>9}  input hash {image.input_hash}  no tags"
        for image in plan.removals
    ]
    lines.append(f"Reclaims {format_size(plan.reclaimable)}.")
    lines.append("")
    lines += [f"Keeping {len(plan.kept)} image(s), including everything still tagged."]
    lines += _safety_note(plan, others)
    return "\n".join(lines)


def _safety_note(plan: PrunePlan, others: int) -> list[str]:
    """State plainly what is being left alone, so the omission is never a surprise."""
    lines: list[str] = []
    if plan.protected:
        lines.append(f"{len(plan.protected)} older image(s) still carry tags and are left alone.")
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
    """
    removed: list[LocalImage] = []
    failures: list[str] = []

    for image in doomed:
        command = [engine_name, "image", "rm", image.image_id]
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
            failures.append(f"{image.short_id}: timed out after {REMOVE_TIMEOUT_SECONDS}s")
            continue

        if result.returncode == 0:
            removed.append(image)
        else:
            detail = result.stderr.strip().splitlines()
            failures.append(f"{image.short_id}: {detail[0] if detail else 'removal failed'}")

    return removed, failures
