---
status: authoritative
owner: technical
purpose: Durable findings about cache invalidation, provenance capture, and image labelling.
---

# Lessons Learned — Caching and Provenance

Part of the [lessons-learned](04-lessons-learned.md) set. See that file for what this
document type is for and how findings are marked (**measured** vs **reasoned**).

_Last updated: 2026-08-03_

---

## 1. The secret mount and the cache key interact in a way that *requires* `CACHE_BUST`

*Reasoned, then measured (§5, this file). Illuminates `BR-BUILD-006`, `BR-BUILD-007`._

This is the most valuable thing learned, and it is not obvious from either requirement in
isolation. At `src/cairn/recipe/images/Containerfile:124-134`:

```dockerfile
ARG CACHE_BUST=""
RUN --mount=type=secret,id=apps_json,target=/opt/frappe/apps.json,uid=1000,gid=1000 \
  : "${CACHE_BUST}" && \
  ... bench init ${APP_INSTALL_ARGS} --frappe-branch=${FRAPPE_BRANCH} ...
```

Three facts compose into one requirement:

1. `apps.json` is mounted as a tmpfs file existing only for that one `RUN`. It never
   enters a layer — which is the point, since app URLs may carry tokens for private
   repos. A build-arg would be permanently readable via image history. Hence
   `BR-BUILD-006`'s "secret, **never** a build-arg".
2. **A secret's contents are deliberately excluded from the layer cache key.** If they
   were included, the secret would leak into cache metadata. So editing `apps.json`
   leaves the `RUN` instruction byte-identical and the cached layer is reused — you get
   an image built from your *previous* app list, silently and with no error.
3. `bench init` runs `git clone` against remote branches, which the builder cannot
   content-address either. A branch that moved is likewise invisible.

Line 129's `: "${CACHE_BUST}"` is the shell no-op `:` used solely to *reference* the ARG,
forcing its value into that instruction's cache key.

So `BR-BUILD-007` — "set `CACHE_BUST` from a hash of all resolved commits; a correct
build MUST NOT require `--no-cache`" — is a **compensating mechanism for two cache blind
spots**, not a performance optimization. Read as an optimization it looks droppable. It
is not: without it, correctness depends on the operator remembering `--no-cache`.

**Corroborated by upstream** at `docs/03-production/06-automated-builds-and-deployment.md`:
"This is especially relevant because `apps.json` is provided as a secret. Secret contents
are not part of Docker layer cache keys and therefore cannot trigger cache invalidation
automatically. As a result, Docker may reuse an older cached layer even when the custom
app definition has changed." Derived here from the Containerfile before that prose was
found — the agreement is reassuring rather than circular.

**One gap upstream does not close:** its recommended technique is an *apps.json* hash,
which misses Frappe. `FRAPPE_BRANCH` is a build-arg and so enters the cache key by
**name**, but a branch that *moves* keeps its name — a Frappe-only update would reuse a
stale `bench init` layer. `BR-BUILD-007` was therefore revised (2026-07-24) to hash
**all** resolved commits, Frappe included.

## 2. The build destroys its own provenance

*Measured (read from the vendored source). Illuminates `BR-BUILD-005`, `BR-BUILD-011`._

`Containerfile:144` ends the builder stage with:

```
find apps -mindepth 1 -path "*/.git" | xargs rm -fr
```

Every app's git metadata is stripped from the image. Once the image exists, **there is no
way to recover which commits went into it by inspecting it.**

This is why `BR-BUILD-005` (resolve-and-record) and `BR-BUILD-011` (stamp resolved commits
as OCI labels) are necessary rather than merely tidy: provenance must be captured *outside*
the build, at resolve time, because the build itself deletes the evidence. Any future
proposal to "just inspect the image" for provenance is foreclosed by this line.

## 3. A pattern-filtered `git ls-remote` omits the peeled ref

*Measured, 2026-07-24. Illuminates `BR-BUILD-005`, `BR-BUILD-011`._

`git ls-remote --heads --tags <url>` lists an annotated tag twice — the tag object, then
the commit it peels to:

```
78e30c5a…  refs/tags/v1.0
6247c646…  refs/tags/v1.0^{}
```

Add a **pattern** and the second line disappears:

```
$ git ls-remote --heads --tags <url> v1.0
78e30c5a…  refs/tags/v1.0            # tag object only

$ git ls-remote --heads --tags <url> v1.0 'v1.0^{}'
78e30c5a…  refs/tags/v1.0
6247c646…  refs/tags/v1.0^{}         # the commit
```

The peeled entry is a ref whose name ends in `^{}`, so it does not match the pattern
`v1.0`; it must be requested by name. Without the second pattern, resolution records the
**tag object's** SHA — an object a clone never checks out. That would have poisoned
provenance (`BR-BUILD-011`), the input hash (`BR-BUILD-008`), and `CACHE_BUST`
(`BR-BUILD-007`) for every annotated-tag pin, while looking entirely plausible: a
40-character hex SHA, in the right field, wrong object.

**Why it survived unit testing:** the stub returned both lines, because that is what an
*unfiltered* `ls-remote` returns and what the documentation examples show. The test
encoded the author's assumption rather than the command's behaviour, and passed. It was
caught by resolving against a throwaway local repository with one annotated tag, one
lightweight tag, and one branch — three lines of setup that no amount of mocking would
have substituted for.

Generalizable: when stubbing a subprocess, the stub's *output* is a second assumption
under test, and a passing test only confirms the two assumptions agree. Verify the real
command's output shape at least once, especially where a wrong value is still
well-formed.

## 4. The OCI spec sets the label convention; Docker's docs carry the reasoning

*Measured (both documents read, 2026-07-24). Illuminates `ADR-030`, `BR-BUILD-011`._

Looking for *why* image labels use reverse-DNS keys, the obvious source is the wrong one.
The OCI image-spec's `annotations.md` says only:

> Keys SHOULD be named using a reverse domain notation - e.g. `com.example.myKey`.
> … Consumers MUST NOT generate an error if they encounter an unknown annotation key.

**SHOULD**, not MUST; `org.opencontainers` reserved; **no rationale given**, and **nothing
at all about domain ownership**. Both of the things one actually needs to decide a
namespace live in *Docker's* label documentation:

> Authors of third-party tools should prefix each label key with the reverse DNS notation
> of a domain **they own** … Don't use a domain in your label key without the domain
> owner's permission.

with the purpose stated as preventing "inadvertent duplication of labels across objects,
especially if you plan to use labels as a mechanism for automation."

Two consequences worth keeping: a non-conforming key is *tolerated* by the spec (consumers
must not error), so bare `cairn.*` would have worked mechanically — the reason to conform
is collision safety for automation, not validation. And the ownership norm is what rules
out a namespace like `io.cairn` for anyone who does not own `cairn.io`.

Generalizable: when a standard is terse, the operative guidance often sits in a dominant
implementer's documentation rather than in the standard. Read both before concluding a
spec is silent on something.

## 5. On podman, an untagged image may be the build cache

*Measured (Brian, 2026-07-25 — cleared dangling images, next build went cold).
Illuminates `BR-CLI-018`, `ADR-032`._

`podman image list` hides *intermediate layer* images by default (`-a` reveals them), which
makes it tempting to conclude that anything visible and untagged is a discardable former
build. That conclusion is wrong, and expensively so.

A multi-stage Containerfile leaves its **stage** images in local storage, untagged. For the
vendored `custom` Containerfile the `builder` stage is the one that matters: it holds the
base plus the whole build toolchain (`gcc`, `build-essential`, every `-dev` package) plus
the completed bench, so it is *larger* than the final image — measured at **4.63 GB against
2.75 GB**. It is also what a later build matches against to skip `bench init`, the single
most expensive step in the whole build. Delete it and every subsequent build is cold, with
no error and no explanation.

So on podman: **`<none>/<none>` is not a synonym for "garbage".** It spans at least three
different things — superseded final builds, multi-stage stage images, and true orphans —
and the engine's listing cannot tell them apart.

What *can* tell them apart: `--label` values are applied only at the **final** commit, so a
stage image never carries them. Any tool that scopes destructive work to images bearing its
own labels is structurally incapable of deleting the cache. Generalizable beyond containers:
**when a cleanup's safety rests on a property the platform computed** (danglingness,
reachability, age), prefer a property *you* stamped and therefore understand. Here the
safety property and the performance property turned out to be the same property — which is
usually the sign that the scoping is the right one.

Corollary for advice-giving: "prune only dangling images, it's safe" was stated in this
project's own conversation before this was measured. Danglingness reads like a
reachability guarantee. It is not one.

### Confirmed, and a stage image can be named for free

*Measured 2026-07-25 on the real build machine._

Re-running the build with `--target builder` and a `--tag`, against a warm cache and the
identical build-args and `CACHE_BUST`:

- **0.762s**, every step reporting `Using cache` — including the `bench init` layer, which
  resolved to `Using cache e03e7719c39b53f6…`, the id already in local storage;
- `COMMIT` landed on **that same id**, and the listing's `CREATED` still read "51 minutes
  ago" — the image was *named*, not rebuilt;
- total distinct images unchanged: no new disk.

This settles two things. The 4.63 GB untagged image **is** the `builder` stage, proven from
the engine's own cache resolution rather than inferred from its size. And an existing stage
can be given a repository and tag for approximately nothing, because a tag is a pointer.

Two cautions that came out of the same run:

- **podman prefixes an unqualified name with `localhost/`** — the tag requested as
  `cairn-cache/erpnext-btu-v16:builder` appears as
  `localhost/cairn-cache/erpnext-btu-v16:builder`. Anything matching on that name later must
  expect the prefix.
- **The cheapness depends entirely on the cache being warm.** The same command against a
  *cold* cache is a full `bench init` — so a tagging pass is only safe immediately after a
  build that actually ran, never after one that was short-circuited, where the stage may
  have been pruned since.

*Reasoned, not measured:* none of this transfers to Docker. BuildKit keeps build cache in a
separate store rather than as images, so there is no untagged stage to name — and asking for
one with `--target` would make it **materialize** several GB that otherwise never exist.
