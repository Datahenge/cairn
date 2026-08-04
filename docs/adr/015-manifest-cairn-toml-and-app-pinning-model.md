---
status: authoritative
owner: technical
purpose: ADR-015 — Manifest (`cairn.toml`) and app-pinning model
---

# ADR-015 — Manifest (`cairn.toml`) and app-pinning model

**Decided:** 2026-07-21
cairn owns a human-friendly **standalone `cairn.toml`** manifest that declares **one
image** (environment-agnostic) and compiles into the build inputs. Structure:
`[cairn] image_name`; a special `[cairn.frappe]` (`url`, `ref`) driving `FRAPPE_PATH`/
`FRAPPE_BRANCH`; an **ordered** `[[cairn.apps]]` list (`name`, `url`, `ref`) for ERPNext
+ custom apps → `apps.json`; and `[cairn.build]` version knobs + passthrough.

**App/Frappe pinning — Option A (resolve-and-record), superseding the original
"pin by commit":** verified from bench source (`bench/app.py`) that both `FRAPPE_BRANCH`
and `apps.json` clone via `git clone --branch <ref>` (no post-clone checkout; `.git` is
then stripped inside the same Containerfile `RUN`), so a **raw commit SHA is not
supported** — refs must be a branch or tag. Therefore cairn **resolves every ref to its
commit at build time (`git ls-remote`) and records it** in provenance (driving
`CACHE_BUST`, the image tag, and labels), but does **not** freeze commits into the build.
The manifest SHOULD pin to **tags** for reproducibility; cairn SHOULD warn on a moving
branch. True commit-pinning would require editing the vendored tree (forbidden,
`ADR-001`) or Option C's build-time git-mirror machinery (rejected as too heavy); the
sanctioned path if it ever becomes essential is a deliberate fork (`ADR-021`).

**Ordered list:** `[[cairn.apps]]` order is significant (install order); documented
prominently in `README.md` and MUST appear inline in every shipped template
(`BR-BUILD-003`). Requirements: `docs/requirements/02-build.md`.

**Branch vs. tag is a real choice, not a lint to silence (added 2026-08-04).** A branch
(e.g. `version-16`) always resolves to that branch's newest commit at build time, so pinning
to one lets a manifest auto-track a target's latest release with no edit required — that is
exactly "always the latest" as a stated intent, not a mistake. The cost is reproducibility:
two builds of the same manifest, days apart, can resolve to different commits and produce
different images. A tag trades the auto-update away for a fixed commit. `BR-BUILD-005`
warns rather than refuses for this reason, and the scaffolded template (`BR-CLI-022`)
defaults to a tag, since a first-time user hasn't yet stated which tradeoff they want.
