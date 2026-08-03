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
