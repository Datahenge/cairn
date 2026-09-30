---
status: authoritative
owner: technical
purpose: ADR-079 — the client is stamped on the image and the environment is not; an opaque manifest id carries the grouping
---

# ADR-079 — The client is stamped on the image, the environment is not

**Decided:** 2026-09-29 (Brian, while scoping build-machine retention — `W-042`).
**Amended the same day** — see "What changed within the day" below.

**Amends:** `BR-BUILD-011`, `ADR-030`'s schema. **Relates to:** `BR-BUILD-001`,
`BR-DEPLOY-009a`, `BR-BUILD-014`, `ADR-032`, `ADR-052`, `ADR-061`, `BR-CFG-013`, `BR-CLI-022`.

## Context

A build machine retains one image per input hash forever: `prune.select` keeps the newest
`--keep` **per input hash**, and `--keep` has a floor of 1, so N distinct hashes retain N images
with nothing to reclaim. Bounding that (`W-042`) requires retention to group images by something
coarser than the input hash. Brian chose the **manifest**.

`ADR-052` settled manifest uniqueness as `(client, image_name, environment)`. Retention reads
local images through `images.inspect_local`, which knows only what the labels carry, so grouping
by manifest means those facts must reach the image. Only `image_name` did, as
`org.opencontainers.image.title`. `client` was computable at build time
(`provision.client_from_manifest`) but recorded nowhere. `environment` is barred from the image
by `BR-DEPLOY-009a`: *no environment name may reach a build by default — the image stays
environment-agnostic (`BR-BUILD-001`) unless `build --assign-tag` is explicitly given.*

**Why that bar exists, stated as a mechanism.** An environment-agnostic image is what lets a
promotion move a tag instead of rebuilding. A *label* is immutable, so one reading
`environment=staging` states an intent that is wrong the moment the image is promoted, with no
way to correct it short of the rebuild promotion exists to avoid. A *tag* reading `:production`
is fine by contrast — it is mutable, says "currently serving production," and moves when that
stops being true. The harm was never the disclosure; it is binding an immutable artifact to a
mutable intent.

## Decision

**Stamp the client. Do not stamp the environment. Carry the grouping in an opaque manifest id.**

`BR-BUILD-011` gains two labels, and `BR-DEPLOY-009a` and `BR-BUILD-001` are **unchanged** — no
exception is carved and no environment name reaches the image:

| Key | Value |
| --- | --- |
| `com.datahenge.cairn.client` | the client owning the manifest, in plain text |
| `com.datahenge.cairn.manifest` | a short digest of `(client, image_name, environment)` |

The manifest id is deterministic — one manifest always yields the same id, with no state to
store — and is built the way `tagging._digest` already builds one, terminating each component so
no combination of values can be re-partitioned into a different triple with the same digest. A
manifest declaring no environment is a legitimate input and must not collide with one that
declares any.

**Retention groups by the manifest id.** Two manifests of one client that build the same
`image_name` and differ only by environment are therefore distinguishable after all, and
`keep_last` applies per manifest as originally intended.

**The id MUST NOT enter the input hash** — the same rule `series` follows (`ADR-032`). It is a
label, not an input. Were it an input, renaming an environment would invalidate every existing
image and force a full rebuild.

## What changed within the day

This ADR was first written rejecting an opaque digest, and grouping by `(client, image_name)`
alone with the shared pool that implied. Brian reversed it hours later. Both the original
rejection and its answer are kept visible because the distinction is the whole substance of the
decision.

**The rejection said:** an opaque digest still binds the image to one environment, so it is
equally false after a promotion — it merely hides the falsehood.

**The answer:** falsehood requires a claim, and an opaque value makes none. What made
`environment=staging` harmful was that a reader — human or tool — infers *intent* from it, and no
reader can infer intent from `d32jf32a`. The label stops being a statement about where the image
belongs and becomes what it always should have been: a statement about which manifest produced
it, which is a historical fact that never expires.

**Two corrections that fell out of the same exchange**, recorded because each changed the work:
the client was **not** already on the image (only `image_name` was), so a new label is required
rather than free; and the registry namespace visible in a tag is not the client — it is a
`[cairn.registry]` coordinate (`BR-CFG-014`) that coincides with the client directory only by an
operator's naming.

## Rejected alternatives

**Stamp `environment` in plain text, amending `BR-DEPLOY-009a`.** Rejected on the mechanism
above: an immutable label carrying a mutable intent.

**Name the key `environment` while making the value opaque.** Rejected: the key would still
announce that the image is bound to an environment, moving the implied intent up one level
rather than removing it. `manifest` names what the label is *for* and implies nothing about where
the image should run.

**Derive the client from the registry namespace already in the tag.** Rejected three ways: that
segment is the registry **namespace** (`BR-CFG-014`), not the client, and nothing ties them
beyond an operator naming them alike; it lives in a *tag*, which is mutable; and a superseded
untagged image has no tag at all, which is precisely the population retention reasons about.

**Group by `series`.** Not unique per client (two clients on `version-16` with none declared
both derive `v16`) and renameable at will by design (`ADR-032`) — a mutable grouping key.

## Consequences

- **The digest is obfuscation, not secrecy, and is not relied on for any.** Environment names
  come from a small dictionary, so anyone motivated can hash the candidates and match. That does
  not defeat the purpose: the goal is that no reader is *misled* by a label reading `production`,
  not that none can find out. The environment name is in any case already public on the registry
  copy as its tag (`BR-DEPLOY-009a`). Including the client in the digest at least makes that
  brute force per-client work.
- **The id records the manifest that *first* built an image, not every manifest that uses it.**
  Environment is not part of the input hash, so two manifests pinning identical inputs produce
  one image and `BR-BUILD-014` short-circuits the second build, which never stamps its own id.
  Harmless — one image is one group, so there is no eviction contest — but better written down
  than discovered.
- **Renaming an environment changes the id**, so images built before the rename group separately
  from those after. This errs toward retaining more, never less.
- The client name travels with the image wherever it is pushed. Under `BR-CFG-013`'s normal
  shape — each client's own registry — this is unremarkable, and worth knowing only where
  several clients' images would share one registry.
- Client-name uniqueness is **already** load-bearing and is not introduced here:
  `provision.github_token_env_file` scopes a GitHub PAT to `/etc/cairn/<client>/`, so two
  distinct companies under one client name would already share a credential file. Uniqueness
  needs no enforcement on a build machine regardless: `client` is a directory segment under
  `/srv/cairn/`, which the filesystem keeps unique, and retention is host-local.
- A manifest outside the canonical `/srv/cairn/<client>/` home has no derivable client, so
  **both** labels are omitted rather than guessed. What retention does with an image carrying
  neither — including every image built before these labels existed, which cannot be backfilled
  because labels are immutable — was settled by `OQ-005` later the same day and is written into
  `BR-CLI-018`: such an image is **legacy**, exempt from the per-manifest restriction but still
  subject to the others, and always reported so an administrator can act on it.
