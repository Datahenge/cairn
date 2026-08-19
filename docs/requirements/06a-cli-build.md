---
status: authoritative
owner: requirements
purpose: BR-CLI requirements — the `cairn-build` command surface (build/control role).
---

# BR-CLI — `cairn-build` Command Surface

_Split out of `06-cli.md` on 2026-08-18; identifiers unchanged. Shared UX conventions, the
commands common to all three binaries, and the `cairn-registry` verbs remain in
[06-cli.md](06-cli.md), which is the entry point for this area._

---

## A. `cairn-build` commands (build/control)

**`BR-CLI-002`** *(build)* — `cairn-build build [--push] [--manifest <path>] [--no-cache]
[--dry-run]` — build the image from `cairn.toml` (resolve refs → apps.json → tagged image +
provenance labels). **Default is build-only**; `--push` also uploads. *(BR-BUILD-*)*

**`BR-CLI-002a`** *(build's `--assign-tag`, on by default with `--push`, `ADR-052`,
`ADR-066`)* — `build --push` MUST also assign the manifest's declared environment by
default, unless `--no-assign-tag` is given: after a successful push (or a no-op
short-circuit, `BR-BUILD-014`/`014a`), it performs the same retag step `assign-tag`
(`BR-CLI-004`) does, reusing the digest `build` already resolved rather than re-running
`assign-tag`'s own resolve-and-check from scratch. A manifest declaring **no** environment
is silently skipped under the default — most manifests don't participate in the environment
model at all, and that is not an error. Passing `--assign-tag` explicitly asks for it and
MUST still error if the manifest declares none (`BR-CLI-009`), and MUST be refused as a
contradiction if `--push` is absent — nothing was pushed to retag. The `:production` gate
(`BR-CLI-010`) applies identically whether the assignment came from the default or from an
explicit `--assign-tag`. *(BR-BUILD-014a, BR-CLI-004, BR-CLI-009, BR-CLI-010, ADR-052,
ADR-066)*

**`BR-CLI-003`** *(push)* — `cairn-build push [--id <tag>]` — upload a built image to the
registry (default: the current manifest's just-built image). *(BR-BUILD-*, BR-CFG-011)*

cairn invokes the engine's `push` with `--quiet`: unquieted, both print one line per layer
("Pushed", "Layer already exists"), misread as an error on a `BR-BUILD-008` second push of
the same digest under `latest`. Suppresses only progress, not errors/exit code, at cairn's
floors (Docker v23+, podman v4+, `ADR-027`; see `push.py` for version history). Real failures
still print and exit non-zero (`BR-CLI-011`); cairn's own framing already names the
reference, the digest reported once already, after the build (`BR-BUILD-011`).

**`BR-CLI-004`** *(pointer verbs — assign / retire, `ADR-052`)* — Neither command takes an
environment name as an argument; both take `--manifest <path>` and read the environment from
the file (`BR-DEPLOY-009a`).

- `cairn-build assign-tag --manifest <path> [--yes] [--dry-run]` — resolves the manifest's refs
  to their **current** commits, computes the deterministic primary tag (`BR-BUILD-008`), and
  checks the registry. **Found:** retags the manifest's declared environment onto that digest
  (server-side, no rebuild) and reports it. **Not found:** reports that and does **nothing** —
  `assign-tag` MUST NOT trigger a build. There is no selector menu (`--latest`/`--previous`/
  `--id`/`--from`, `ADR-050`, retired) — there is only ever one well-defined answer: what the
  manifest's own refs currently, factually resolve to.
- `cairn-build retire --manifest <path>` — **decommission** the manifest's declared environment
  from cairn (see `BR-CLI-009`).

An earlier draft added an opt-in `--install-app <apps>` here. It was **struck** 2026-07-25
(`ADR-037`, `BR-DEPLOY-003a`): installing a Frappe App is the operator's act, not a pointer
move's. *(BR-DEPLOY-004, BR-DEPLOY-003a, ADR-023, ADR-052)*

**`BR-CLI-005`** *(introspection, local only)* — `cairn-build images [--json]`, no other
arguments: which images does *this* build machine hold, why does each exist, and which are
superseded. cairn MUST identify its own images by their provenance labels (`BR-BUILD-011`),
MUST group them by **input hash**, and MUST show, per image, its tags — or that it has
**none** — along with age, size, and the resolved Frappe/app commits read from labels.
`cairn-build` never reads a registry — that's `cairn-registry images`'s question
(`BR-REG-005`, `ADR-069`). No manifest is accepted or needed.

An engine's own image listing answers only repository, tag, id, age and size, so an untagged
former build is indistinguishable from anything else untagged. Every fact needed to explain
it is already stamped on the image; this is the command that reads them back. Images cairn
did not build MUST be excluded, but their count MUST be reported, so the command is never
mistaken for a complete inventory.

**On a host colocating roles, "cairn built this" and "cairn built this *here*" are different
claims** (`ADR-061`) — provenance labels travel with a pulled image exactly as they do with a
built one. An image carrying the `cairn-adopt-owned` marker (`BR-DEPLOY-023`) MUST be excluded
from this report entirely (`ADR-072`), same as an image cairn did not build — once
`cairn-adopt` claims an image as currently running, accounting for it is its question, not
this one's. For everything else shown, cairn MUST show whether it still carries the
`cairn-build-owned` marker (`BR-BUILD-018`): present means this host's build role produced it
and it has not been shared; absent means it was pushed, or arrived some other way.
*(BR-BUILD-011, BR-BUILD-014, BR-BUILD-018, BR-DEPLOY-023, ADR-032, ADR-061, ADR-069,
ADR-072)*

**`BR-CLI-006`** *(vendor, struck)* — `cairn-build vendor status | sync` is retired. Cairn no
longer syncs from upstream `frappe_docker`; it owns its recipe directly and carries no command
surface for tracking an external pin. *(ADR-059)*

**`BR-CLI-009`** *(no declared environment, no auto-vivification, `ADR-052`)* — `assign-tag
--manifest <path>` and `retire --manifest <path>` MUST **error if that manifest declares no
environment** (`<path> declares no environment`) — there is nothing to point or decommission.
Since a manifest declares at most one environment (`BR-DEPLOY-009a`), there is no "wrong name"
to guard against — only "no name at all."

Whether the environment's registry pointer already exists is a separate, later question
`assign-tag` answers by resolving and checking the registry (`BR-CLI-004`), never by refusing
up front.

`retire --manifest <path>` removes the declaration from that manifest (the operator's edit,
not cairn's — cairn only validates and warns), touches **no images**, and MUST warn that the
**registry tag name persists** (GHCR has no per-tag delete — see `03-deploy.md`).
*(BR-DEPLOY-009, BR-DEPLOY-009a, ADR-052)*

**`BR-CLI-010`** *(prod gate)* — Any command that creates, moves, or retires a
**`:production`** pointer MUST require **explicit confirmation** — interactive prompt by
default, `--yes` to skip for automation. *(BR-DEPLOY-015)*

**`BR-CLI-016`** *(build transcript — attended CLI only)* — cairn recognises **three
execution contexts** (`ADR-031`), and writes a transcript in exactly one of them:

| Context | Behavior |
| --- | --- |
| Target daemon (systemd) | stdout/stderr only (`BR-DEPLOY-019`) |
| Unattended CLI (CI) | stdout/stderr only |
| **Attended CLI** (human at a terminal) | terminal **and** transcript file |

- Attendedness MUST be detected from **stderr being a TTY**, and MUST be overridable in
  both directions by `--transcript <path>` and `--no-transcript`.
- In attended mode cairn MUST write the full build output to a transcript **and** keep it
  streaming live to the terminal — the transcript replaces neither the live output nor
  the operator's ability to `tee`.
- Attended builds MUST request **plain, append-only** engine progress, so both scrollback
  and the transcript stay readable. Unattended contexts are unaffected.
- The default location MUST be `/tmp/cairn-<uid>/`, created mode `0700`; cairn MUST refuse
  to use it if it exists and is not owned by the invoking user, or is not a real directory.
  Files are named `<timestamp>--<image_name>.log` — from the **manifest's** image name, not
  the built tag, because the file must be open before ref resolution can compute a tag and
  the resolution is itself part of what the transcript records. The primary tag is written
  into the transcript instead. A `last-build.log` symlink points at the newest, and a
  `last-failure.log` symlink is updated on failure so a later success cannot bury it.
- The transcript path MUST be printed **when the build starts and when it ends**, so the
  path survives an interrupted run or a lost terminal.
- A failed build MUST retain its transcript.
- The location MUST be overridable by `transcript_dir` in build config (`BR-CFG-008`).

*(ADR-031, BR-CFG-008, BR-DEPLOY-019)*

**`BR-CLI-018`** *(prune — build machine, `ADR-061`, `ADR-072`)* — `cairn-build prune
[--keep <n>] [--dry-run] [--yes]` reclaims space on the **build** machine, under three
concentric restrictions:

1. Only images carrying cairn's own provenance labels (`BR-BUILD-011`) are candidates — and,
   since `ADR-072`, an image also carrying the `cairn-adopt-owned` marker (`BR-DEPLOY-023`)
   is never one of them, excluded at the same step `BR-CLI-005` excludes it from `images`.
2. **Nothing else is protected.** Of the remaining candidates, every one is eligible: one
   still carrying `cairn-build-owned` (`BR-BUILD-018`, not yet pushed); a fully untagged
   orphaned duplicate whose tags already moved to a newer build of the same input hash
   (`BR-BUILD-014`); and, since `ADR-072`, a **pushed** image with real tags that nothing
   local is currently running — no longer unconditionally protected, as `ADR-061` originally
   had it. What made that protection unconditional before was having no signal for "still in
   use"; restriction 1's exclusion is now that signal.
3. Of the eligible pool, only images beyond the newest `<n>` per **input hash** (default 1)
   are actually removed — `<n>` counts a group's newest members regardless of ownership
   status, so this reads as a grace window rather than rollback headroom: build-machine
   storage is not a registry and offers no such guarantee (`BR-BUILD-018`), it is simply
   giving a just-built, not-yet-pushed image a moment before it is considered fair game.

Removing an eligible image MUST NOT pass the engine's `--force`: a removal needing it is one
to report, not perform. Since an eligible-but-still-owned image typically carries multiple
local tags at once (primary, moving, and the owned marker — `BR-BUILD-008`, `BR-BUILD-018`),
and engines refuse `image rm <id>` on a multiply-tagged image without `--force`, cairn MUST
remove each of that image's tag references individually — the last one is what actually frees
the disk — falling back to removal by id only for an image with no tags at all.

cairn MUST NOT remove volumes or containers under any option (`ADR-022`), MUST report what
it will remove and confirm first (`BR-CLI-011`), and MUST state what it is leaving alone so
the omission is never a surprise. A removal that fails MUST NOT abort the rest.

**Label-scoping is a cache-safety mechanism, not merely tidiness.** On podman, an untagged
image may be a **build-cache stage** rather than a former build — the `builder` stage of the
recipe's Containerfile is untagged, larger than the final image, and is what lets a rebuild
skip `bench init`. A prune written against "dangling" would delete it and silently convert
every later build into a cold one. cairn's labels are applied only at the **final** commit,
so a stage image never carries them, and a label-scoped prune cannot reach the cache. cairn
MUST therefore never prune by danglingness. *(BR-DEPLOY-006 is the target-side counterpart —
though, unlike this command, it keeps rollback headroom rather than reclaiming only what was
never shared, since the target has no registry-backed "shared" signal of its own to key off.
ADR-032, ADR-061, lessons §12)*
