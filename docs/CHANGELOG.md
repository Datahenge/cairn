# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-08-04 (later — archived 2026-07-21 through 2026-07-27 to `docs/archive/`)

This file hit its word-count sprawl limit a second time (`W-014`) on the entry below.
Rather than bump the ceiling again, archived the older half verbatim — content only,
nothing rewritten or summarized — to
[`docs/archive/CHANGELOG-2026-07.md`](archive/CHANGELOG-2026-07.md), which carries its
own dated index. This file now holds only 2026-08-03 onward; the allowlist ceiling
dropped back down to match. `W-014` closed.

---

## 2026-08-04 — `CONFIGURATION.md` retired; reference migrated to `userdocs/`

Retired, not rewritten — resolves `DOCS-01`. Content re-verified against source, split into
`userdocs/reference/{manifest,builder-config,target-descriptor}.md`; inbound references
repointed. Detail: `open/OPEN_WORK.md` `W-012`, `open/OPEN_DECISIONS.md` `DOCS-01`.

---

## 2026-08-03 (later still — `cairn-registry`: retention/GC for the local registry)

Raised ahead of `W-001`: the local registry's port/storage were hardcoded, and cairn had never
deleted a registry tag — content-hash tags accumulate forever, unbounded disk growth.

**New `ADR-048`**: registry becomes its own CLI, `cairn-registry`, amending `ADR-046` as
`ADR-046` amended `ADR-018`. `stage_registry` moves out of `cairn-build setup` (pre-1.0, no
shim needed). **New `08-registry.md`** (`BR-REG`, added to `AGENTS.md`): config file
(bind-mount `data_dir`, not an anonymous volume), provisioning, and a retention algorithm
needing no `[cairn.environments]` read — eligible only if every tag on a digest matches
cairn's content-hash shape (`BR-BUILD-008`); a moving or environment tag protects it.
`keep_last`/`max_age_days` decide deletion; `gc` reclaims blobs, read-only.

`06-cli.md` gained `BR-CLI-024`–`027`.

---

## 2026-08-03 (later yet again — GHCR-default cleanup and `image_base` removed)

Two consistency fixes, raised by Brian while reviewing the `builder.toml` documentation.

**GHCR was still the de facto default in practice, though not in stated policy.** `ADR-038`/
`ADR-039` (2026-07-25) had already downgraded GHCR from "recommended default" to "one option,
weakest on cost," and `ABOUT_REGISTRIES.md`/`ABOUT_GHCR.md` already said so — but the reversal
was never reflected back into `ADR-009`, whose title and body still said "GHCR recommended
default," and the scaffolded starter manifest (`provision.MANIFEST_TEMPLATE`, written by
`cairn-build setup`) still pre-filled `[cairn.registry] host = "ghcr.io"`. A new deployment
therefore got GHCR by default in practice — the path of least resistance — despite the
documented policy saying otherwise.

- **Amended `ADR-009` in place**: added a 2026-07-25-dated amendment noting the reversal and
  pointing to `ADR-038`/`ADR-039`/`ABOUT_REGISTRIES.md`; index summary in `docs/adr/README.md`
  updated to match (precedent: `ADR-034`).
- **`provision.MANIFEST_TEMPLATE` no longer includes `[cairn.registry]`.** It's optional
  (`BR-CFG-011`/`BR-CFG-014`) and absence already means local-only, which is the correct
  default — no registry should be pre-selected for a client that hasn't chosen one.
- **`CONFIGURATION.md`/`README.md`** manifest examples dropped the same block; `CONFIGURATION.md`
  gained a separate `[cairn.registry]` example (host `registry.example.com`, a neutral
  placeholder) shown only once the deployment has actually chosen a registry, pointing to
  `ABOUT_REGISTRIES.md` for how. The `builder.toml` example's `registry` value was also swapped
  from `ghcr.io` to the same neutral placeholder, so no doc anywhere implies a default registry.

**`image_base` removed** (`BuildConfig.image_base`, `CAIRN_IMAGE_BASE`, the `image_base` entry
in `BUILD_CONFIG_KEYS`). Brian: "I just cannot think of a reason it would be useful." It was a
full override of the composed `<registry>/<namespace>/<image_name>` string, kept machine-local
by `ADR-039`; no concrete scenario for it was ever documented beyond "rare," and it duplicated
what `BR-CFG-011`'s composition already answers definitively from `cairn.toml` + `[cairn.registry]`.

- **Amended `ADR-039` in place**, recording the removal and its (thin) original rationale.
- **Updated** `docs/requirements/05-config.md` (`BR-CFG-012`'s env-var list), `ADR-042` (same),
  `docs/technical/CONFIGURATION.md` (dropped the key's row and example, and the `CAIRN_IMAGE_BASE`
  mention).
- **Code:** `config.py` (`BUILD_CONFIG_KEYS`, `BuildConfig`, `resolve_image_base`), `push.py`
  and `cli_build.py` (dropped the `image_base` half of the "is a registry configured" check).
  `build.BuildPlan.image_base` — the unrelated *computed* image-base name used for tagging — is
  untouched; only the machine-local override key is gone. Tests updated in `test_config.py`
  and `test_push.py`; full suite green.

## 2026-08-03 (yet later still — `BR-CLI-022`/`BR-CLI-023` implemented, `v0.2.0`)

Implemented `W-013`: `cairn-build setup --client <name>` provisioning `/srv/cairn/<name>/`
scaffold-only-if-absent, and the `setup`/`setup-timer` split on both CLIs (`ADR-047`).
`provision.py` gains `MANIFEST_ROOT`/`MANIFEST_TEMPLATE`/`stage_manifest`/`_require_root`
(timer stages now gate their own privilege, no longer running behind `preflight`);
`doctor.py` gains `check_known_manifests` (informational only); both CLIs gain
`setup-timer`, carrying the flags `setup` no longer touches. New test coverage for all of
it; full suite green, `ruff` clean. `05-implementation-index.md`/`open/OPEN_WORK.md`
updated — `W-013` now tracks live-VPS verification, not implementation. Version bumped to
`0.2.0`: `--client` becoming required and the timer leaving `setup` are both breaking
changes to its existing surface.

## 2026-08-03 (later still yet — `environment.toml` renamed to `adopt.toml`)

Renamed the target descriptor's filename for explicit ownership, matching `builder.toml`'s
own naming: each machine-local file is now named for the one CLI that reads it
(`cairn-adopt` ↔ `adopt.toml`, `cairn-build` ↔ `builder.toml`) rather than requiring the
reader to already know "the environment one" means the target's file.

- **Amended `ADR-034` in place** (decided 2026-07-25, filename amended 2026-08-03) — every
  other property (fixed path, TOML, one per host) is unchanged.
- **Updated `BR-DEPLOY-010a`**, `docs/adr/README.md`'s index row, `ADR-042`'s cross-reference,
  and `docs/plans/next-steps.md`.
- **Code:** `descriptor.DESCRIPTOR_PATH`, `provision.DESCRIPTOR_PATH`, `adopt.py`'s generated
  install-path comment (also corrected, while there, its stale `cairn adopt` → `cairn-adopt
  examine` reference from before the `ADR-046` split), and `cli_adopt.py`'s `reconcile` help
  text. Tests in `test_descriptor.py`, `test_adopt.py`, `test_cli_adopt.py`, `test_provision.py`
  updated to match; full suite re-run green.
- **`README.md`/`CONFIGURATION.md` left stale on this too**, folded into `W-012`'s existing
  scope rather than patched piecemeal.

## 2026-08-03 (later yet — canonical manifest home, `ADR-047`)

Raised while writing the Builder guide against a real client VPS: the manifest location we'd
suggested (`~/cairn-test`) wasn't multi-user-visible and didn't match the project's own
existing `/srv/acme/cairn.toml` example, which nothing actually created or enforced. Worked
through the design with Brian and landed **`ADR-047`**:

- **Canonical location `/srv/cairn/<client>/cairn.toml`** — not bare `/srv/<client>/`, since a
  host's `/srv` may hold unrelated data cairn has no business assuming about; `/srv/cairn/` is
  cairn's own namespace.
- **`cairn-build setup --client <name>`** (required, no default) provisions that directory,
  group-shared the same way `ADR-043` already shares `/etc/cairn`, and scaffolds a starter
  `cairn.toml` from the existing published example — **only if one isn't already there**;
  never overwrites. Strikes `README.md`'s "no scaffolding command" line (left for the `W-012`
  rewrite, not fixed piecemeal).
- **`setup` / `setup-timer` split**, both CLIs — build/reconcile automation becomes its own
  top-level command instead of a `setup --only timers` flag most first-time readers wouldn't
  find before running their first build or reconcile by hand.
- Added `BR-CLI-022`, `BR-CLI-023`; amended `BR-CLI-021`.
- Logged `W-013` in `open/OPEN_WORK.md` to implement this in `cli_build.py`/`cli_adopt.py`/
  `provision.py` — requirements land before code, per the working agreement.

## 2026-08-03 (even later — Get Started, verified against a live test VPS)

Began writing `userdocs/get-started/index.md` for real, sourced from a live install/config
session against a client test VPS rather than written speculatively (`W-012`).

- **Wrote prerequisites, install, and `doctor` sections**, each confirmed against real
  command output (Docker v29.6.2, git v2.47.3, `sudo pipx install --global datahenge-cairn`,
  `cairn-build doctor` — 8 checks, 2 expected warnings on an unconfigured machine).
- **Trimmed `userdocs/index.md`'s work-in-progress note** — no longer forwards installation
  questions to the stale README section now that Get Started covers that ground itself;
  Guides/Reference topics still forward to the root-level technical docs.
- **Marked `W-012` `in_progress`** in `open/OPEN_WORK.md` — manifest-writing and first build
  are next; `README.md` gets cut down to a docs-site pointer once Get Started covers install
  through a verified first build.
- **Clarified, mid-session, that `cairn-adopt examine` is a target-side command** and must not
  be folded into the builder-role Get Started flow — a builder cannot assume co-location with
  any target's running Compose project. Adopting an already-running deployment is its own,
  separate guide, written from the target's side, once `cairn-adopt`'s own Get Started
  content exists.
- **Split Get Started at the Install boundary.** Content from `doctor` onward moved to a new
  `userdocs/builder/index.md`, added to `mkdocs.yml`'s nav. Get Started now ends role-neutral
  (installing cairn, explaining the two binaries) so a target-only reader isn't routed through
  builder-specific content; a "Target" guide is named as a future nav entry but not yet
  stubbed, matching the rule that a nav entry only gets written once its content is verified.

## 2026-08-03 (later still — documentation review session)

Full documentation review pass (frontmatter, clarity, dedup, link integrity, sprawl control)
across `docs/`, `decisions/`, `open/`, `userdocs/`, and root files. Findings and fixes:

- **Corrected `ADR-037` follow-through.** `ADR-014`, `ADR-022`, and `ADR-024` still described
  opt-in `bench install-app` as a sanctioned exception after `ADR-037` struck it entirely;
  added correction notes to each. `decisions/011` still called the primary tag "immutable"
  after `ADR-032` retracted that word; corrected to "deterministic".
- **Fixed stale CLI naming** from before the `cairn-build`/`cairn-adopt` split (`ADR-046`) in
  `docs/technical/ABOUT_GHCR.md`, `docs/00-project-scope.md`, `docs/requirements/03-deploy.md`
  (`cairn retire` → `cairn-build retire`), and `CURRENT_CONTEXT.md` (`cairn vendor sync` →
  `cairn-build vendor sync`). `README.md` and `docs/technical/CONFIGURATION.md` remain
  deliberately stale per the `ADR-046` commit message; tracked as `W-012` in
  `open/OPEN_WORK.md`.
- **Fixed a dangling reference** in `BR-CLI-013` (06-cli.md) to a `status` command that was
  never defined; named the actual commands.
- **Trimmed duplicated rationale.** `BR-CFG-013`'s "why" paragraph restated
  `docs/technical/ABOUT_REGISTRIES.md`'s rule 1 almost verbatim; trimmed to a one-line
  pointer at `ADR-038` and that document.
- **Split `docs/technical/04-lessons-learned.md`** (was ~3,200 words, out-of-order numbering)
  into an index plus three topic files — `04a-lessons-build-engines.md`,
  `04b-lessons-caching-and-provenance.md`, `04c-lessons-process-notes.md` — renumbered
  sequentially within each. Updated the two external citations that pointed at old section
  numbers (`docs/adr/027`, `docs/plans/next-steps.md`) and removed the now-unneeded
  `.docs_check_allowlist` entry.
- **Added missing frontmatter** to `docs/requirements/00-overview.md` through `07-docs.md`,
  `docs/00-project-scope.md`, and `docs/plans/*.md` (all now carry `status`/`owner`/`purpose`).
  Decided, with Brian, to formally exempt `README.md`, root `CHANGELOG.md`, and
  `userdocs/**/*.md` from the frontmatter convention — none are rendered by a tool that
  strips YAML frontmatter, so adding it would show as literal text; recorded in
  `docs/technical/01-documentation-conventions.md`.
- **Marked `docs/plans/next-steps.md` and `docs/plans/phase-1-build.md` `status: archived`.**
  `next-steps.md`'s live-backlog role was already absorbed into `open/OPEN_WORK.md`
  (seeded from it the same day); `phase-1-build.md`'s own banner called for a refresh "at
  Phase-4 start" that never happened — now tracked as `W-011`.
- **Opened `DOCS-01`** in `open/OPEN_DECISIONS.md`: whether to split
  `docs/technical/ABOUT_GHCR.md` now or wait for its already-planned migration into the
  `userdocs/` mkdocs nav.
- Verified: `docs/adr/README.md` and `decisions/README.md` index completeness, all three
  archived-ADR stubs (023/028/041), all frontmatter `status` values, and no `BR-`/`ADR-`
  leakage into `README.md`/`userdocs/`. All clean — no changes needed.

## 2026-08-03 (yet later still — `06-cli.md` reorganized into role sections, not split into two areas)

Brian asked whether `BR-CLI`/`06-cli.md` should split into two areas to mirror the
`cairn-build`/`cairn-adopt` binary split. Answer: no — `05-config.md` already solved the
identical tension (two roles, `BR-CFG`) with one file sectioned `A. Target` / `B. Build`
rather than two area files, precisely because most of what a CLI-conventions area holds
(logging, `--json`, config discovery, help text) is shared house style that applies
identically to both binaries; splitting would either duplicate that content across two
files or need a third "shared" area just to hold it.

Restructured `06-cli.md` to the same pattern: **Substrate** (the one-package/two-CLI fact),
**A. `cairn-build` commands**, **B. `cairn-adopt` commands**, **C. Commands on both CLIs**
(`doctor`, `setup`), **D. Shared conventions**. This also corrected a placement error from
the split above: `BR-CLI-009` (existence guards) and `BR-CLI-010` (prod gate) are entirely
about the pointer verbs (`new-tag`/`retag`/`retire`) — build-only — and had been left under
a general "Guards & safety" heading; `BR-CLI-016` (build transcript) is build-only in the
same way and had been left under "Conventions." All three moved into section A. No
requirement text changed, no ID renumbered — only which section each lives under.

---

## 2026-08-03 (later still yet — `BR-DATA-008` brought into line with the already-struck `install-app` opt-in)

Caught while auditing the docs during the `cairn-build`/`cairn-adopt` split above: `BR-DATA-008`
still described the **opt-in** `bench install-app <apps>` path `ADR-023` originally proposed —
but `ADR-037`/`BR-DEPLOY-003a` had already struck that path entirely, back on 2026-07-25, and
`BR-DATA-008` was simply never updated to match. Two places in the docs disagreed about whether
cairn ever runs `install-app`.

Brian clarified the intended behavior: cairn itself must never initiate `bench install-app`,
under any circumstance — but the human operator legitimately may need to run it by hand, when a
newly-deployed image introduces a Frappe App the target site has never had installed. Rewrote
`BR-DATA-008` to say exactly that (an operator-only, by-hand gap, never a cairn code path), and
added a "superseded" cross-link from `ADR-023` to `ADR-037`, which struck it but never linked
back.

---

## 2026-08-03 (later still — `cairn-build` / `cairn-adopt`: two CLIs replace the unified `cairn` binary)

Raised while drafting the `userdocs/` Get Started guide from a real TEST-VPS deployment: a
single onboarding narrative kept forcing an assumption about which reader was reading, since
"stand up frappe_docker, then adopt it" and "build and push an image" are genuinely different
stories that one linear page can't tell without picking one. Brian also flagged that
"reconciler" reads, to anyone who knows ERPNext, like an accounting feature name (Bank
Reconciliation Tool, Payment Reconciliation) rather than a deploy agent — a real domain
collision, not a style complaint — and asked whether cairn's single binary should split, the
way a Rust project might split into a shared lib crate plus two bin crates.

Landed as `ADR-046` (supersedes `ADR-018`; amends `ADR-028`, `ADR-035`, `ADR-040`, `ADR-043`):
still **one package** (`datahenge-cairn`, no dependency/workspace split — that question,
raised mid-discussion, turned out to be moot, since the shared code was never going to be a
separate distribution), but **two console-script CLIs** in place of the unified `cairn`:
`cairn-build` (build/control) and `cairn-adopt` (target). No unified `cairn` command, no
`datahenge-cairn` alias (its only reason to exist — a PyPI name collision fallback — no longer
applies once neither binary is named `cairn`).

Consequences threaded through the requirements:
- **`cairn doctor`'s role-detection is retired** (`ADR-028` superseded) — `cairn-build doctor`
  and `cairn-adopt doctor` each run exactly one fixed check set; the binary invoked is the role
  signal now.
- **`cairn adopt` is renamed `cairn-adopt examine`** — `cairn-adopt adopt` read as a stutter and
  wrongly implied a change was being made, when the command is a strict read-only survey.
  "examine" pairs with `doctor`'s existing diagnostic register.
- **`cairn-provision` is retired as a separate program** (`ADR-040`, `ADR-043` amended) — its
  work becomes `setup`, a privilege-gated subcommand nested in each CLI (`cairn-build setup`,
  `cairn-adopt setup`), which also removes the `--role` flag entirely: each CLI's `setup`
  provisions only what that role needs. `install` was considered and rejected as the subcommand
  name — cairn already disclaims installing a Frappe App (`BR-DEPLOY-003a`), and reusing
  "install" for cairn's own host bootstrapping would echo that. The seven-point installer
  contract (`BR-DEPLOY-021`) and `/etc/cairn` group-sharing (`ADR-043`) carry over unchanged.

Revised `BR-CLI-001` through `BR-CLI-020`, added `BR-CLI-021` (`setup`), revised
`BR-DEPLOY-021`/`022`'s installer language, and rewrote `00-overview.md`'s "two roles" section
to match. Also fixed imprecise wording surfaced along the way: "cairn never installs an app"
now reads "cairn never installs a Frappe App" everywhere it appears in living text
(`BR-DEPLOY-003a`, `06-cli.md`, `next-steps.md`, `High Level Motivations and Workflows.md`) —
dated historical entries in `CHANGELOG.md`/`01-decisions-closed.md`/`03-discussion-log.md` were
left as-is, since rewriting a dated record would misrepresent what was actually said at the
time.

Code has not changed yet — `src/cairn/cli.py` still implements the old single-binary surface,
and `README.md`/`CONFIGURATION.md` still describe it. That catch-up is deliberately a separate,
later step.

---

## 2026-08-03 (later — new `DOCS` requirement area: published documentation site)

Brian asked to add a requirement for high-quality online documentation, GitHub Pages-based
like Datahenge's BTU project. Clarified four open questions with him before drafting
(Scribe Phase 2 dialogue): source-tree location, tooling, publish domain, and initial
content scope. Decided: a new top-level `userdocs/` directory (kept structurally separate
from the internal `docs/` requirements root, since `/CLAUDE.md` forbids `BR`/`ADR` IDs from
reaching a user); mkdocs + mkdocs-material, matching BTU's proven pattern; the default
GitHub Pages URL, no custom domain; and a lean initial scope — stand up the site + CI
publish pipeline with placeholder content, deferring migration of the existing root-level
docs (`README.md`, `CONFIGURATION.md`, `ABOUT_GHCR.md`, `ABOUT_REGISTRIES.md`) into the
site's nav to later, separate work.

Recorded as `ADR-045` (`docs/01-decisions-closed.md`) and a new area,
`docs/requirements/07-docs.md` (`BR-DOCS-001` through `BR-DOCS-007`), added to the
table of contents in `00-overview.md`.

---

## 2026-08-03 (overview — surfaced the two roles/modes up front)

Brian asked what cairn's two roles/modes are; the answer existed only inside `ADR-018`
(build/control vs. reconcile, one package) and `ADR-028` (`cairn doctor` detects its role
from context), buried in the decision register rather than stated where a reader would
first look. Added a "Two roles, one tool" section to `00-overview.md`, right after system
purpose, summarizing the role split and its enforcement (credentials, not code) and
pointing at the `ADR`s and BR areas that cover each role. No new requirement — a
clarity-only edit, so no new `BR` IDs.

---

Entries from 2026-07-21 through 2026-07-27 are archived at
[`docs/archive/CHANGELOG-2026-07.md`](archive/CHANGELOG-2026-07.md).
