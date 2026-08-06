---
status: authoritative
owner: technical
purpose: ADR-061 — a cairn-build-owned marker tag, stripped on push, replaces untagged-only pruning and gives colocated roles a real answer to "did this build role put this here"
---

# ADR-061 — a `cairn-build-owned` marker tag, stripped on push, replaces untagged-only pruning

**Decided:** 2026-08-05 (Brian, working through what a single VPS colocating `cairn-build`,
`cairn-registry`, and `cairn-adopt` actually shares, and what a real `cairn-build prune`
needs to stay safe once it does more than clean up duplicate rebuilds).

## Context

Two things surfaced together while examining colocation, both traced against real code rather
than assumed:

1. **`cairn-build images --local` (`BR-CLI-005`, `OQ-001`, `open/OPEN_QUESTIONS.md`) couldn't
   distinguish "cairn built this" from "cairn built this on *this* host."** `BR-BUILD-011`'s
   provenance labels are OCI image config, baked in at build time — they survive a `docker
   pull` intact. So on a host where `cairn-adopt reconcile` pulls a deploy image
   (`reconcile.py`'s `docker pull <ref>`) alongside images `cairn-build` produces locally, both
   carry full cairn provenance and both showed up in `--local`'s report, with no way to tell
   which is which.
2. **`cairn-build prune` (`BR-CLI-018`) and the target's future GC (`BR-DEPLOY-006`,
   `open/OPEN_WORK.md`'s `W-003`, not yet implemented) are two independently-computed local
   image GCs that would share one image store on a colocated host, with no way for either to
   know what the other still needs.** Tracing today's actual prune logic
   (`prune.select()`) showed its blast radius is narrower than it first looks — the
   deterministic primary tag (`BR-BUILD-008`) is permanent per input hash and is only ever
   reassigned by a duplicate rebuild of identical inputs — but "eventually cairn-build cleans
   up excess images" (the acknowledged direction of travel) would need real teeth, and real
   teeth on a shared store is exactly where two uncoordinated GCs collide: `cairn-build prune`
   deleting an image `cairn-adopt` is currently running, or wants for rollback.

## Decision

Every build additionally applies a fixed, local-only tag — `cairn-build-owned`
(`BR-BUILD-018`) — alongside the existing primary and moving tags. It is never pushed. On a
successful push of an image's own tags, the owned marker is stripped from that image. It is not
reapplied; a build only ever gains it once, at the moment it is built.

**This makes "still owned" and "would ever matter to `cairn-adopt`" provably disjoint, by
construction, not by coordination.** `cairn-adopt` only ever touches images it pulled, and a
pulled image was — by definition — already pushed, which means it lost the owned marker before
`cairn-adopt` could ever have reached for it. Neither role has to read the other's state, query
a shared lock, or agree on a protocol; the owned marker's own lifecycle keeps the two candidate sets
apart.

**`cairn-build prune` (`BR-CLI-018`) is rewritten around it.** Restriction 2 changes from "only
remove an untagged image" to "never remove an image carrying any tag *other than* the owned
marker" — protecting anything pushed (or predating the owned marker, treated the same way out of
caution) exactly as before, while now also reaching an unpushed image that still carries its
own real tags once it is stale. Restriction 3's `--keep <n>` becomes an explicit grace window,
not rollback headroom — build-machine storage was never promised to be either, and saying so
plainly is more honest than implying a guarantee `BR-BUILD-014a`'s own registry fallback
already assumes may not hold.

**One implementation consequence, caught before it shipped:** an eligible-but-still-owned
image typically carries three live tags at once (primary, moving, owned), and engines refuse
`image rm <id>` on a multiply-tagged image without `--force` — which cairn never passes.
`prune`'s removal step therefore removes each tag reference individually; the last one is what
actually frees the disk.

**`cairn-build images --local` (`BR-CLI-005`) reports the owned marker per image**, closing `OQ-001`
directly: present means this host's build role produced it and nothing has seen it since;
absent means it was pushed, or arrived here some other way (a pull, a manual retag, or it
predates this feature). The report no longer has to guess.

**`BR-DEPLOY-006`'s not-yet-written target-side GC gets one constraint up front**: it must
never remove an image still carrying the owned marker. Given the disjointness above this should
never actually apply in ordinary operation — but it costs nothing to state, and it is the
right default for a sweep-style implementation that might otherwise walk the whole local store
rather than only its own known-good digests.

## Alternatives considered

**Make every tag sacred everywhere, and have the target's future GC keep its own rollback set
via its own local retagging** (the previously-favored answer). Rejected once the owned-tag
design was on the table: it would have required `BR-DEPLOY-006` to invent new bookkeeping
(target-owned rollback tags) before it is even written, whereas the owned marker needs nothing from
the target side beyond the one-line guard above — the disjointness is structural, not a
convention both roles have to uphold correctly forever.

**A label instead of a tag.** Rejected on a technical ground, not a preference: `BR-BUILD-011`
labels are OCI image config, immutable for the life of that digest. "Strip it after a
successful push" is only possible with a mutable, separately-addressable pointer — a tag —
not a label.

## Scope

No change to `BR-DEPLOY-006` itself beyond the one guard above — the target-side GC's actual
selection logic remains `W-003`, still open. `--delete-after-push` (an optional flag to strip
*all* local tags immediately after a confirmed push, not just the owned marker) was raised alongside
this and is a natural companion, but is a separate flag and a separate decision; this ADR does
not include it. *(BR-BUILD-008, BR-BUILD-011, BR-BUILD-014, BR-BUILD-018, BR-CLI-005,
BR-CLI-018, BR-DEPLOY-006, ADR-022, ADR-032, ADR-052)*
