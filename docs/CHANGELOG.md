# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

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

## 2026-07-27 (later still — recorded a local git mirror as a deferred `BR-BUILD-016` successor)

After `BR-BUILD-016` shipped, Brian asked whether a future local git mirror — refreshed via
the SSH deploy key already working host-side, served to the build over `--network=host` so
the BuildKit sandbox needs no credential at all — would sidestep the problem entirely. It
would, and would eliminate `github_auth.py`'s reason to exist along with it. Checked first
whether this had already been discussed: it echoes `ADR-015`'s **Option C** ("build-time
synthetic-ref git mirror"), rejected as too heavy — but that mirror existed to fake
commit-SHA pinning, a different job than making a private repo reachable. Recorded as a new,
explicitly *not a revival*, open decision rather than folding it into the closed one.

- **Added `ADR-044`.** Deferred, not a default: `BR-BUILD-016` already meets today's concrete
  need. Recorded as the strong long-term replacement candidate if PAT-based auth ever proves
  insufficient, with the real costs sized (a new provisioning stage, a freshness mechanism,
  the `--network=host` buildx-driver entitlement question) rather than left implicit.

---

## 2026-07-27 (later still — private `github.com` apps, one token, `BR-BUILD-016`)

Brian's clients own the private app repos he builds against — he can't create a fine-grained PAT
himself (he isn't the repo owner), and a classic PAT was rejected outright as too broad. He first
asked about an SSH deploy key already set up on the VPS (`git@github-clientrepo:...`); traced
through, that works today for `git ls-remote` (a bare host-side subprocess) but not for the actual
build — the clone happens inside an isolated BuildKit sandbox with no access to the host's SSH
config at all, and forwarding it in would mean editing the vendored, unmodified Containerfile
(`ADR-007`), i.e. the deferred fork escape hatch (`ADR-021`), not a today-sized change. Resolved
instead: the client creates a fine-grained PAT scoped to just their one repo and hands Brian the
token — same isolation a deploy key gives, delivered as a bearer credential instead, which *can*
be embedded in the HTTPS URL with zero Containerfile changes.

- **Added `BR-BUILD-016`.** One token, `$CAIRN_GITHUB_TOKEN`, authenticates a `github.com` app
  URL for both `git ls-remote` (`resolve.py`) and the `apps.json` build secret (`appsjson.py`
  content, via a new `BuildPlan.apps_json_secret` property in `build.py`). Deliberately not a
  `builder.toml`/`BUILD_CONFIG_KEYS` entry — that file is shared and group-writable
  (`BR-DEPLOY-022`), the wrong place for a secret.
- **New module `github_auth.py`** — the one seam every caller routes through: `authenticated()`
  injects the token only for `http(s)://github.com/...` (never another host, never an SSH form),
  and `redacted()` strips the token from text that might otherwise echo it back (git's own error
  output on a failed authenticated `ls-remote`).
- **Provenance, `--dry-run`, and error messages stay token-free.** `BuildPlan.apps_json` (used by
  `render()`) is never touched; only the new `apps_json_secret` property — used at the one real
  write site, `appsjson.written(...)` — carries the credentialed form. `ResolvedRef.url` likewise
  always stays the plain manifest URL; the token exists only for the live `ls-remote` subprocess
  call.
- Frappe itself stays explicitly out of scope: it rides the `FRAPPE_PATH` build-arg
  (`BR-BUILD-004`), permanently readable via image history, so there is no safe channel for a
  token to reach it.

---

## 2026-07-27 (later still — the descriptor is now actually group-writable, and `write()` converges mode)

Brian's first fully successful `cairn-provision` run surfaced a last, quieter bug: `/etc/cairn`
itself had the correct shared group and setgid bit (`drwxrwsr-x root cairn-admins`), but
`environment.toml` inside it came out `rw-r--r--` — group-**readable**, not writable, defeating
the entire point of `BR-DEPLOY-022` sharing the directory in the first place. Setgid only
propagates *group ownership* to a new file, never its permission bits — those still come from
whatever umask the writing process (root, here) happens to have.

- **`stage_descriptor` now writes `environment.toml` at the new `SHARED_FILE_MODE` (`0o664`)**
  instead of `write()`'s general-purpose default (`0o644`).
- **`Runner.write()` now converges mode as well as content.** Previously, once a file's content
  matched, it was reported "already correct" forever — including a mode that had drifted, which
  is exactly what left Brian's existing `environment.toml` stuck at `0o644` even though nothing
  about its content was ever wrong. Re-running now corrects a drifted mode in place (no backup
  needed — same content, only the mode changes), and a `--dry-run` reports what it would fix
  rather than calling a wrong mode "already correct."
- Revised `BR-DEPLOY-021` rule 1 and `BR-DEPLOY-022` to state both explicitly.

---

## 2026-07-27 (later still — site names come from the filesystem, not from `list-apps`' formatting)

A real target Brian was bringing up hit a false `is_multi_site` STOP on a perfectly ordinary
single-site host. Diagnosis: `_parse_list_apps` inferred site names from `bench --site all
list-apps`'s formatting — an unindented line meant a site, an indented one an app. Measured on
this host's Frappe 16.26.1, a single site produces **no header line at all**, just a flat,
unindented two-line app list (`frappe`, `erpnext`). Both lines read as "sites," zero apps were
found, and cairn refused to adopt a host that in fact serves exactly one site
(`erp.lsnav.app`, confirmed via `ls sites/`).

- **Site discovery no longer depends on `list-apps` at all.** `_survey_sites_and_apps` now reads
  `sites/*/site_config.json` directly — the same test bench itself uses to recognize a site — and
  treats that as authoritative. A side benefit: sites are now known even when `bench` itself can't
  answer (a dead backend), which previously lost the site along with the apps.
- **`_parse_list_apps` replaced with `_parse_apps(output, sites)`**, which filters out any line
  matching an already-known site name and treats everything else as an app — correct whether or
  not a given bench version prints the (now redundant) header line, with no indentation-sniffing
  at all.
- Revised `BR-CLI-020` to require filesystem-derived site names.

---

## 2026-07-27 (later still — `cairn adopt` recognizes cairn's own registry by label, not by name)

Continuing the same discussion: reordering the stages (below) fixes the common, first-run case,
but not a standalone `--only descriptor` re-run, or any run where the registry happens to already
be up — the exact recovery path Brian was pointed at earlier in this session. Brian asked whether
cairn could instead positively identify its own registry project and ignore it outright, rather
than depend on ordering at all. It can: Docker labels are attached to the actual containers, not
inferred from a name — unlike `com.docker.compose.project`, which every compose-managed stack
gets alike and so cannot distinguish cairn's own infrastructure from an operator's site.

- **Added `CAIRN_MANAGED_LABEL`** (`adopt.py`, `"com.datahenge.cairn.managed"`). `registry_compose()`
  now writes it onto the registry service; `provision.py` imports the constant from `adopt` rather
  than duplicating the literal, so the write side and the read side cannot drift apart.
- **`cairn adopt` excludes labeled projects from auto-detection only.** `_survey_project` now asks
  `docker ps --filter label=…` for the compose projects any cairn-managed container belongs to,
  and drops them before picking a single running project — but only when no `--project` was given;
  an operator naming a cairn-managed project explicitly is still honored as-is. If cairn's own
  infrastructure turns out to be the *only* thing running, that is now reported honestly as "no
  compose project is running" rather than silently adopting the registry as though it were a site.
- Revised `BR-CLI-020` to state the exclusion rule and that it binds only to guessing, never to an
  explicit `--project`.

---

## 2026-07-27 (later still — `descriptor` moves ahead of `registry` on a bootstrap box)

The `--project` requirement Brian hit on a fresh `--role both` install turned out to be
self-inflicted rather than inherent: `registry` ran before `descriptor` in `BOTH_STAGES`, so by
the time `cairn adopt` ran, its own `cairn-registry` compose project was already up alongside the
site — two candidates where there should only ever have been one. `descriptor` never actually
depends on the registry existing; nothing forced that order except how the list was written.

- **Reordered `BOTH_STAGES`** to `... backup, descriptor, registry, timers`. On the common
  bootstrap case, `cairn adopt` now runs while only the site's own project is up, so `--project`
  goes back to being needed only when a host is genuinely ambiguous — not on every install.
- Considered and rejected two alternatives: teaching `_pick_project` to ignore a project literally
  named `cairn-registry` (a silent, name-based assumption `adopt.py`'s design deliberately avoids
  — `_pick_project` refuses to guess rather than special-case), and recording the name in
  `builder.toml` (collides with that file's existing `registry` key — the push-destination host —
  and crosses the builder/target read boundary `ADR-041` draws around that file; `cairn adopt` is
  target-side). Fixing the ordering needed neither: the name was never actually unknown, since
  `REGISTRY_DIR` is cairn's own constant, so there was nothing to look up in the first place.

---

## 2026-07-27 (later still — a renewed registry certificate now recreates the container)

Brian hit this on a real re-run: after `--project` fixed the earlier `descriptor` ambiguity, a
second `cairn-provision --force` regenerated the registry's TLS certificate, re-trusted it
system-wide, then failed at the TLS verification step with "did not answer over TLS."

Cause: `docker compose up -d` recreates a container only when its *declared* config (image, env,
volumes list) changes — a bind-mounted file changing content underneath an already-running
container is invisible to it. The registry process had the *old* cert loaded in memory; the host
now trusted only the *new* one. Files converged, running state did not — a real violation of rule
1's idempotence guarantee, not a one-off environment quirk.

- **Revised `BR-DEPLOY-021` rule 1** to state the general case: regenerating identity material a
  running container already loaded MUST recreate that container.
- **Fixed `stage_registry`.** `docker compose up -d` now gets `--force-recreate` whenever this run
  (re)generated the certificate — first install or `--force`, either one — and is left alone
  otherwise, so an unrelated re-run doesn't churn a container that's already correct.

---

## 2026-07-27 (later — the free-disk gate now measures where Docker actually lives)

Brian caught a second, sharper problem while asking about the disk-free floor: on his target
host, Docker's data (images, volumes) lives on a separate mount from `/`, and `_check_disk()`
was hardcoded to check `/` — so the gate could pass on a full data volume, or fail on a roomy
root, either way measuring the wrong filesystem.

- **Revised `BR-DEPLOY-021` rule 5.** The free-disk check MUST now measure the filesystem the
  engine reports as its actual data directory (`docker info --format '{{.DockerRootDir}}'`), not
  assume `/`. Falls back to `/` only when the engine can't be asked (not installed, or not
  reachable yet — this runs before the earlier checks are known to have passed). The reported
  detail names the path checked, so a mismatch would be visible rather than silently wrong, per
  `BR-CLI-011`.

---

## 2026-07-27 (an explicit override for the free-disk gate)

Brian asked whether `cairn-provision`'s 30 GB free-disk floor could be bypassed with `--force`.
It could not — `--force` only governs overwriting existing files (rule 3), and the preflight gate
(rule 5) had no override at all: any failed check, disk included, stopped the run unconditionally.

- **Revised `BR-DEPLOY-021` rule 5.** The free-disk check specifically MAY now be bypassed with a
  new, explicit `--skip-disk-free` flag — for an operator who has already judged the risk of
  running short mid-build or mid-migration. No other prerequisite (root, engine, plugins, memory)
  gets this treatment; running low on memory during an asset build is the kind of failure that is
  hard to diagnose after the fact, so it stays a hard stop. A bypass is still reported, as a
  warning in the closing summary, so it is never silent.

---

## 2026-07-26 (still later — no directory search, no home directories, no local-override file; `cairn-admins`)

Continuing the same discussion, prompted by two more things Brian raised: a future
containerized cairn where a working directory means nothing, and the sharper present-tense
problem — a real multi-user VPS where separate logins (his example: Brian, Sara, Jim) share one
deployment and per-user config silently diverges between them.

- **Added `ADR-042`.** Manifest discovery drops the upward directory walk entirely
  (superseding `ADR-029`'s walk-up mechanism): `--manifest <path>` or `$CAIRN_MANIFEST`, nothing
  else, no fallback default path. Confirmed explicitly with Brian that this reverses
  `BR-CFG-012`'s former "the common case MUST require no flags" clause, rather than walking it
  back quietly. `builder.toml` moves to `/etc/cairn/builder.toml` — no `$XDG_CONFIG_HOME`, no
  home directory, matching `/etc/cairn/environment.toml`'s existing pattern; who may write it is
  left to ordinary filesystem permissions, which cairn assumes nothing about.
  `cairn.local.toml` is removed outright, not relocated — its one job (a personal, no-root,
  per-checkout override) is fully absorbed by a new `CAIRN_*` environment-variable layer
  (`CAIRN_ENGINE`, `CAIRN_REGISTRY`, `CAIRN_NAMESPACE`, `CAIRN_IMAGE_BASE`,
  `CAIRN_TRANSCRIPT_DIR`) sitting at the same top precedence the file used to occupy.
- **Revised `BR-CFG-008`/`012`/`015` (new)** and `BR-CLI-014`/`007` to match: no filesystem
  search of any kind, the three-layer build-config precedence restated with the env-var layer,
  and a new requirement (`BR-CFG-015`) that `/etc/cairn` stays a single host-wide directory
  whose ownership cairn never assumes.
- **Added `ADR-043` and `BR-DEPLOY-022`.** `cairn-provision` now creates a `cairn-admins` group
  (name configurable, `--admin-group`) by default on every role, and shares `/etc/cairn` with
  it — group-owned, **mode 2775** (`rwxrws r-x`, setgid). Brian's own suggestion was `chmod
  g+rw`; the execute bit and setgid were added while implementing it, not a reinterpretation —
  a directory needs its execute bit to be enterable at all, and setgid is what keeps files
  *later* created inside (by a re-run, or by root writing the descriptor) from reverting to the
  creating process's own primary group. `--no-admin-group` skips the stage entirely. Runs before
  `registry`/`descriptor` so the setgid bit predates every file those stages write.
  `cairn doctor` gains a **read-only** check (`check_shared_config_dir`) reporting the
  directory's group, setgid bit, writability, and the invoking user's membership — never
  mutating, matching `ADR-040`'s standing invariant that only `cairn-provision`, not `cairn`
  itself, changes host state.
- **Code:** `src/cairn/config.py` (`find_manifest`/`find_manifest_or_none` drop the directory
  walk and read `$CAIRN_MANIFEST`; `load_build_config` drops the `cairn.local.toml` layer and
  reads the `CAIRN_*` overrides; `BUILDER_CONFIG_PATH` moves to `/etc/cairn/builder.toml`);
  `src/cairn/cli.py` and `src/cairn/push.py` (error messages and `--manifest` help text
  updated; `--manifest` added to `images`/`prune` for consistency now that no command has an
  implicit fallback); `src/cairn/provision.py` (new `admin-group` stage, `--admin-group`/
  `--no-admin-group` flags); `src/cairn/doctor.py` (new `check_shared_config_dir`, `--manifest`
  threaded through `doctor`).
- **Explicitly out of scope:** `src/cairn/project.py`'s directory walk for cairn's own
  vendoring project root is unaffected — finding cairn's own checkout while developing cairn
  is a different question from which deployment a command targets, and cwd still legitimately
  answers it.

## 2026-07-26 (later — the machine build-config file is renamed to `builder.toml`)

Brian pushed back on the previous entry's naming while reviewing it: `config.toml` and the
manifest `cairn.toml` are one word apart, and nothing in either name tells a reader which is
which.

- **Added `ADR-041`.** Renamed `~/.config/cairn/config.toml` → `~/.config/cairn/builder.toml`
  — named for the **Builder** role that reads it, not the generic word "config" that could be
  either file. `BR-CFG-008`/`012` and `BR-CLI-014` amended to the new name; the code constant
  `USER_CONFIG_PATH` renamed to `BUILDER_CONFIG_PATH` (`src/cairn/config.py`). No key, no
  precedence rule, and no access boundary changed — filename only.
- **Verified the access boundary the rename now advertises.** Grepped every call site of
  `load_build_config()`: `build`, `push`, `images`, `prune`, `new-tag`/`retag`/`retire`, and
  `doctor` — every builder-side command, plus `doctor` (which reports on either role) — and
  confirmed no target-side command (`reconcile`, `adopt`, `systemd-units`) reads it. This was
  already true before the rename; the rename just makes the name match the fact.
- **Answered three override questions Brian asked, and documented them in
  `CONFIGURATION.md`:** `builder.toml` cannot be shadowed by a same-named file in the working
  directory (that slot is `cairn.local.toml`, a differently-named file beside the manifest —
  not a bare cwd lookup), cannot be overridden by an environment variable (none is read for
  any of its five keys), and cannot be overridden by a CLI flag except `--transcript <path>`
  on `cairn build`, which replaces the transcript destination outright rather than overriding
  the `transcript_dir` setting.

## 2026-07-26 — split `CONFIGURATION.md` out of README; documented config.toml creation

Prompted by Brian starting a real client install and finding two README gaps: the
Configuration section had grown into full reference material (manifest schema, the
three-layer build-config precedence, the target descriptor), and nothing said how
`~/.config/cairn/config.toml` comes into existence or what it may contain.

- **Added `CONFIGURATION.md`** as the full configuration reference, mirroring the
  existing `ABOUT_REGISTRIES.md`/`ABOUT_GHCR.md` pattern (README stays a short pointer,
  the topic gets its own doc). Covers the manifest schema, both build-config layers
  (`~/.config/cairn/config.toml`, `cairn.local.toml`), full precedence, and the target's
  `/etc/cairn/environment.toml`.
- **Clarified, as a documentation fix, not a behavior change:** both `cairn.toml` and
  `~/.config/cairn/config.toml` are hand-authored — there is no `cairn init` or
  scaffolding command for either, confirmed against `src/cairn/config.py`. Decided (with
  Brian) that this stays manual by design rather than growing a new `BR-CLI` scaffold
  command; if that changes later it needs its own requirements pass, not a doc-only fix.
- **Documented `~/.config/cairn/config.toml`'s actual shape** — flat keys with no
  `[cairn]` table wrapper, unlike the manifest — and every recognized key
  (`BUILD_CONFIG_KEYS` in `src/cairn/config.py`) with its meaning. This existed in code
  but was never written down for a user.
- Slimmed README's `## Configuration` to a minimal quickstart example plus a link,
  keeping only the registry-ownership discussion (`ABOUT_REGISTRIES.md`/
  `ABOUT_GHCR.md`) inline since that's a judgment call, not a reference.

## 2026-07-25 (later — the installer moves into the package as `cairn-provision`)

Follows directly from the PyPI-install fix earlier the same day: once `cairn` itself is fully
functional from a bare `pip install`, the installer's original reason for living outside the
package (it ran before cairn's virtualenv existed) no longer holds.

- **`ADR-040` amended.** `install/bootstrap.py` moved to `src/cairn/provision.py`, with its own
  console-script entry point, `cairn-provision` (`pyproject.toml`'s `[project.scripts]`,
  alongside `cairn` and `datahenge-cairn`). It is never installed apart from `cairn` — same
  distribution, same install. It stays out of the `cairn` command tree regardless: `ADR-035`
  (cairn never installs systemd units) and `ADR-022` (cairn never writes to the data plane) are
  about what `cairn` itself may do, not about packaging, and those hold unchanged.
- **`stage_cairn` removed.** It used to create a fresh virtualenv and `pip install` cairn into
  it from a checkout — meaningless now that `cairn-provision` running at all means cairn is
  already installed. `--source` (the checkout directory) is gone with it, replaced by
  `--workdir` (the deployment directory: where `cairn.toml` lives and the build timer runs
  from) — a genuinely different concept that the old design had conflated with "where cairn
  itself lives."
- **Locating `cairn` from `cairn-provision`.** Resolved as a sibling in the same install
  (`Path(sys.argv[0]).parent / "cairn"`), falling back to a `PATH` lookup — not a checkout path,
  which no longer exists as a concept here.
- **Systemd units, TLS certs, and the pre-install backup are still written directly**, not
  printed for the operator to type — considered and reaffirmed, not a default. Direct-write
  guarded by `--dry-run` and idempotency turned out to be the more common pattern among
  comparable tools (`certbot`, `mkcert`, `k3s`'s installer) than print-and-transcribe, and cairn's
  installer already had that safety net for every other stage.
- **Recommended install changed for anything a client depends on**: `sudo pipx install --global
  datahenge-cairn` rather than a personal `pip install`. The concrete risk: a consultant's own
  Linux account is not something a client's production systemd timers should depend on
  outliving. `--global` installs to a shared system location, not a personal home directory.
- **`BR-DEPLOY-021` reworded** — "shipped alongside the CLI" now means the same package's
  second entry point, not a separate file in the repo.

---

## 2026-07-25 (the PyPI-install blockers close — vendoring moves inside the package)

Resolving `ADR-018`'s three recorded reasons `pip install datahenge-cairn && cairn build`
could not work, found while auditing the project for its first real PyPI publish.

- **`ADR-007` amended, `ADR-018` and `ADR-029` resolved.** The vendored `frappe_docker` tree
  moved from the repo root to `src/cairn/vendored/frappe_docker` — *inside* the `cairn`
  package — on Brian's framing that vendoring is a fetch mechanism, not an ongoing
  relationship: once fetched, the tree is an ordinary part of cairn's own source, and
  `ventwig` has no further business with it. `packages = ["src/cairn"]` now ships it in the
  wheel with no special packaging step. Every vendor-tree lookup resolves package-relatively
  from cairn's own installed location, never by searching the filesystem for a project root.
- **`BR-VEND-003`/`BR-VEND-005` amended.** `cairn vendor sync` now writes a companion
  `src/cairn/vendored/frappe_docker.pin.toml` (ref, commit, tree hash, synced-at) from
  ventwig's own `.ventwig.lock`. `vendor.assert_clean()` verifies against that file instead
  of shelling out to the `ventwig` CLI — it recomputes the same git tree-hash ventwig uses
  (a scratch `git init`/`add -A`/`write-tree`), needing only the `git` binary cairn already
  requires unconditionally. `ventwig` is now touched by nothing except `cairn vendor
  sync`/`status`, run deliberately from a checkout.
- **`BR-BUILD-011` / `ADR-030` amended.** The `com.datahenge.cairn.frappe-docker.*`
  provenance labels now read from the pin file instead of `.ventwig.lock` directly.
- **`cli.py` simplified.** `find_project_root()` is needed only by `vendor status`/`vendor
  sync` now — every other command (`build`, `push`, `images`, `prune`, `new-tag`, `retag`,
  `retire`, `doctor`) no longer threads a project root through at all. This incidentally
  fixes `cairn doctor` raising a raw `ProjectRootNotFoundError` on a target-only install —
  doctor no longer needs a project to run.
- **Verified, not assumed.** A wheel built from the new layout, installed into a clean venv
  with no checkout and no `[dev]` extra, ran `cairn doctor` and `cairn build --dry-run`
  through to build-engine invocation with no project-root or vendoring error. The builder
  role no longer strictly requires a checkout — a consequence beyond what was asked, recorded
  in `ADR-018` rather than acted on unilaterally in the installer (`ADR-040`), since that
  installer still provisions from a checkout by default for other reasons (dev tooling).
- **Version.** `pyproject.toml` moved off the `0.0.0` placeholder to `0.1.0`, a second
  independent blocker to a real publish (PyPI versions cannot be reused).

---

## 2026-07-25 (night, provisioning — a tool instead of a runbook)

Standing up a builder VPS is a dozen steps. Brian rejected documenting them as a runbook: a
procedure pasted command-by-command is not idempotent, not testable, and does not get cheaper for
builder VPS #2 and #3 — which, for a multi-client practice, is the case that matters. *"If it's
worth doing for safety/checks, it's worth building it as a reusable installer."*

- **`ADR-040` — provisioning is an installer beside the CLI, never a verb inside it.** The obvious
  home was `cairn bootstrap`, and it would have breached two decisions made days earlier:
  `ADR-035` (cairn emits systemd units and never installs them) and `ADR-022`/`BR-DATA-006` (cairn
  writes nothing to a data-plane volume — a pre-install `bench backup` writes into the sites
  volume). A separate program, run with explicit privilege by the operator, is the honest
  expression of the same boundary rather than a loophole around it. Recorded as `BR-DEPLOY-021`
  with a seven-point contract: idempotent, truthful `--dry-run`, never silently overwrites, no
  secrets, gates before acting, verifies its own claims, and is **never the only path**.
- **The invariant this completes, now true across the whole CLI:** *cairn prints host
  configuration; the operator installs it.* `systemd-units` prints units; `adopt` prints a
  descriptor; neither writes.
- **`BR-CLI-020` — `cairn adopt`.** Reads a running frappe_docker deployment and prints a
  descriptor for it. This is the piece that earns its keep: three of the sharpest risks in adopting
  an existing stack existed **only** because a human transcribes facts off a running box into a
  TOML file. It reads the compose project and its file set, the sites and their installed apps, and
  the image actually running — and **reports gaps rather than filling them**, because a plausible
  default inserted here surfaces weeks later as a stack composed from the wrong files. What it
  prints is round-tripped through the descriptor reader, so it cannot emit something `reconcile`
  would reject.
- **Two stop conditions it exists to catch.** It cross-checks the manifest's *ordered* app list
  against what the site has installed — a mismatch means `bench migrate` meets code the site does
  not expect — and it detects a **multi-site** host, which `BR-DEPLOY-014` does not support and
  which `reconcile` would silently narrow. Both are stops, not warnings.
- **`install/bootstrap.py`** — stdlib-only, sudo-run, seven `--only`-able stages. It cannot import
  cairn because it runs *before* the virtualenv exists; that self-containment is forced, not
  chosen. Python rather than shell because this runs as root on client infrastructure and therefore
  has to be testable.

**A role error Brian caught mid-implementation, and it was broader than he flagged.** He pointed
out that `bench backup` cannot run on a builder — a build machine has no site. True, and the same
reasoning condemned two more stages: **`recon`** (nothing to survey) and **`descriptor`** (which
describes a *running* deployment), while **`registry`** is builder-only since a target pulls from
the builder's. The stage lists are now role-derived — builder: preflight, cairn, registry, timers;
target: preflight, recon, backup, cairn, descriptor, timers — with a `--role both` for the
bootstrap case where one box does each. Every stage also refuses the wrong role *itself*, since
`--only` can invoke one directly. The original single list happened to work only because today's
box is both.

**Verified the same way as the rest.** 27 mutations applied one at a time — a builder allowed to
back up, a target allowed to host a registry, the dry run writing files, an existing file
overwritten without `--force`, preflight stopping at the first failure, the disk gate dropped,
memory read as `MemFree` instead of `MemAvailable`, the certificate key made world-readable, the
registry bound to `0.0.0.0`, an empty backup accepted as verified, timers started rather than
merely enabled, multi-site detection removed, frappe counted as a manifest app, app order stopped
mattering. **Every one was caught by a named test.** One initial mutation was invalid — it broke
the syntax rather than the behaviour, which catches trivially and proves nothing — so it was
rewritten as a real reordering and re-run.

568 tests, ruff clean.

## 2026-07-25 (night, image ownership — a requirement that should have existed first)

Brian raised a problem with the registry design that **should have been addressed far earlier**,
and he was right about that too. Every registry decision to date — `ADR-009` registry-agnosticism,
`BR-CFG-011`'s image base, `ADR-036`'s client — was made without ever stating *whose account the
image lands in*. The documented example throughout was `ghcr.io/datahenge/…`, and `ABOUT_GHCR.md`
raised the ownership problem only as the fourth bullet of a subsection. That is a
professional-liability constraint on the whole deploy architecture, not a caveat.

His statement of it: he builds **clients'** private customizations and apps, and must never be the
sole owner of a client's image — if the relationship ends badly the client cannot deploy or roll
back software they own, "the equivalent of holding a client's business hostage." He also will not
maintain one GitHub account per client: browsers cache logins, and "which account am I in right
now" is costly and genuinely dangerous.

- **`ADR-038` — the image belongs in the account that owns the source.** Recorded as
  `BR-CFG-013`: cairn MUST support publishing to a namespace the operator does not own, MUST NOT
  assume the operator's own, and MUST NOT infer one from anything. The operator's own namespace was
  never wrong — it was wrong as a *default*.
- **One of the three objections did not survive the mechanism.** A GHCR namespace can be an
  organization the operator does not own: the client adds the operator's *single* account, the
  package belongs to their org, billing accrues to them, and revoking membership leaves them whole.
  One account, N clients. The objection was to one-account-per-client, which was never the only
  pattern — only the only one documented.
- **The cost objection stands and is decisive.** GitHub Packages prices multi-gigabyte artifacts
  badly regardless of who pays, and Brian's point about `frappe_docker` having no per-app layer
  seam compounds it exactly as it compounds build time (`ADR-021`, entry 1): every build is a fresh
  full-size layer, so layer sharing saves almost nothing and each retained rollback version costs
  close to a whole image. GHCR is therefore documented as **one option, not the default**.
- **A fourth objection, raised in follow-up, turned out to be the most useful.** Brian asked
  whether write access to a client's registry is *boundless* — "not because I would be malicious,
  but because I can make mistakes. I'm a few typos away from destroying their non-ERPNext images."
  Factually GHCR is better than feared: `write:packages` is a ceiling on what the *token* may
  attempt, not a grant; packages carry per-package Read/Write/Admin roles; a package linked to a
  repository **inherits that repository's permissions**, so the per-repo model he prefers is
  available for images; and a mistyped push either creates a new package or is denied — it cannot
  overwrite one he was never granted. But the principle was unstated, so it is now `BR-CFG-013`'s
  second half: **the operator's credential MUST be scopeable to the engagement's images and nothing
  else.** Framed as *liability containment for the operator* rather than as a security control — a
  credential that can write one repository cannot cause a catastrophe — and as a registry
  **selection criterion**, which is why per-repository IAM scoping ranks above account-wide
  credentials.
- **`ADR-039` — registry coordinates move into the manifest.** `BR-CFG-008` had put them in
  machine-local config and stated the manifest must stay free of registry settings. Under
  `ADR-038` that is a defect: the fact that Acme's images belong in `ghcr.io/acme-corp` would live
  only on Brian's laptop — undocumented, lost with the laptop, invisible to the client who is meant
  to be able to take over. Now `[cairn.registry]` with a required `host` and optional `namespace`,
  committed. The original reasoning inverted: it assumed one manifest might target many registries,
  but with client-owned registries one manifest means one owner means one registry. Recorded as
  `BR-CFG-014`; `BR-CFG-008` and `BR-CFG-012` amended.
- **Precedence, with the load-bearing half named:** machine config → the manifest's registry →
  `cairn.local.toml`. The manifest overriding machine-wide config is what prevents a machine-wide
  `namespace = "datahenge"` from silently publishing a client's image into the operator's account.
  Keeping the local file *above* the manifest preserves the escape hatch: publish elsewhere for a
  test without editing, and committing, a client's file. `engine`, `image_base`, and
  `transcript_dir` stay machine-local, and `[cairn.registry]` rejects anything but its two keys so
  the boundary cannot erode.

**Docs.** New `ABOUT_REGISTRIES.md` leads with the three rules (ownership, least privilege,
credentials are never cairn's), compares client-owned cloud registries / client-owned GitHub org /
a registry on the client's VPS / the operator's own namespace, and ends with **what to ask a client
for** in plain language. `ABOUT_GHCR.md` is demoted to a detail reference, gains an accurate
account of how narrow package access can be, and gains a terminology section — Brian pointed out
that "package" is GitHub's generic noun and undefined in Docker terms, so the mapping is now
explicit: package = repository, package version = image, and that is *why* deleting a version takes
every tag on it.

**A regression caught by the existing suite while implementing this:** making the
`cairn.local.toml` layer conditional on the manifest file existing broke the case where a local
config sits beside a manifest that does not exist yet. Only the registry layer needs the manifest;
the local file needs only its directory.

## 2026-07-25 (night, two decisions closed)

Both Brian's, both closing questions that had been deliberately left open.

- **`ADR-037` closed — cairn never installs an app; the clause is struck.** Brian leaned toward
  striking and asked for a recommendation; the recommendation was to strike, on a structural
  argument rather than one of convenience. **A convergence loop cannot host a one-shot
  mutation.** `reconcile` is safe because repeating it is a no-op; `install-app` is irreversible
  and must happen exactly once, which would require cairn to remember whether it already had —
  durable state cairn deliberately does not keep. Every candidate transport (an image label, a
  descriptor field, a second registry artifact) was really a proposal for *where to keep that
  state*. Two further reasons, each sufficient alone: it is a second data-plane write beyond the
  permitted `bench migrate` (`ADR-022`), and it breaks rollback — move the pointer back and the
  app's schema remains while the code that understands it is gone. What clinched it is
  consistency: `BR-DEPLOY-007` already makes `bench new-site` the operator's job, and installing
  an app is the same class of act — it changes what the environment *is*, not which version it
  runs. Recorded as `BR-DEPLOY-003a`; `--install-app` removed from `BR-CLI-004`. `reconcile`'s
  behaviour is unchanged: it never installed.
- **`ADR-032`'s deferred half resolved — the legible tag half is a declared `[cairn] series`.**
  It had derived from the Frappe *ref*, making the tag a function of how the ref was spelled: one
  commit reached by a branch and by a tag produced two names for one image, and following
  `BR-BUILD-005`'s own advice to pin to tags renamed every image for no change in content. Now
  declared once. The deciding argument against **reading the true version at the resolved
  commit** — which sounds strictly more correct — is that it cannot be done provider-neutrally:
  `git ls-remote` returns hashes, not file contents, so it needs either a clone on every build or
  a GitHub-specific API call, and cairn assumes a git host no more than it assumes a registry.
  Two safety properties: `series` **never enters the input hash** (a label, not an input, so
  renaming a line cannot orphan existing images or provoke a rebuild), and absent a declared
  series the old derivation still applies. Accepted cost, stated rather than hidden: nothing
  validates the claim — a manifest may say `series = "v16"` while building Frappe 15.

**A test gap worth recording, found by mutation rather than by review.** Two mutations survived
the first pass. One showed that *nothing pinned the actual hash value*: every existing test
compared one computed hash against another, so a change to **what goes into** the recipe would
have passed the entire suite while silently renaming every image in existence — breaking the
input-hash short-circuit, making every deterministic tag in the registry unreachable by name, and
addressing rollback targets by names cairn would never generate again. `test_the_hash_recipe_is_pinned_across_cairn_versions`
now pins both digests as literals. The second showed the manifest→tag wiring for `series` was
untested — a setting that validated, documented itself, and could have done nothing. Both closed;
the re-run catches all three.

## 2026-07-25 (night, naming and GHCR)

- **`ABOUT_GHCR.md` added at project root**, linked from `README.md`. Brian is new to GHCR and
  asked what he is logging into, how it relates to his GitHub account and repos, and who owns
  the images after deployment. Written for that reader, and deliberately carrying **no `BR`/`ADR`
  identifiers** — it is user-facing documentation, where the identifier rule binds.
- **`README.md` status corrected.** It still said "Early design. No code yet", which stopped
  being true some time ago. Now distinguishes what has run against real infrastructure from
  what is only tested.
- **`ADR-018`'s naming re-verified against reality, and one half amended.** The PyPI
  distribution `datahenge-cairn` is confirmed **available**, and `cairn` is confirmed **taken**
  (by an unrelated project, `cairn` 0.2.3) — so the decision's premise holds and no change is
  needed there. The *repository* half is amended: `ADR-018` proposed `datahenge-cairn` for the
  repo too, but the prefix existed solely to dodge a collision in PyPI's flat global namespace,
  and GitHub namespaces by owner. `Datahenge/cofferdam` and `Datahenge/btu` both establish the
  plain-name convention, and `Datahenge/datahenge-cairn` stutters. **Repo: `Datahenge/cairn`.**
- **`ADR-021`'s fork-pressure register gains a second, independent cost for entry 1.** The
  atomic `bench init` layer was argued entirely in build minutes; documenting GHCR's billing
  surfaced the money half. Because the step yields one multi-gigabyte layer, layer sharing buys
  almost nothing, so every custom-app commit costs close to a full image in private-registry
  storage *and* in outbound transfer to every converging target. One upstream constraint, two
  independent consequences — recorded as evidence, not as a second argument.
- **A gap named rather than filled:** cairn stamps no `org.opencontainers.image.source` label,
  which is what GHCR reads to link a package to a repository automatically. Adding it requires
  deciding *which* repository an image points at — the deployment's or the tool's — which is a
  design question. Documented in `ABOUT_GHCR.md` as a manual step until decided.

## 2026-07-25 (night, deploy path)

Three gaps blocked the deploy verbs: `BR-DEPLOY-009` and `BR-DEPLOY-010` each settled what a
thing *is* without saying where it lives, and `BR-DEPLOY-001` required a systemd timer without
saying who writes it. All three are now decided, and Brian chose each.

- **`ADR-033` — the declared environment list is `[cairn.environments]` in `cairn.toml`**
  (environment name → registry tag). Chosen over a second file because the list is portable,
  shared, and belongs under review beside what it points at — and the manifest is already
  discovered with no flags (`BR-CFG-012`). It does **not** contradict `BR-BUILD-001`: that
  calls the *image* environment-agnostic, not the file, and no environment name reaches a
  build. Build config was rejected outright — a source of truth gating a production retag
  cannot live somewhere machine-local and uncommitted (`BR-CFG-008`). Recorded as
  `BR-DEPLOY-009a`; `BR-BUILD-002` now admits the optional fifth key.
- **`ADR-034` — the target descriptor is TOML at `/etc/cairn/environment.toml`, one
  environment per host.** Fixed path, because `reconcile` runs unattended: a flag is
  something nobody is present to pass, and a search path can silently find the wrong file.
  The file's presence doubles as the role signal `ADR-028` detects a target from. One
  environment per host follows `BR-DEPLOY-014` (one site per environment) and `ADR-002`
  (single-host VPS), and keeps `reconcile` argument-free with a single global lock; if
  multiple environments per host are ever needed, `/etc/cairn/<env>.toml` extends it and
  `reconcile` gains an argument. It is **host state, not deployment state** — never committed.
  Recorded as `BR-DEPLOY-010a`.
- **`ADR-035` — cairn emits systemd units and never installs them.** Writing to
  `/etc/systemd/system` and reloading the daemon needs root and changes the host outside
  cairn's stated boundary; `BR-DEPLOY-008` makes cairn a thin orchestrator *over* systemd, not
  an adopter of the host's init configuration. Ignoring the units was also rejected: the
  cadence, the single-flight expectation, and journald owning the log are cairn's knowledge,
  and a printed unit is documentation that cannot drift from the code. Recorded as
  `BR-CLI-019`.

**Field context that shaped the sequencing:** the VPS already runs a live site, so `cairn`
takes over the image pointer only — `BR-DEPLOY-007` keeps `bench new-site` the operator's job,
and none of this work creates sites, volumes, or databases.

Two further decisions the implementation forced:

- **`ADR-036` — cairn speaks the registry API directly** rather than shelling out, and this was
  decided by evidence rather than preference. `BR-DEPLOY-005` requires reading an image's
  provenance labels *remotely, without pulling*; the control machine has `podman` 5.4.2 and
  `buildah` 1.39.3 and **no podman or buildah subcommand can do that**. `docker buildx
  imagetools` and `skopeo` can, and neither is installed — so delegating would mean a new hard
  binary dependency to perform one manifest fetch. cairn now owns a small stdlib client: three
  GETs and a PUT, no third-party HTTP library. Credentials stay the engine's (`BR-CFG-010`):
  cairn reads the file `podman login` wrote, uses it for one command, and persists nothing;
  anonymous is tried first, so a public repository never opens it. **Flagged for Brian's
  review** — he chose the other three decisions, not this one.
- **`ADR-037` (open) — how an `install-app` opt-in reaches a target.** `BR-DEPLOY-003` permits
  it behind an opt-in directive and `BR-CLI-004` expresses that opt-in control-side, but the two
  halves of an environment are joined *only by the tag name*, which has no room for a payload.
  So `cairn reconcile` does not run `install-app` at all, which is the correct reading of
  `ADR-023`: absent a decided transport, installing would be the auto-install that decision
  forbids. Four options are recorded, including striking the clause — a genuine possibility,
  since adding an app to a live site is a rare and deliberate act. Trigger: the first time it is
  actually needed, note what was needed, then decide.

**On testing this before it touches production.** The deploy path is covered by 162 new tests,
and — as with the CLI work — the tests were checked for the failure they claim to detect. 22
mutations were applied to `registry.py`, `environments.py`, `reconcile.py`, `descriptor.py`, and
`cli.py` one at a time: a retag that re-serializes the manifest (which would change its digest),
a retag writing to the source tag, a pull-only token, credentials read before trying anonymous,
`new-tag` accepting a live pointer, production's confirmation skipped, a stopped stack counted as
converged, `migrate` skipped, compose overrides layered in reverse, a shared rather than
exclusive lock. **Every one was caught by a named test.** One real defect was found this way and
not in production: a root-owned `~/.docker/config.json` made `Path.is_file()` raise
`PermissionError`, which would have turned every registry command into a traceback where
anonymous access would have worked.

## 2026-07-25 (night)

- **`cairn prune` verified on the real machine.** Brian confirmed it worked as intended,
  closing the one item in `docs/plans/next-steps.md` §1 that no test could settle — the only
  new code that had never been executed against real images, and cairn's only destructive
  verb. `BR-CLI-018` is now implemented *and* exercised in the field.
- **The CLI layer is now tested.** `tests/test_cli.py` added (45 tests, Typer `CliRunner`),
  closing the one material coverage hole a suite review found the same day: `cli.py` was
  simultaneously the largest module and the only surface a user touches, and it had never
  been executed under test. `_run_in_project` — which *is* `BR-CLI-012`'s exit-code contract
  (0 success, 2 for an expected failure, 130 for interrupt, the action's own code otherwise)
  — was previously verified only by hand. `cli.py` and `__main__.py` go 0% → 100%; the
  package total is 94%.
- **The tests were checked for the failure they claim to detect.** 14 mutations were applied
  to `cli.py` one at a time — wrong exit codes, ignored flags, a silenced warning, a skipped
  confirmation, the registry check moved after the build — and every one was caught by a
  named test. This is the same discipline as
  `test_the_guard_actually_detects_a_violation` in `test_conventions.py`: a test that cannot
  fail is not protection. Notably, `transcript.wanted` and `prune.select` were already
  thoroughly tested at the module level while nothing verified the CLI passed them the right
  arguments — tested logic behind untested wiring.
- **Two tests repaired, not removed.** `test_build_args_do_not_affect_the_cache_bust` named a
  guarantee its body never exercised (`cache_bust` accepts only a resolution, so build args
  *cannot* be passed to it); it now pins the property actually worth holding — build args
  change the input hash but must not change the cache bust. `test_sizes_are_not_binary_units`
  was subsumed by the assertion above it and is folded into it, keeping the original bug in
  the docstring.
- **`pytest-cov` added to the `dev` extra**, and `.coverage` gitignored. No
  `--cov-fail-under` floor is set yet — that is a separate decision, since putting `--cov` in
  `addopts` makes every test run depend on the plugin being installed.

## 2026-07-25 (evening, later)

- **`ADR-021` gains a fork-pressure register.** Brian observed that each pitfall makes an
  eventual fork of `frappe_docker` feel nearer. The register exists so that judgement rests
  on evidence rather than accumulated feeling: it admits **only** constraints that are
  genuinely upstream's, and explicitly excludes cairn's own work (transcripts, timing,
  tagging, pruning, the short-circuit), none of which a fork would change.
- **Two entries recorded, both Brian's.** (1) *The atomic `bench init` layer* — sharpened
  considerably by his actual workflow: a client engagement pins one Frappe/ERPNext version
  and then iterates on custom apps for weeks, so the unchanged 95% is re-cloned and rebuilt
  on every custom-app commit. That makes the worst-handled case the **dominant** one, not an
  edge. Now the strongest argument on the list. (2) *Commit-level pinning is impossible
  through bench*, which matters more in this ecosystem than most because `version-15` /
  `version-16` move continuously under backporting. Consequence: an image cannot be rebuilt
  from its manifest once the branch has moved, so the stored image is the only durable copy.
- **Countervailing evidence recorded too**, to keep the register honest: the vendored recipe
  was measured working as designed on the same day.
- **Trigger set:** revisit when entry 1 is measured — time a rebuild after a single
  custom-app commit against a first build.
- **`docs/plans/next-steps.md` added** as a session-resumption point.

## 2026-07-25 (evening)

- **`BR-BUILD-015` added — name the build-cache stage.** Brian asked whether cairn should
  label the build cache so an admin running `podman image list` doesn't delete it. The
  mechanism had to change: `podman image list` prints repository, tag, id, age and size —
  **labels are never displayed**, only filterable, so a label helps nobody scanning a
  listing. A **tag** is what shows, and a tag is a pointer: free.
- **Measured before committing** (lessons §12): a `--target builder` pass against a warm
  cache took **0.762s**, every step a cache hit, `COMMIT` landing on the *existing* image
  id with `CREATED` unchanged. No new image, no new disk. It also proved from the engine's
  own cache resolution that the 4.63 GB untagged image **is** the `builder` stage.
- **Two constraints the measurement produced.** The pass is only cheap against a warm
  cache, so it runs solely after a build that *actually ran* — never after a
  `BR-BUILD-014` short-circuit, where the stage may have been pruned since and the same
  command would be a full `bench init`. And podman prefixes unqualified names with
  `localhost/`.
- **`ADR-027` amended — the engines are equivalent in *output*, not in *residue*.** Docker
  keeps build cache in a separate store rather than as images, so `--target` there would
  **materialize** several GB that otherwise never exist. `BR-BUILD-015` is podman-only as a
  correctness constraint, not a preference. General rule recorded: behaviour touching an
  engine's local storage is decided per engine; behaviour touching the image is not.
- **A claim of mine withdrawn before it reached code.** I had argued tagging would also let
  `cairn prune` reclaim *stale* cache stages. It does not: a moving `:builder` tag hands
  itself to each new stage, so superseded ones revert to untagged. Tagging per input hash
  would identify them but pin every 4.63 GB stage forever — worse. The design keeps one
  moving tag: the live cache is protected, stale stages correctly become collectable.

## 2026-07-25 (later still)

- **`BR-CLI-018` strengthened during implementation — never remove a tagged image.** The
  requirement said "keep the newest `<n>` per input hash (default: 1, the tagged one)",
  whose parenthetical merely *assumed* the newest is the tagged one. Writing the code made
  the gap visible: nothing forced it. Now stated as three concentric restrictions — cairn's
  own labels, then untagged only, then beyond keep-N — because a tag is a name something
  else may rely on, and removing a tagged image would require the engine's `--force`, the
  one flag that makes an accident possible. cairn never passes it.
- **Also required: say what is being left alone.** A 4.63 GB image absent from a prune
  report should read as a decision, not an oversight, so the count of non-cairn images is
  always stated along with why they are excluded.
- **Sizes corrected to decimal units** (`cairn images --local`). It reported 2.57 GB where
  `podman image list` reported 2.75 GB for the same image — binary arithmetic under a
  decimal label. A listing meant to be read beside the engine's own must agree with it.

## 2026-07-25 (later)

- **`ADR-032` closed — one image per input hash; prune only what cairn labelled.** Four
  consecutive builds of an unchanged manifest produced four image IDs, five nameless
  multi-gigabyte images, ~14 GB of orphans — and one unchanged primary tag. Diagnosis
  required separating **declared** inputs (`version-16`) from **resolved** inputs (the
  commit), which collapses the confusing cases: same declared/different resolved is a
  branch that moved; different declared/same resolved is a branch and a tag naming one
  commit. Image content is a function of resolved inputs alone — but the mapping is
  one-to-many the other way, since the image config carries a build-time clock.
- **`BR-BUILD-014` added — cairn will not rebuild an input hash it already holds.** An
  existing primary tag proves the inputs are unchanged; rebuilding can only mint a second
  digest, move the tag to it, and orphan the first. `--rebuild` overrides.
- **`BR-BUILD-008`: "immutable primary tag" corrected to "deterministic".** The original
  wording invited exactly the wrong inference and did so successfully. Three tiers of
  identity now stated inline — address (digest), deterministic name (cairn's tag,
  re-pointable), moving pointer (`latest`).
- **`BR-CLI-005` extended with `--local`**; **`BR-CLI-018` added for `cairn prune`.** An
  engine's image listing knows repository, tag, id, age, size — it cannot answer *why an
  image exists*. Everything needed is already stamped by `BR-BUILD-011`.
- **Prune scopes by label, never by danglingness — a cache-safety rule, not tidiness.**
  Brian observed that clearing dangling images made the next build enormously slower: on
  podman an untagged image may be a build-cache **stage**. cairn's labels land only at the
  final commit, so a label-scoped prune cannot reach the cache. Recorded as lessons §12.
  This retracts advice given earlier in the same conversation ("prune dangling, it's safe").
- **Left open deliberately:** whether the tag's `<legible>` half should keep deriving from
  the *declared* Frappe ref. It currently does, so one commit reached by a branch and by a
  tag yields two tag names for one image, and following `BR-BUILD-005`'s own advice to pin
  to tags renames every image for no change in content.

## 2026-07-25

- **`ADR-031` closed — three execution contexts; build transcript in attended CLI only.**
  `ADR-026` forbade custom log files outright, which `BR-DEPLOY-019` restated as an
  absolute. Brian's first real build exposed the cost: minutes of unscrollable engine
  output, lost to any stray `clear`. The initial proposal — "narrow it to the target
  side" — was rejected by Brian as too simplistic, since it ignores unattended **CI**
  builds where the filesystem is again the wrong place. The axis is not *where* but
  **who already owns and retains the record**: journald (daemon), the CI log viewer
  (unattended), nobody (attended). `ADR-026` amended, `BR-DEPLOY-019` scoped to name its
  one exception, new `BR-CLI-016` (transcript) and `BR-CLI-017` (timing), and
  `transcript_dir` added to `BR-CFG-008`.
- **Two findings folded into that decision.** Attended builds force plain engine progress
  — BuildKit's default TTY display redraws lines with ANSI escapes, which is what
  destroyed scrollback and would have made a teed file unreadable. And one `isatty()`
  check on stderr resolves all three contexts correctly, since neither journald nor a CI
  runner allocates a TTY: three contexts, two behaviors, one test.
- **`BR-CLI-016` corrected during implementation — transcript filename.** It first
  specified `<timestamp>--<image>-<primary-tag>.log`, which is unbuildable: the file has
  to be open *before* ref resolution, and resolution is what computes the tag. Named from
  the manifest's `image_name` instead, with the tag written inside the transcript. The
  `last-build.log` symlink means the filename is rarely typed anyway.
- **Timing is terminal + transcript only, never a provenance label** (`BR-CLI-017`).
  Duration is a property of a build *run* — cache state, machine, network — not of the
  image's inputs, which is what `BR-BUILD-013` makes guarantees about.
- **Multi-image staging analysed and parked** (`03-discussion-log.md`). After the first
  real `cairn build`, Brian proposed splitting the build into a sequence of
  content-addressed images so later steps could reuse earlier ones. Reading the vendored
  `images/custom/Containerfile` established two things: the expensive `base` stage is
  *already* cached across builds (`CACHE_BUST` is declared in `builder`, after every
  `base` instruction), and the app install is a **single atomic `RUN`** — Frappe clone,
  every app clone, pip installs and the asset build in one layer with one cache-bust
  knob. There is therefore no seam to split apps on without editing the vendored tree
  (`BR-VEND-004`, `ADR-001`) or forking (`ADR-021`). Four fork-free options recorded;
  the input-hash short-circuit is worth doing regardless. Decision deferred pending
  per-phase build timings — no requirements changed yet.

## 2026-07-24

- **The identifier rule made enforceable, after being violated twice.** Brian asked
  whether the rule was strong enough, having watched `BR` IDs reach user-facing output
  repeatedly. It wasn't — not because the wording was unclear, but because it sat in
  workflow step 6 (*"User documentation"*, a phase not yet begun), never named the
  channels that actually leak (`--help`, errors, warnings, progress), was absent from the
  binding *"For the AI (operating rules)"* section, and **had no enforcement**. Fixed on
  all four axes in `/CLAUDE.md`, the last via `tests/test_conventions.py`, which parses
  every non-docstring string literal in the package and fails on any `BR-`/`ADR-`
  identifier — including a test that plants a violation to prove the guard can fail.
  Recorded as lessons §11: prefer conventions that can fail a test; for a rule stated in
  prose, ask not "is the wording clear?" but "what would notice if I broke it?"
- **`BR-CLI-011` strengthened — "silence cuts both ways".** As written, the requirement
  listed only *destructive* examples (no auto-rollback, no auto-install, no data writes),
  and was implemented as "no silent destructive actions". That reading let `cairn build`
  run vendored-tree checks, three network round-trips, and a container build while
  printing **nothing** — reported by Brian as a build that "finished almost instantly"
  with no output at all. The requirement now also forbids a command *appearing to do
  nothing*, and requires verifying post-conditions instead of trusting an exit code: an
  engine that exits 0 without producing the image must be reported as a failure. A
  requirement ambiguous enough to produce the wrong implementation is a requirement
  defect, so it was fixed rather than only the code.
- **CLI help no longer leaks `BR` identifiers.** `/CLAUDE.md` requires internal docstrings
  to cite `BR` IDs while *external* descriptions omit them; because Typer renders a
  command's docstring as its `--help` text, every command was showing its `BR` ID to
  users. Commands now carry a user-facing `help=` on the decorator, leaving docstrings
  free to stay internal. Caught while reviewing `cairn --help` output, not by a test —
  worth a check before the Phase-6 user docs.
- **`ADR-030` records a rejected alternative: a per-deployment label namespace**
  (`com.microsoft.cairn.*` for a client Microsoft). Brian raised it and spotted the risk;
  the decisive objection is that **cairn reads these labels, not just writes them** — a
  target running `reconcile` holds an environment descriptor, not the build manifest, so
  it cannot know which prefix its own images used. The bootstrap never closes either:
  discovering a configured namespace still requires one fixed key to look it up under.
  Also recorded: a typo produces a perfectly valid label that fails silently, surfacing at
  rollback; and a namespace names *who defines the keys*, not who owns the image. The
  legitimate need underneath — recording whose image it is — belongs in
  `org.opencontainers.image.vendor`/`.title`/`.url`, which cairn could make settable later.
  Blast radius clarified: a wrong namespace does not make an image incompatible; it blinds
  cairn's own introspection, promotion, and rollback.
- **`ADR-030` — provenance label schema settled before the first push.** cairn-specific
  keys use **`com.datahenge.cairn.*`**, alongside standard `org.opencontainers.image.*`
  where one already fits. Reasoning was checked against the primary sources rather than
  convention-by-memory: the OCI image-spec only says keys **SHOULD** use reverse-DNS and
  is silent on both rationale and domain ownership, while **Docker's** documentation
  supplies both ("a domain **they own**"; "Don't use a domain … without the domain
  owner's permission"; the purpose being collision safety for automation). `io.cairn` /
  `dev.cairn` were **rejected as domains owned by others**; bare `cairn.*` was considered
  and rejected for forfeiting the collision protection cairn actually relies on, since it
  keys behavior off these labels. cairn deliberately does **not** set
  `org.opencontainers.image.vendor` — the distributing entity of a client's image is the
  client's to declare. Recorded in lessons §10 that a terse standard's operative guidance
  often lives in a dominant implementer's docs.
- **`BR-BUILD-008` clarified — a pin bump can change the tag with an unchanged manifest.**
  Affirmed by Brian as intended: the input hash covers *effective* build args
  (`BR-BUILD-010`), so a `frappe_docker` bump that moves a Containerfile default changes
  the image's inputs and therefore its tag. Stated explicitly because it will otherwise
  read as a defect to whoever meets it first; `BR-VEND-009` already makes pin bumps
  deliberate.
- **`BR-BUILD-007` revised — `CACHE_BUST` hashes *all* resolved commits, Frappe included.**
  As written it covered "the resolved app commits" only, which cannot satisfy its own goal
  ("a correct build MUST NOT require `--no-cache`"): `FRAPPE_BRANCH` enters the layer cache
  key by **name**, so a Frappe branch that *moves* keeps its name and would reuse a stale
  `bench init` layer. Brian approved including Frappe's commit, which also aligns the input
  set with `BR-BUILD-008`'s tag hash. Upstream's own recommended technique (an `apps.json`
  hash) has the same gap.
- **Two upstream corroborations recorded in `04-lessons-learned.md`.** The vendored
  `frappe_docker` docs turn out to state, in prose, two things this project had derived
  independently: **§1** — "BuildKit is the default builder starting with Docker Engine
  23.0" (`02-setup/02-build-setup.md:15`), confirming what was marked an inference about
  `BR-CLI-007`'s version floor; and **§2** — that `CACHE_BUST` exists precisely because
  secret contents are excluded from layer cache keys. **§4** gains a third: upstream
  documents `podman build` as a first-class equivalent with byte-identical flags,
  independent support for `ADR-027`. Reading the vendored docs earlier would have
  shortened that investigation.
- **`BR-CLI-007` revised — `git` added to the build-role preflight.** Implementing
  `resolve.py` surfaced that `git` is an unlisted build prerequisite: every manifest ref
  is resolved with `git ls-remote` (`BR-BUILD-005`), so a machine without git fails at
  resolution time rather than at preflight. Brian confirmed git is a prerequisite; the
  requirement now names it. No minimum version — `ls-remote` and its pattern matching
  predate every git a current distribution ships.
- **Lessons §9 — a pattern-filtered `git ls-remote` omits the peeled ref.** Found while
  implementing `resolve.py` (`BR-BUILD-005`): requesting `<ref>` alone returns an
  annotated tag's **tag object**, not the commit it peels to; `<ref>^{}` must be passed
  as a second pattern. Left uncorrected this would have recorded an object no clone ever
  checks out into provenance (`BR-BUILD-011`), the input hash (`BR-BUILD-008`), and
  `CACHE_BUST` (`BR-BUILD-007`) — well-formed and wrong. Unit tests passed throughout,
  because the stub returned what an *unfiltered* `ls-remote` returns; caught only by
  resolving against a real repository. No requirement changed.
- **`ADR-029` + `BR-CFG-012` — config discovery and precedence, finally documented.**
  `BR-CLI-014` promised "documented precedence" that was never written down; implementing
  `config.py` forced the gap. **Decided:** the manifest root and cairn's own project root
  are resolved by independent searches — `--manifest` if given, else the nearest
  `cairn.toml` walking up from the working directory, while the vendored tree stays
  anchored to cairn's root. They coincide in development and stop coinciding once cairn
  is `pip install`-ed, with no code change required. Build config layers
  `~/.config/cairn/config.toml` (machine-wide) under an optional `cairn.local.toml`
  **beside the manifest**, overriding key-by-key. `BR-CLI-014` now cites `BR-CFG-012`
  rather than promising documentation. `ADR-029` records one deferred gap: the wheel
  packages only `src/cairn`, so a pip-installed cairn has no vendored tree to build from
  — a `BUILD`-phase packaging concern.
- **Corrected `docs/plans/phase-1-build.md`**, whose illustrative manifest still showed
  the pre-approval `[cairn] name` and `[cairn.frappe] branch`. The approved
  `BR-BUILD-002` mandates `image_name` and `url`/`ref`; the plan is downstream of the
  requirements, so it was brought into line (and gained the `BR-BUILD-003` ordered-list
  comment that every shipped template must carry).
- **`ADR-027` — build engine is pluggable (`docker` | `podman`); deploy engine stays
  Docker.** Adopted after the measured buildah result. The unlock was recognizing that the
  build machine and the target are **different machines** whose only interchange is an OCI
  image in a registry, so `DEPLOY` needs no change at all — `BR-DEPLOY-005` already reads
  provenance over the (engine-independent) registry manifest API. Engine is auto-detected
  (prefer `docker`, else `podman`) and overridable via `engine =` in **local build config**,
  never in the portable `cairn.toml`. **Revised:** `BR-CLI-007` (role-aware preflight),
  `BR-BUILD-006` ("BuildKit secret" → "build secret"), `BR-BUILD-011` (engine's `--label`),
  `BR-BUILD-012` (exact build command), `BR-CFG-008` (engine is build config),
  `BR-CFG-010` (`docker login` / `podman login`); **amended** `ADR-003`. Engine floors:
  Docker v23+, podman v4+ (measured on 5.4.2). Carried risks: OCI-vs-v2s2 manifest format
  on push, and label readback across engines — both to confirm against a real registry.
  Rationale, evidence, and risks in `ADR-027`; motivation was avoiding a second engine
  managing nftables chains on a build-only laptop.
- **`ADR-028` — `cairn doctor` is role-aware, detected from context.** One package serves
  two roles (`ADR-018`), so a fixed preflight reports irrelevant failures. Build/control:
  build engine, vendored-tree integrity, config. Target: Docker + Compose, systemd,
  registry reachability. No flag in the common case (`BR-CLI-014`). The **target-role
  branch lands with `DEPLOY`**; doctor implements the build role today.
- **New document type — `docs/04-lessons-learned.md`.** Durable technical findings about
  the tools cairn builds on, kept separate from `BR` (what must be true), `ADR` (what we
  chose), and the discussion log (how we got there); each finding marked **measured** or
  **reasoned** and citing the IDs it illuminates. Added a row for it to `/CLAUDE.md`'s
  artifacts table. Seeded with seven findings from the Docker/podman investigation, the
  most consequential being **why `BR-BUILD-007` (`CACHE_BUST`) is a correctness
  requirement rather than an optimization**: a BuildKit secret's contents are excluded
  from the layer cache key by design, so editing `apps.json` alone will *not* invalidate
  the `bench init` layer. Also records that `Containerfile:144` strips app `.git`
  metadata — foreclosing image inspection as a provenance source and making
  `BR-BUILD-005`/`BR-BUILD-011` necessary rather than tidy.
- **Measured: buildah 1.39.3 / podman 5.4.2 satisfies the build side** (`BR-BUILD-006`,
  `BR-BUILD-007`) — secret mount honoured with `uid=`/`gid=`, no leak into layers or
  history, `CACHE_BUST` keying the cache in both directions. Retracts an earlier
  overstated claim that buildx has no podman equivalent. **No requirement changes**: the
  docs still name Docker (`BR-CLI-007`, `BR-BUILD-011`, `ADR-003`) and DEPLOY remains
  compose-shaped and untested against podman. Recorded so the question can be reopened
  cheaply if it ever is.
- **Phase 4 — second module (`cairn doctor`).** Implemented `src/cairn/doctor.py` (Docker
  Engine v23+ and buildx probes, plus the three vendored-tree preconditions) and
  `vendor.assert_build_inputs` — the first implementation of `BR-VEND-006`, deriving the
  required build inputs from the Containerfile's own context `COPY`s rather than a
  hardcoded list. Cites `BR-CLI-007/012/015`, `BR-VEND-005/006/007`. 20 unit tests
  (same `BR` IDs), ruff-clean; both the pass and fail paths verified end-to-end.
  **`BR-CLI-007` is landed partially by design:** its *"config valid"* leg awaits the
  config module and will be added when `config.py` lands (`BR-CLI-014`, `BR-CFG-008`,
  `BR-BUILD-002`). Decided then: a **missing** `cairn.toml` will WARN and keep exit 0
  (doctor is a machine preflight, legitimately run on a target host or before a manifest
  exists); a **malformed** one will FAIL. `--json` was deliberately not added — `BR-CLI-013`
  scopes it to `images`/status.
- **Phase 4 begins — first module (`VEND`).** Made the project a real Python package
  (hatchling, `src/` layout, `cairn` console script + `datahenge-cairn` alias, typer, ruff,
  pytest). Implemented `src/cairn/`: `project.py` (root discovery + vendor-source parsing),
  `vendor.py` (thin `ventwig` wrappers + drift/`.git` integrity checks), `cli.py` (Typer
  app with the `vendor status|sync` group). Cites `BR-VEND-003/005/007`, `BR-CLI-001/006/015`.
  9 unit tests (same `BR` IDs), ruff-clean; `cairn vendor status` verified end-to-end
  against the real vendored tree.

- **Non-requirement consistency sweep.** Aligned forward-looking docs with the approved
  requirements: project scope + overview reframed to **two pillars + a data-plane boundary**
  (was "three pillars"/"backup·restore·rollback"); `CLAUDE.md` `DATA` area updated; "DB
  snapshot" removed from the cairn metaphor. Added **supersession notes** to `ADR-012`
  (no pre-migrate snapshot) and `ADR-019` (cairn performs no restore), both pointing to
  `ADR-022`. Banner-marked the Phase-1 build plan as **superseded-in-part** (markers are
  labels not `.cairn/markers/`; no `cairn markers` command; `DATA` is a boundary). History
  docs (discussion log, this CHANGELOG) left as append-only record.
- **Requirements clarity audit.** Tightened all six requirement docs
  (`BR-VEND/BUILD/DEPLOY/DATA/CFG/CLI`) to crisp normative statements; migrated inline
  rationale/mechanism/verification into the cited ADRs and the discussion log. IDs and
  citations unchanged; approvals stand (clarity revision, not a design change).

- **`CLI` approved (`BR-CLI-001`…`015`). ALL SIX requirement areas now approved**
  (`VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`) — the Scribe Coding requirements phase
  is complete. Next: Phase 4 (modular code), one small module at a time.
- **`CLI` drafted (Pass 1)** — `docs/requirements/06-cli.md`, `BR-CLI-001`…`015`. Verb set:
  `build [--push]`, `push`, `new-tag`/`retag`/`retire` (create/move/decommission, with
  `--latest|--previous|--id|--from` selectors + typo-guards), `images`, `vendor`, `doctor`,
  `reconcile`. Conventions: `--dry-run`, prod-gate `--yes`, `--json` on reads,
  stdout/stderr logging + exit codes, config discovery. Sharpened `BR-DEPLOY-009` to a
  **declared environment list** (not bare convention).
- **Verified GHCR deletion is version-based** (no per-tag delete; deleting a version removes
  its image + all tags; public >5,000-download versions are undeletable). So `cairn retire`
  decommissions at cairn's layer only; the registry tag name lingers. Recorded in the
  deferred GHCR-cleanup note.
- **`DEPLOY` approved** (`BR-DEPLOY-001`…`020`) — all decisions resolved; only the deferred
  GHCR-side cleanup command remains (non-blocking). Five of six requirement areas approved.
- **Naming & packaging (`ADR-018` closed).** Single package/repo, name **`datahenge-cairn`**
  (`cairn` taken; `docker-cairn`/`frappe-cairn` falsely imply Docker/Frappe ownership;
  `datahenge-cairn` signals Datahenge + doubles the stone motif). Import package `cairn`;
  command **`cairn`** (+ `datahenge-cairn` alias). Split deferred behind an explicit
  trigger. Renamed the project **`docker-cairn` → `cairn`** throughout the docs (prose) and
  the local repo directory → `datahenge-cairn`; `pyproject` name → `datahenge-cairn`.
  Remote left untouched (new one to be created later). Also corrected the README pillars to
  match the current scope (two pillars + data-plane boundary; no DB backup/restore).
- **`DEPLOY` sequencing / health / failure / observability** (`BR-DEPLOY-016`…`020`).
  Single-flight reconcile; in-place recreate; `migrate` after every image enable (incl.
  rollback); health-gated success. **`ADR-025`**: deploy failure = **halt + report**, no
  auto-rollback (rollback stays manual). **`ADR-026`**: log to stdout/stderr only (host owns
  monitoring); optional best-effort **failure webhook** (transport-agnostic). Closed
  **`ADR-011`** (tagging settled by `BR-BUILD-008`).
- **`DEPLOY` secrets, single-site, prod gate** (`BR-DEPLOY-009`…`015`). Environment model:
  two halves joined by the tag; cairn **renders** the compose from the descriptor.
  **Closed `ADR-017`** (secret-agnostic: cairn references/wires but never handles secret
  values; registry pull via `docker login`; DB secrets via `compose.mariadb-secrets.yaml`
  recommended, `.env` supported). **Closed `ADR-016`** (single site per environment;
  multi-site deferred). Prod pointer moves require explicit confirmation; `install-app`
  to prod doubly explicit. Only sequencing/health remains open in DEPLOY.
- **`DEPLOY` opened, drafted (Pass 1, partial)** — `docs/requirements/03-deploy.md`,
  `BR-DEPLOY-001`…`008`: pull-based reconcile (target polls the env tag's digest);
  deploy/promote/rollback are one primitive (server-side retag, no rebuild); registry
  introspection reads provenance labels remotely; timer-driven GC keeps last N images and
  **never touches volumes**; cairn deploys to existing environments only.
- **Closed `ADR-010`** — desired-state pointer = the environment's moving registry tag
  (target polls; laptop advances by retag).
- **Added `ADR-024`** — reconcile is a thin orchestrator over docker/compose + registry
  API + systemd; Watchtower/Flux/ArgoCD evaluated and rejected (with reasons).
- **`DATA` approved** (`BR-DATA-001`…`008`) — the data-plane boundary area is settled.
- **Opt-in `bench install-app` (`ADR-023`).** A concrete case (deploying a 5-app image to
  a 2-app TEST site) showed `bench migrate` does *not* install newly-added apps. Decision:
  a default deploy is code-swap + `migrate` only (never changes a site's app set — least
  surprise); `bench install-app` is a second sanctioned Frappe command, **opt-in only**,
  delivered via the target's reconcile (no SSH). Added `BR-DATA-008`; amended `ADR-014`
  ("sole automatic" + install-app) and `ADR-022`.
- **Refined `BR-DATA-006` for accuracy:** cairn does not *itself* write to volumes, but the
  stack's own `configurator`/entrypoint reconcile the volume at every `compose up`
  (`ls -1 apps > sites/apps.txt`, `bench set-config -g …`, relink `sites/assets`) — Frappe's
  machinery, not cairn.
- **Established the data-plane boundary (`ADR-022`).** cairn ships code, not data: no SQL
  connection, no `bench execute`/`frappe` code, no DB movement; altering a target DB
  directly is impossible by construction. Sole exception: `bench migrate` after an image
  swap. Volumes/site-configs/`encryption_key` are aware-but-untouched.
- **Closed `ADR-014`** — `bench migrate` is the sole sanctioned (indirect) DB interaction;
  mandatory post-deploy, opaque, non-destructive. **Closed `ADR-013`** — backup / restore
  / DB-movement are out of scope.
- **Wrote `DATA` as a boundary area** (`docs/requirements/04-data.md`, `BR-DATA-001`…`007`,
  drafted). Reframed **Pillar 3** in the project scope; **revised approved `BR-CFG-005`/
  `006`** (no two-classes action; no volume seeding — `BR-DATA-006` supersedes); dropped
  "DB snapshot" from the cairn-marker concept.

## 2026-07-23

- **`CFG` fully approved** (build config signed off). `BR-CFG-010` refined: cairn may read
  a registry token from env / a local env file to perform a *transient* `docker login`,
  but still never stores credentials.
- **Closed `ADR-009`** — cairn is registry-agnostic; **GHCR is the recommended default**
  (ERPNext/GitHub ubiquity; fits the pull-only model). Follow-up: a GHCR setup runbook is
  needed (deferred to Phase-6 user docs).
- **`CFG` target config approved; build config drafted (Pass 1).** Added
  `docs/requirements/05-config.md`. Target (`BR-CFG-001`…`007`): env config lives on the
  sites volume and is never clobbered; opacity line (Frappe framework config understood,
  app config opaque); never overwrite Frappe-managed `site_config.json`; two config
  classes (data-bound `encryption_key` must travel vs env-authority must not);
  preserve-first + additive-seed provisioning. Build config (`BR-CFG-008`…`011`, drafted):
  build-time settings live in a local file separate from the portable `cairn.toml`;
  registry-agnostic; auth delegated to `docker login`; provenance labels ride with the
  pushed image (registry = image-and-metadata store).
- **Narrowed `ADR-009`** to "recommended default registry only" (cairn is now
  registry-agnostic via build config).

## 2026-07-21

- **`BUILD` requirements approved.** `BR-BUILD-008` tag composition settled as option (b)
  — human-legible slug + input-hash (`v16-a1b2c3d4`) + moving `latest`. Marked the
  `BUILD` row **approved**.
- **`BUILD` drafted (Pass 2).** `BR-BUILD-001`…`013` in `docs/requirements/02-build.md`.
  Verified bench pins by branch/tag only (no raw-SHA); adopted **Option A**
  (resolve-and-record commits, pin tags, warn on branch) — correcting the earlier
  "apps.json accepts commits" claim. Provenance is stamped as **OCI image labels**
  (not stored in the cairn tool repo); optional sidecar lives in the deployment dir.
  One item still open: `BR-BUILD-008` tag composition (pure hash vs. human-legible).
- **Closed `ADR-015`** (manifest `cairn.toml` schema + Option A app-pinning), moved to
  the closed register.
- **Added `ADR-021` (open)** — a deliberate fork of frappe_docker (MIT) as the sanctioned
  escape hatch for control unattainable while vendoring unmodified; deferred, not a
  default.
- **Manifest schema talk-through (pre-`BUILD`).** Settled: standalone `cairn.toml`
  (one file = one image, env-agnostic); `image_name`; special `[cairn.frappe]` section;
  **ordered** `[[cairn.apps]]` list = positional install order (no dependency solver);
  `[cairn.build]` knobs (`python_version`, `node_version`, `install_chromium`) +
  passthrough; no separate lockfile (marker is the record); input-deterministic (not
  hermetic) reproducibility bar. Redis/MariaDB versions are a DEPLOY concern (compose
  image tags), not image/manifest inputs. Documented the ordered-list rule prominently in
  `README.md` (required inline in every shipped template).
- **`VEND` requirements approved.** Brian signed off `BR-VEND-001`…`010` (hard-stop drift
  reasoning accepted; `ADR-020` parked open). Marked the `VEND` row **approved** in the
  requirements overview.
- **Began Phase 2 (requirements co-creation) with `VEND`.** Drafted `BR-VEND-001`…`010`
  in `docs/requirements/01-vendoring.md` (Pass 2): drift is a hard stop with no override;
  pin is immutable-intent and mechanism-agnostic; single vendored source.
- **Added `ADR-020` (open)** — strengthen upstream-pin immutability via a ventwig
  enhancement (SHA pinning and/or sync-time commit verification); non-blocking.
- **Adopted Scribe Coding** (Document-Driven AI Development) as the project methodology;
  added the ground-rules contract at `/CLAUDE.md`. Established the dual identifier
  system: `BR-<AREA>-NNN` (requirements) and `ADR-NNN` (decisions/ADRs).
- **Established the living-documentation infrastructure:** created
  `docs/requirements/` with `00-overview.md` (requirements root + ToC + conventions)
  and this `docs/CHANGELOG.md`.
- Requirements areas defined: `VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`.
  Per-area requirement documents are pending Phase-2 co-creation.
- **Renamed the decision-record prefix `D-NNN` → `ADR-NNN`** across all docs
  (`ADR-001`…`ADR-018`), for an explicit, self-describing identifier that matches
  `cofferdam-app`'s ADR convention. No IDs or numbering changed — prefix only.
- **Set the build PoC target to Frappe v16 + ERPNext + BTU** (`Datahenge/btu@version-16`),
  superseding the earlier ERPNext-only PoC now that a suitable, non-contradictory custom
  app exists. Updated the Phase-1 plan's verification target and illustrative
  `cairn.toml` manifest (the actual `cairn.toml.example` file is deferred to BUILD
  implementation, after Phase-2 `BUILD` requirements exist).
- **Added `ADR-019` — strict decoupling from cofferdam** (cairn and cofferdam are
  mutually unaware). Reframed the Phase-1 plan's Pillar-3 note around a *generic*
  restore-scoping rule (never overwrite local env config on the sites volume) instead of
  cofferdam-specific enforcement; retracted the earlier `cofferdam validate` deploy
  invariant. Genericized the `CFG` area description in `CLAUDE.md` and the requirements
  overview (cofferdam now only a non-normative example).

### Predating this changelog (context)

The following were created before the changelog existed and are its baseline:
`docs/00-project-scope.md`; the decision register `docs/01-decisions-closed.md`
(`ADR-001`…`ADR-008`, `ADR-012`) and `docs/02-decisions-open.md`
(`ADR-009`…`ADR-011`, `ADR-013`…`ADR-018`); `docs/03-discussion-log.md`; and the Phase-1
build plan `docs/plans/phase-1-build.md`. Vendored upstream `frappe_docker` pinned to
`v3.2.1` via ventwig.
