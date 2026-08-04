"""The registry retention algorithm (`BR-REG-006`/`007`/`008`, `ADR-048`).

Decides which registry digests are safe to delete, without ever reading a manifest or
`[cairn.environments]` (`BR-REG-001`) — every fact this module needs comes from the
registry's own tag list.

**The safety rule, in one sentence:** a digest is eligible only if *every* tag currently
pointing at it matches cairn's own disposable content-hash shape
(`<series>-<12-hex-inputhash>`, `BR-BUILD-008`). A digest still carrying a moving series tag
or a declared-environment tag — either a plain, non-hash-shaped name — is categorically
protected. An environment tag is created by `retag()`'s server-side manifest copy onto the
*same* digest a content-hash tag already names (`registry.py`), so it always shows up in this
same per-digest tag list; no `cairn.toml` needs to be read to know that.

Structured like `prune.py` on purpose — same three-part shape (`select` → `render` → act) for
the same reason: `--dry-run` must be able to stop after the report, before anything mutates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .errors import RegistryError
from .registry import ImageRef, delete_digest, digest_of, inspect, tags

#: cairn's own disposable content-hash tag shape (`BR-BUILD-008`): `<series>-<12-hex-hash>`.
#: The *only* shape retention is ever allowed to consider — everything else (a moving series
#: tag like `v16`, a declared environment tag like `production`) is categorically protected,
#: and that protection is a code invariant here, not a configuration choice (`BR-REG-007`).
CONTENT_HASH_TAG_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._]{0,63}-[0-9a-f]{12}$")

#: The OCI creation label every cairn build stamps (`BR-BUILD-011`) — the only clock a
#: registry read has. cairn always writes it as `%Y-%m-%dT%H:%M:%SZ` (`build.py`), so parsing
#: it needs none of `images.py`'s tolerance for other engines' timestamp formats — and
#: `images.py` cannot be imported here regardless (`BR-REG-001`: it reaches `config.py` via
#: `build.py`).
CREATED_LABEL = "org.opencontainers.image.created"

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Candidate:
    """One digest in a repository: every tag pointing at it, and when it was built."""

    digest: str
    tags: tuple[str, ...]
    created: datetime | None

    @property
    def short_digest(self) -> str:
        return self.digest.removeprefix("sha256:")[:12]

    @property
    def is_protected(self) -> bool:
        """Whether *any* tag on this digest is not cairn's disposable content-hash shape."""
        return not all(CONTENT_HASH_TAG_RE.match(tag) for tag in self.tags)


@dataclass(frozen=True)
class RetentionPlan:
    """What retention would delete, and what it deliberately would not — mirrors
    `prune.PrunePlan`'s three-way split."""

    deletions: tuple[Candidate, ...]
    kept_by_floor: tuple[Candidate, ...]
    kept_by_age: tuple[Candidate, ...]
    protected: tuple[Candidate, ...]

    @property
    def is_empty(self) -> bool:
        return not self.deletions


def candidates(base: ImageRef) -> list[Candidate]:
    """Enumerate every digest in *base*'s repository, with its tags and creation time.

    One `digest_of` call per tag (cheap: a single manifest fetch, no blob). The creation
    label is fetched only for digests that turn out eligible — a protected digest's age is
    never relevant to anything, so the extra blob fetch `inspect()` costs is skipped for it.
    """
    by_digest: dict[str, list[str]] = {}
    for tag in tags(base):
        digest = digest_of(base.with_tag(tag))
        by_digest.setdefault(digest, []).append(tag)

    result: list[Candidate] = []
    for digest, tag_names in by_digest.items():
        ordered = tuple(sorted(tag_names))
        eligible_shape = all(CONTENT_HASH_TAG_RE.match(tag) for tag in ordered)
        created = _created_at(base, ordered[0]) if eligible_shape else None
        result.append(Candidate(digest=digest, tags=ordered, created=created))
    return result


def select(items: list[Candidate], *, keep_last: int, max_age_days: int) -> RetentionPlan:
    """Apply `BR-REG-006`'s algorithm: protect by tag shape, then floor, then age.

    *keep_last* counts only eligible digests — a protected one (an environment or the moving
    tag) is never part of the rollback-headroom floor; it is not rollback headroom, it is a
    live pointer.
    """
    if keep_last < 1:
        raise ValueError("keep_last must be at least 1")

    protected = [item for item in items if item.is_protected]
    eligible = _newest_first([item for item in items if not item.is_protected])

    floor = eligible[:keep_last]
    remainder = eligible[keep_last:]

    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)
    deletions = [item for item in remainder if item.created is not None and item.created < cutoff]
    kept_by_age = [item for item in remainder if item not in deletions]

    return RetentionPlan(
        deletions=tuple(deletions),
        kept_by_floor=tuple(floor),
        kept_by_age=tuple(kept_by_age),
        protected=tuple(protected),
    )


def render(plan: RetentionPlan) -> str:
    """Return the report shown before anything is deleted (`BR-CLI-011`)."""
    lines: list[str] = []
    if plan.is_empty:
        lines.append("Nothing to delete.")
    else:
        lines.append(f"Will delete {len(plan.deletions)} digest(s):")
        lines += [
            f"  {item.short_digest}  {_age(item.created):>4}  {', '.join(item.tags)}"
            for item in plan.deletions
        ]
    lines.append(
        f"Keeping {len(plan.kept_by_floor)} image(s) as rollback headroom, "
        f"{len(plan.kept_by_age)} under the age ceiling."
    )
    if plan.protected:
        lines.append(
            f"{len(plan.protected)} digest(s) carry a moving or environment tag and are "
            f"never considered for deletion, regardless of age."
        )
    return "\n".join(lines)


def delete(base: ImageRef, plan: RetentionPlan) -> tuple[list[Candidate], list[str]]:
    """Delete every digest *plan* selected, one at a time (returning (deleted, failures)).

    One request per digest so a single refusal costs only that digest rather than aborting
    the rest — same posture as `prune.remove`.
    """
    deleted: list[Candidate] = []
    failures: list[str] = []
    for item in plan.deletions:
        try:
            delete_digest(base, item.digest)
        except RegistryError as exc:
            failures.append(f"{item.short_digest}: {exc}")
        else:
            deleted.append(item)
    return deleted, failures


def _created_at(base: ImageRef, tag: str) -> datetime | None:
    try:
        remote = inspect(base.with_tag(tag))
    except RegistryError:
        return None
    return _parse_created(remote.labels.get(CREATED_LABEL))


def _parse_created(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


def _newest_first(items: list[Candidate]) -> list[Candidate]:
    """Rank by creation label, undated candidates last — never assumed newest."""
    return sorted(
        items,
        key=lambda item: (item.created is None, -(item.created or _EPOCH).timestamp()),
    )


def _age(created: datetime | None) -> str:
    if created is None:
        return "?"
    days = (datetime.now(UTC) - created).days
    return f"{days}d"
