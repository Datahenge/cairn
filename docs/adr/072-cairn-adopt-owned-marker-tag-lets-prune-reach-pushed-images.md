---
status: authoritative
owner: technical
purpose: ADR-072 — a symmetric cairn-adopt-owned marker tag lets cairn-build prune reach pushed images a colocated target no longer needs
---

# ADR-072 — a `cairn-adopt-owned` marker tag lets `cairn-build prune` reach pushed images

**Decided:** 2026-08-08 (Brian, after noticing `cairn-build images` holding six images on a
client VPS long after every build but the newest had been pushed — tracing the actual code
confirmed no bug, but surfaced a real gap `ADR-061` had deliberately left conservative).

## Context

`ADR-061` made `cairn-build prune` (`BR-CLI-018`) reach past fully-untagged images to any
image still carrying only the `cairn-build-owned` marker (`BR-BUILD-018`) — but it protected
**every** pushed image unconditionally, regardless of whether anything on the host still
needed it. That was deliberate: on a host colocating `cairn-build` with a target role
(`cairn-adopt`), both share the **same local engine image store** (not to be confused with
`cairn-registry`'s own separate on-disk blob store, `ADR-069`) — and `cairn-build prune` had
no way to know whether a pushed image it could see was one `cairn-adopt` was currently
running.

Tracing today's behavior against a real report confirmed the mechanism works exactly as
`ADR-061` specified: three genuinely distinct input hashes (a manifest app pinned to a moving
ref), most already pushed (marker correctly stripped), none superseded. The six-image count
was not a bug — it was `ADR-061`'s own conservative default: once pushed, an image is exempt
from `cairn-build prune` forever, because nothing tells prune whether it is still in use.

## Decision

`cairn-adopt` gains a symmetric, fixed, local-only tag — `cairn-adopt-owned`
(`BR-DEPLOY-023`) — applied to the image its `backend` container is currently running.
Unlike `cairn-build-owned` (applied once, at build time), this marker is **refreshed on every
`reconcile` pass**, including a converged no-op — not only when an actual pull occurs. A
no-op re-tag is cheap and idempotent, and refreshing on every pass means the guarantee never
depends on when a given host last happened to pull: a host still running an image pulled
before this feature shipped picks up the marker on its very next reconcile, converged or not,
with no manual step.

**`cairn-build prune` (`BR-CLI-018`) is rewritten again.** An image carrying the
`cairn-adopt-owned` marker is never a candidate in the first place — excluded at the same
step that now excludes it from `images`. Beyond that exclusion, nothing else is protected:
every remaining candidate is eligible once past the `--keep` grace window, including a pushed
image (real tags, no markers) nothing local is currently running. This is the change
`ADR-061` deliberately deferred: "any tag other than the owned marker" protected too broadly
because prune had nothing else to check against; a positive, host-local signal for "still in
use" closes that gap the same way the owned marker itself closed the untagged-only gap.

**`cairn-build images` (`BR-CLI-005`) also changes.** An image carrying `cairn-adopt-owned`
is excluded from the report entirely, rather than shown with the build marker reported absent
as `ADR-061` resolved `OQ-001`. Once `cairn-adopt` has claimed an image as currently running,
it is `cairn-adopt`'s to account for, not `cairn-build`'s — `cairn-build images` answers "what
does this build role hold," and a currently-deployed image is no longer only that.

**Reclaiming a *stale* `cairn-adopt-owned` image — one a target ran previously but has since
moved off — is `cairn-adopt prune` (`BR-CLI-028`), specified alongside this decision.** It
mirrors `cairn-build prune` (`BR-CLI-018`): the currently-running image (read the same way
`BR-DEPLOY-003b` already does, off the running container) is unconditionally protected
regardless of `--keep`; of the rest, only images beyond the newest `--keep <n>` are removed,
by tag rather than by id, for the same multiply-tagged-image reason `BR-CLI-018` already
documents. This is what finally gives `BR-DEPLOY-006`'s long-open target-side GC (`W-003`) a
concrete selection rule instead of an open-ended sweep.

## Alternatives considered

**Have `cairn-build prune` inspect live running containers directly** (`docker ps` +
`docker inspect <container> --format {{.Image}}`, the same technique `reconcile.py`'s own
`running_digest()` already uses for its own purposes) instead of a static tag. Rejected as
scope creep: it would make a *build* binary reach into container/compose state it has no
other reason to know about, and it would need to be re-derived correctly by every future
role that colocates with `cairn-build`. A tag applied by the role that acquires the image is
the same mechanism `cairn-build` already applies to itself (`ADR-061`) — kept parallel
rather than introducing a second technique for the same question.

**Keep the last N generations as rollback headroom**, via `cairn-adopt` retagging images it
previously ran. Deferred, not rejected outright — that headroom question belongs to
`BR-DEPLOY-006`'s eventual GC design, not to this decision. Today's answer for anything not
currently running is "no headroom beyond the currently-running image," consistent with
`BR-BUILD-018`'s own "local build storage is not a registry, no retention guarantee": a
manual rollback re-pulls from the registry, which `BR-BUILD-014a` already made the
authoritative path rather than local cache.

## Scope

No change to `cairn-build-owned`'s own lifecycle (`ADR-061` stands as written). `W-003`
(`BR-DEPLOY-006`) moves from an open design question to a specified, not-yet-implemented
command (`BR-CLI-028`) by this decision — the code itself is separate work, tracked there.
*(BR-CLI-005, BR-CLI-018, BR-CLI-028, BR-BUILD-018, BR-DEPLOY-006, BR-DEPLOY-023, ADR-019,
ADR-061, ADR-069)*
