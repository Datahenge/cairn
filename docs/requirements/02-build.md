# BR-BUILD — Image Build Requirements

_Status: **approved** 2026-07-21 (living — may be revised via CHANGELOG) · Last updated: 2026-07-24_

Requirements for building a custom ERPNext image from a manifest, using the vendored
`frappe_docker` `custom/Containerfile`. Conventions: see `/CLAUDE.md`. Decisions cited:
`ADR-004`, `ADR-007`, `ADR-009`, `ADR-011`, `ADR-015`.

---

## Manifest & inputs

**`BR-BUILD-001`** — cairn MUST build a custom image from a standalone `cairn.toml`
declaring exactly one, environment-agnostic image. *(ADR-015)*

**`BR-BUILD-002`** — The manifest MUST provide `[cairn] image_name`; a `[cairn.frappe]`
section (`url`, `ref`) driving `FRAPPE_PATH`/`FRAPPE_BRANCH`; an **ordered** `[[cairn.apps]]`
list (`name`, `url`, `ref`) for ERPNext + custom apps; and `[cairn.build]` knobs
(`python_version`, `node_version`, `install_chromium`) with an optional passthrough for the
long tail (`debian_base`, `wkhtmltopdf_*`). It MAY provide an optional
`[cairn.environments]` table — the declared environment list of `BR-DEPLOY-009`
(`ADR-033`), which no build reads — and an optional `[cairn] series` naming the legible half
of the image tag (`BR-BUILD-008`, `ADR-032`). *(ADR-015, ADR-032, ADR-033)*

**`BR-BUILD-003`** — `[[cairn.apps]]` is **order-significant**: cairn MUST preserve manifest
order into `apps.json` and into the deploy-time install sequence, and MUST NOT reorder or
resolve dependencies. This rule MUST be documented in `README.md`, and every shipped
`cairn.toml` template/example MUST carry an inline comment declaring the list ordered.
*(ADR-015)*

**`BR-BUILD-004`** — Frappe MUST be supplied via the `FRAPPE_*` build-args, never in
`apps.json`; `apps.json` MUST contain only ERPNext + custom apps. *(frappe_docker interface)*

## Ref resolution (Option A — resolve-and-record)

**`BR-BUILD-005`** — Refs pin by **branch or tag only** (raw commit SHA unsupported). cairn
MUST resolve every ref (Frappe + each app) to its commit at build time and record it in
provenance; it MUST NOT freeze commits into the build. The manifest SHOULD pin to tags;
cairn SHOULD warn when a moving branch is used. *(ADR-015)*

**`BR-BUILD-006`** — `apps.json` MUST be passed only as a **build secret**
(`--secret id=apps_json`), never as a build-arg. *(ADR-015, ADR-027)*

## Cache & tagging

**`BR-BUILD-007`** — cairn MUST set `CACHE_BUST` from a hash of **all** resolved commits
(Frappe **and** every app); a correct build MUST NOT require `--no-cache`. Frappe is
included because `FRAPPE_BRANCH` enters the cache key by **name**, so a branch that moves
would otherwise reuse a stale `bench init` layer. *(ADR-015)*

**`BR-BUILD-008`** — cairn MUST tag the image with a **deterministic primary tag**
`<legible>-<inputhash>` — `<inputhash>` a short hash of *all* resolved inputs (Frappe + app
commits + effective build args) that alone guarantees uniqueness (e.g.
`cairn/erpnext-btu-v16:v16-a1b2c3d4`). cairn MUST also apply a moving `latest` tag. The
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

Because the input hash covers **effective** build args (`BR-BUILD-010`), a deliberate
`frappe_docker` pin bump that changes a Containerfile default changes the tag **even when
`cairn.toml` is unchanged**. This is intended, not a defect: the image's inputs did change,
and `BR-VEND-009` already makes pin bumps explicit and reviewable. *(ADR-011, ADR-009)*

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

## Build invocation

**`BR-BUILD-009`** — cairn MUST build using the vendored `images/custom/Containerfile` with
`frappe_docker/` as the build context, and MUST enforce the `VEND` preconditions first:
`BR-VEND-005` (drift) and `BR-VEND-006` (completeness). *(ADR-004)*

**`BR-BUILD-010`** — cairn MUST pass the `[cairn.build]` knobs as the matching build-args and
MUST record the effective values (including Containerfile defaults where unset) in
provenance. *(ADR-015)*

**`BR-BUILD-015`** *(name the build-cache stage)* — On **podman**, after a build that
actually ran, cairn SHOULD tag the vendored Containerfile's `builder` stage
`cairn-cache/<image_name>:builder` (podman stores this as `localhost/…`). `--no-cache-tag`
disables it.

An untagged image invites deletion. The `builder` stage is untagged, **larger** than the
final image (measured: 4.63 GB against 2.75 GB), and is what lets a rebuild skip
`bench init` — so an administrator running `podman image list`, seeing `<none>`, and
reaching for `prune` converts every later build into a cold one, with no error to explain
it. A tag is a pointer: naming it changes no digest, creates no image, and costs no disk
(measured at 0.762s, every step a cache hit).

Constraints, each load-bearing:
- **podman only.** Docker keeps build cache in a separate store rather than as images, so
  there is no stage to name and `--target` would make BuildKit **materialize** several GB
  that otherwise never exist. See the `ADR-027` amendment.
- **Only after a build that ran** — never after a `BR-BUILD-014` short-circuit, and never as
  a standalone verb. The pass is cheap *only* against a warm cache; if the stage has since
  been pruned, the identical command is a full `bench init`. Confining it to the moment
  after a real build is what guarantees the stage exists.
- **The tagging pass MUST NOT pass `--no-cache`**, even when the build did. It exists to
  name what that build just produced.
- **Best-effort.** A failure MUST NOT fail the build; the image is already built and
  verified. It is reported, not raised.
- The tag **moves** with each build, like `latest`. Superseded stages revert to untagged and
  are then genuinely collectable — which is correct, and is why cairn does not tag per input
  hash: that would identify them but pin every one of them forever. *(lessons §12, ADR-027,
  ADR-032, BR-CLI-018)*

## Provenance

**`BR-BUILD-011`** — On a successful build, cairn MUST stamp provenance onto the image as OCI
labels (via the build engine's `--label`, `ADR-027`), recording: `image_name`; resolved Frappe + app commits
with their source refs; effective build args; both tags; the `frappe_docker` pin (from
`.ventwig.lock`); the input-hash; and a timestamp. cairn MAY emit a sidecar marker into the
deployment working directory, and MUST NOT write markers into its own installation or source
tree. The concrete label schema is `ADR-030`. *(ADR-011, ADR-030)*

**`BR-BUILD-012`** — cairn MUST offer a `--dry-run` that emits the resolved `apps.json`, the
exact build command, the computed tags, and the intended provenance, without
building. *(BR-CLI)*

## Reproducibility bar

**`BR-BUILD-013`** — cairn's guarantee is **input-deterministic** (same resolved inputs →
same declared image), not bit-for-bit hermetic; this limit MUST be documented. *(ADR-004,
ADR-007)*

---

## Cross-references
- Preconditions `BR-VEND-005` / `BR-VEND-006` are enforced here.
- The `cairn build` command surface is specified under `BR-CLI`.
