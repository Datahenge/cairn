---
status: authoritative
owner: requirements
purpose: BR-BUILD cache-busting, the deterministic tag scheme, input-hash deduplication, and the cairn-build-owned marker.
---

# BR-BUILD — Cache & Tagging Requirements

Split out of [`02-build.md`](02-build.md) on 2026-09-03, which had reached its word-count
ceiling. This document owns how a built image is **named and reused**: what invalidates the
build cache, how the primary and moving tags are computed, when an existing image is reused
instead of rebuilt, and the ownership marker that makes pruning safe. `02-build.md` keeps
what a build *is* — inputs, ref resolution, invocation, provenance.

Requirement IDs are unchanged and never renumbered by a move.

**`BR-BUILD-007`** — cairn MUST set `CACHE_BUST` from a hash of **all** resolved commits
(Frappe **and** every app); a correct build MUST NOT require `--no-cache`. Frappe is
included because `FRAPPE_BRANCH` enters the cache key by **name**, so a branch that moves
would otherwise reuse a stale `bench init` layer. *(ADR-015)*

**`BR-BUILD-008`** — cairn MUST tag the image with a **deterministic primary tag**
`<legible>-<inputhash>` — `<inputhash>` a short hash of *all* resolved inputs (Frappe + app
commits + effective build args) that alone guarantees uniqueness (e.g.
`cairn/erpnext-v16:v16-a1b2c3d4`). cairn MUST also apply a moving `latest` tag. The
image base defaults to `cairn/<image_name>` and MUST be registry-agnostic.

`<legible>` comes from the manifest's declared `[cairn] series` (`ADR-032`, resolved
2026-07-25); absent one it is derived from the declared Frappe ref as before
(`version-16`→`v16`). It MUST NOT enter the input hash: it is a **label, not an input**, so
changing `series` MUST rename future images without invalidating existing ones or provoking a
rebuild (`BR-BUILD-014`). A declared `series` MUST be a legal tag fragment and MUST NOT contain
a hyphen, since the tag reads as `<series>-<hash>`.

**Why declared rather than derived.** Deriving it from the ref made the tag a function of how
the ref was *spelled*: one commit reached by a branch and by a tag produced two names for one
image, and following `BR-BUILD-005`'s own advice to pin to tags renamed every image for no
change in content. Reading the true version at the resolved commit was rejected as it cannot be
done provider-neutrally — `git ls-remote` returns hashes, not file contents. *(ADR-032)*

**"Deterministic", not "immutable"** — the word was corrected 2026-07-25 (`ADR-032`) after
the original wording invited a false inference. Same inputs always produce the same *name*;
that name is still a mutable pointer the engine will move onto a newer image. Three tiers
of identity are in play and only the first is immutable:

| Tier | Example | Property | Owner |
| --- | --- | --- | --- |
| Address | `sha256:1782626c…` | content-addressed, immutable | the engine / OCI |
| **Deterministic name** | `v16-1bf0adf3823f` | derived from resolved inputs; **re-pointable** | cairn |
| Moving pointer | `latest`, later `:production` | names a role, not content | cairn |

Because the input hash covers **effective** build args (`BR-BUILD-010`), a deliberate change
to the owned recipe (e.g. bumping a Containerfile default) changes the tag **even when
`cairn.toml` is unchanged**. This is intended, not a defect: the image's inputs did change,
and any recipe edit is already an explicit, reviewable commit (`BR-VEND-002`). *(ADR-011,
ADR-009)*

**`BR-BUILD-014`** *(one image per input hash)* — When the primary tag already exists
**locally**, cairn MUST NOT rebuild. It MUST report the existing image and its digest and
exit 0, unless `--rebuild` is given.

The primary tag is a deterministic function of every resolved input (`BR-BUILD-008`), so an
existing tag is proof that the inputs are unchanged. Rebuilding cannot produce a different
image in any respect that matters — but it *will* produce a different **digest**, because
the image config carries a build-time clock (`org.opencontainers.image.created`, and the
engine's own `created` field). That new digest takes the tag, and the previous image is left
nameless. Rebuilding is therefore not merely wasted time: it is how a *deterministic* name
comes to point at a succession of digests, and how a build machine accumulates orphaned
multi-gigabyte images.

Consequently **one input hash SHOULD correspond to one image**, and cairn's refusal to
rebuild is what makes that true in practice. `--rebuild` remains available for the case
where an image is believed corrupt. *(ADR-032, BR-CLI-005, BR-CLI-018)*

**`BR-BUILD-014a`** *(registry-side fallback, `ADR-052`)* — When the local check
(`BR-BUILD-014`) misses **and** a registry is configured, cairn MUST also check whether the
primary tag already exists in that registry before deciding to build, checked whenever a
registry is configured — not gated on `--push`. A hit MUST be reported distinctly from a local
hit (naming the registry), and MUST skip the build the same way a local hit does. This is what
makes a build machine's cache miss (a cold local store, or a second/replacement machine) cost
a registry read instead of a full rebuild, since the primary tag is deterministic regardless of
which machine computed it first. cairn MUST NOT pull the image locally as a side effect of a
registry hit. *(ADR-052)*

**`BR-BUILD-018`** *(the owned marker, `ADR-061`)* — Every build MUST additionally apply a
third, fixed local tag — `cairn-build-owned` — alongside the primary and moving tags
(`BR-BUILD-008`), marking the image as **not yet shared**. cairn MUST NOT push this tag.

On a successful push of an image's own tags (`build --push`, or `push` without `--id`), cairn
MUST strip the marker once every pushed tag has uploaded. A push via `--id` — an explicit tag,
not necessarily "this manifest's current build" — MUST NOT touch it.

**Local build storage is not a registry** — no backup, no retention guarantee; that is a
registry's job (`BR-REG` area). The marker lets `cairn-build prune` (`BR-CLI-018`) tell an
image nothing outside this host has seen (reclaimable once stale) from one already shared
(never its to remove), and gives `images --local` (`BR-CLI-005`) an exact answer to whether
this build role produced an image or it arrived some other way — a pulled image was, by
definition, already pushed, so it can never carry the marker. *(ADR-061)*

---

## Cross-references
- Build inputs, ref resolution, invocation, and provenance: [`02-build.md`](02-build.md).
- `prune`'s use of the ownership markers is specified under `BR-CLI`.
