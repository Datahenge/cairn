---
status: authoritative
owner: technical
purpose: ADR-069 — cairn-build images becomes local-only; cairn-registry images gains --host/--namespace/--image and provenance detail, splitting the whole introspection surface by which CLI owns the answer
---

# ADR-069 — `images` splits cleanly by role: `cairn-build` = local, `cairn-registry` = registries

**Decided:** 2026-08-06 (Brian).
**Amends:** `BR-CLI-005`, `BR-REG-005`.
**Supersedes:** an earlier same-day draft of this file that only added a `--local` fallback to
`cairn-build images` when no manifest was given — abandoned before implementation once the
design below replaced it.

## Raised

Three rounds, same conversation:

1. Brian ran `cairn-build images` bare and got a hard error — no manifest, so no repository to
   read. The command's help text also claimed "reads the registry by default" without saying
   that default needs a manifest. First fix considered: fall back to `--local` when no manifest
   is known.
2. Brian pushed back on the premise: if the point is examining a **registry**, deriving the
   repository indirectly from a manifest's `image_name` felt like the wrong lever — why not
   name the registry/repository directly?
3. Restated more sharply: three genuinely different questions, one per CLI role. `cairn-build
   images` (zero args) = "what does *this build machine* hold?" `cairn-registry images` = "what
   does *a registry* hold?" — with sub-questions of its own: which registry (local or remote),
   which namespace (all, or one client), which image (one name, maybe globbed). "The builder
   talks about things the builder owns; the registry talks about things registries own (a local
   one, or a remote one)."

A fourth constraint surfaced mid-design, not from Brian but from re-reading the userdocs
already shipped: `userdocs/registry/ghcr-setup.md` and `ghcr-tags-and-troubleshooting.md`
already use `cairn-build images` (manifest-driven) against **GHCR** — a real, authenticated,
third-party registry — to check what a tag points at before deleting a version on GitHub. That
path works today because the single-repository read (`registry.tags`/`registry.inspect`) does
the full anonymous-then-bearer-token exchange (`BR-CFG-010`), the same credential dance
`push`/`assign-tag` use. `registry.catalog()` — the only way to *enumerate* a registry's
repositories — is anonymous-only by design, documented as scoped to cairn's own self-hosted,
unauthenticated registry (`BR-REG-003`). Folding registry introspection into `cairn-registry
images` only works without regressing the GHCR workflow if a **specific, named** repository can
still go through the authenticated single-repo path instead of the catalog.

## Decision

**`cairn-build images` becomes `[--json]`, nothing else, unconditionally local.** No
`--manifest`, no `--local` (there is no other mode to flag), no registry read of any kind. It
answers one question regardless of environment: what does this machine hold, why, and which is
superseded. `_registry_repository` and the registry branch of `images_command` are deleted, not
deprecated — nothing behind them survives.

**`cairn-registry images` becomes `[--host HOST] [--namespace NAME] [--image PATTERN] [--json]`**
and gains the provenance detail the old `cairn-build` registry mode used to show (frappe/app
versions, the `cairn-build-owned` marker), so that capability is relocated, not lost:

- **`--host`** — defaults to this machine's own registry (`registry.toml`); any other value
  queries that registry instead, local or remote.
- **`--namespace`** / **`--image`** — narrow which repositories are inspected. `--image` accepts
  a glob (`fnmatch`).
- **Exact `--namespace` + `--image`, no glob** → cairn reads that **one** repository directly —
  `images.inspect_registry`, the same tag-by-tag authenticated read `BR-CLI-005`'s old registry
  mode used. No catalog call. This is what keeps GHCR reachable: `cairn-registry images --host
  ghcr.io --namespace <owner> --image <name>` after a `docker login`/`podman login`, replacing
  what `cairn-build images --manifest ...` used to do.
- **Anything else** (no `--image`, or `--image` is a glob) → `registry.catalog(host)` enumerates
  repositories first, then the same `--namespace`/`--image` filter narrows the result before each
  matched repository is read the same way. Catalog access is anonymous-only; against a registry
  that requires auth for it (most third-party registries, GHCR included), this fails plainly.
  That's an inherent property of catalog-wide enumeration, not something to work around here —
  it is exactly why the direct single-repository path above exists.
- Output, for every path, is grouped by input hash/digest with provenance labels read the same
  way `--local` already reads them, and a repository holding zero cairn images is counted, not
  itemized — mirroring `BR-CLI-005`'s treatment of non-cairn local images.

**Fixed incidentally:** the existing `cairn-registry images`' "Repository" line printed the bare
catalog name; `userdocs/registry/cli.md` already documented (incorrectly, until now) that it
prints the full reference with registry host. The rewrite prints the full reference, making the
doc's claim true and the line copy-pasteable into a target descriptor's `image` field, which was
the documented intent.

## Consequences

- `cli_build.py`: `images_command` loses `local`/`manifest_path` params; `_registry_repository`
  deleted.
- `images.py`: `registry_as_json` becomes `registry_payload`, returning a `dict` instead of a
  JSON string — `cli_build.py` was its only caller and no longer calls it; `cli_registry.py`
  assembles a multi-repository JSON wrapper from one `dict` per repository and serializes once.
  `inspect_registry`/`group_registry`/`render_registry` are unchanged and now serve
  `cli_registry.py` instead of `cli_build.py`.
- `cli_registry.py`: `images_command` gains `--host`/`--namespace`/`--image`; its private
  `_grouped_tags`/`_repository_json` helpers are deleted in favor of `images.py`'s
  provenance-aware equivalents.
- `userdocs/builder/index.md` drops its `--local` example (bare `cairn-build images` now).
  `userdocs/registry/ghcr-setup.md` and `ghcr-tags-and-troubleshooting.md` replace their
  `cairn-build images` references with the `cairn-registry images --host ghcr.io --namespace
  ... --image ...` form. `userdocs/registry/cli.md` documents the new flags and the corrected
  repository-line format.
- Tests: `test_cli_build.py`'s registry-mode `images` tests are removed (the behavior no longer
  exists there); its local-mode tests drop `--local`. `test_cli_registry.py` gains coverage for
  `--host`/`--namespace`/`--image` and the catalog-vs-direct-lookup split.

*(BR-CLI-005, BR-REG-001, BR-REG-005, BR-DEPLOY-005, BR-BUILD-011, BR-BUILD-018, BR-CFG-010,
ADR-032, ADR-036, ADR-061)*
