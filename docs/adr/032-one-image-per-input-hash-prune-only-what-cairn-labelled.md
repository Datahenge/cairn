---
status: authoritative
owner: technical
purpose: ADR-032 — One image per input hash; prune only what cairn labelled
---

# ADR-032 — One image per input hash; prune only what cairn labelled

**Decided:** 2026-07-25
Four consecutive `cairn build` runs against an unchanged manifest produced four different
image IDs, five nameless multi-gigabyte images, and roughly 14 GB of orphans — while the
primary tag never changed. Three symptoms, one cause, and the diagnosis turned on
separating two things the docs had been treating as one.

**Declared inputs** are what `cairn.toml` says (`version-16`); **resolved inputs** are the
commits those symbols pointed at. Image content is a function of the *resolved* inputs
alone. That collapses the whole matrix of confusing cases: identical declared inputs can
yield different images (a branch moved between two builds), and different declared inputs
can yield identical images (a branch and a tag naming one commit). `BR-BUILD-005`'s
resolve-and-record is therefore load-bearing, not a convenience.

But the mapping is **one-to-many in the other direction too**: identical resolved inputs
still yield different *digests*, because the image config carries a build-time clock. No
amount of hashing fixes that — it has to be decided.

Decided: **cairn does not rebuild an input hash it already holds.** An existing primary tag
proves the inputs are unchanged; rebuilding can only mint a second digest, move the tag onto
it, and orphan the first. Refusing is what makes a deterministic *name* behave like one.
`--rebuild` overrides for a suspected-corrupt image. *(BR-BUILD-014)*

Also decided, and the sharper half:
- **"Immutable primary tag" was the wrong words** and caused the wrong inference. Corrected
  to **deterministic** throughout, with the three tiers — address (digest, immutable),
  deterministic name (cairn's tag, re-pointable), moving pointer (`latest`) — stated in
  `BR-BUILD-008` so the distinction survives this conversation.
- **Prune scopes by cairn's labels, never by danglingness.** Brian observed that clearing
  dangling images made the next build enormously slower: on podman an untagged image may be
  a build-cache **stage**, not a former build. cairn's `--label`s land only at the final
  commit, so a stage image never carries them, and a label-scoped prune is structurally
  incapable of eating the cache. The safety property and the performance property turn out
  to be the same property. *(BR-CLI-018, lessons §12)*
- **The engine's own image listing cannot answer "why does this exist"** — it knows
  repository, tag, id, age, size. Every fact needed is already stamped on the image by
  `BR-BUILD-011`; `cairn images --local` reads them back and groups by input hash, making
  supersession visible rather than inferred. *(BR-CLI-005)*

**Resolved 2026-07-25 — the `<legible>` half is a manifest-declared `series`.** Left deferred
here: the half derived from the *declared* Frappe ref, so the tag depended on how the ref was
**spelled** rather than on what was built. One commit reached by a branch and by a tag yielded
two names for one image, and taking `BR-BUILD-005`'s own advice to pin to tags renamed every
image though nothing about the content changed.

Decided: `[cairn] series = "v16"`. The manifest states the readable half once, and it stays put
when the Frappe ref is re-pinned. Brian chose it after the options were laid out; the deciding
argument for it over **reading the version at the resolved commit** — which sounds strictly more
truthful — is that the truthful version cannot be obtained provider-neutrally. `git ls-remote`
returns hashes, not file contents, so reading `frappe/__init__.py` needs either a clone on every
build or a GitHub-specific API call, and cairn assumes a git host no more than it assumes a
registry.

Two properties that make this safe:

- **`series` never enters the input hash.** It is a label, not an input. Changing it renames
  *future* images without invalidating existing ones or provoking a rebuild — exactly the
  distinction this decision is about.
- **Absent a declared `series` the old derivation still applies**, so a manifest predating it
  keeps producing the names it always did.

Accepted cost, stated plainly: nothing validates the declaration. A manifest may say
`series = "v16"` while building Frappe 15, and cairn will not notice. That is checkable later
(compare against the resolved version at build time) but not checkable for free — which is the
entire reason the more truthful option was rejected. Recorded in `BR-BUILD-002`/`BR-BUILD-008`.

*(BR-BUILD-008, BR-BUILD-014, BR-CLI-005, BR-CLI-018, ADR-011, ADR-015)*
