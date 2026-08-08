"""Reclaim disk on the target machine, without touching what's running (BR-CLI-028, ADR-072).

`cairn-adopt` marks every image it has ever run with a fixed local tag, `cairn-adopt-owned`
(`BR-DEPLOY-023`), refreshed on the currently-running image every `reconcile` pass. This
command is the only thing that ever removes it — `cairn-build prune` (`BR-CLI-018`) excludes
these images entirely, on the understanding that reclaiming them is this command's job, not
its own.

Selection has two tiers, not `cairn-build prune`'s three: a target runs one image at a time,
so there is one running image to protect unconditionally — read the same way
`BR-DEPLOY-003b` already does, off the running container, never merely "the newest by
recency" — and a flat recency order for everything else. Removal mechanics are shared with
`cairn-build prune` (:func:`cairn.prune.remove`) rather than duplicated: the multiply-tagged,
no-``--force`` reasoning is identical on either role.
"""

from __future__ import annotations

from dataclasses import dataclass

from .images import LocalImage, format_size


@dataclass(frozen=True)
class AdoptPrunePlan:
    """What an adopt prune would remove, and what it deliberately keeps."""

    removals: tuple[LocalImage, ...]
    kept: tuple[LocalImage, ...]
    running: LocalImage | None

    @property
    def reclaimable(self) -> int:
        return sum(image.size for image in self.removals)

    @property
    def is_empty(self) -> bool:
        return not self.removals


def select(images: list[LocalImage], running_image_id: str | None, keep: int) -> AdoptPrunePlan:
    """Decide what to remove: every `cairn-adopt-owned` image but the running one and the
    newest *keep* of the rest.

    *running_image_id* is unconditionally protected regardless of position or `--keep` — the
    image the target's `backend` container was actually started from (`BR-DEPLOY-003b`), not
    a guess from recency. A rollback can leave the running image older than one already
    superseded, which is exactly why recency alone must never decide this one.
    """
    if keep < 1:
        raise ValueError("keep must be at least 1")

    running = next((image for image in images if image.image_id == running_image_id), None)
    rest = [image for image in images if image is not running]

    kept = tuple(rest[:keep])
    removals = tuple(rest[keep:])

    return AdoptPrunePlan(removals=removals, kept=kept, running=running)


def render(plan: AdoptPrunePlan, others: int) -> str:
    """Return the report shown before anything is removed (`BR-CLI-011`)."""
    if plan.is_empty:
        return "\n".join(
            [
                f"Nothing to remove: {len(plan.kept)} image(s) kept for rollback headroom.",
                *_safety_note(plan, others),
            ]
        )

    lines = [f"Will remove {len(plan.removals)} image(s) this host previously ran:"]
    lines += [
        f"  {image.short_id}  {format_size(image.size):>9}  input hash {image.input_hash}  "
        f"{', '.join(image.tags) if image.tags else 'no tags'}"
        for image in plan.removals
    ]
    lines.append(f"Reclaims {format_size(plan.reclaimable)}.")
    lines.append("")
    lines.append(f"Keeping {len(plan.kept)} image(s) for rollback headroom.")
    lines += _safety_note(plan, others)
    return "\n".join(lines)


def _safety_note(plan: AdoptPrunePlan, others: int) -> list[str]:
    """State plainly what is being left alone, so the omission is never a surprise."""
    lines: list[str] = []
    if plan.running:
        lines.append(f"Currently running: {plan.running.short_id}. Never removed.")
    else:
        lines.append("Nothing is currently running on this host, per the compose stack.")
    if others:
        lines.append(
            f"{others} other image(s) in local storage are not cairn-adopt's and are not "
            f"listed — including anything `cairn-build` produced here itself."
        )
    return lines
