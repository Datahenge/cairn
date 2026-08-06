# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-08-06 (new lessons-learned topic: Docker & host storage)

Closing out the same client-VPS disk-space incident as the two entries below: six durable
findings recorded in new **`docs/technical/04d-lessons-docker-and-host-storage.md`** —
Docker's `data-root` vs. containerd's independent `root`; disproving a plausible-looking
double-counting theory with `stat -f` rather than trusting matching sizes/timestamps; not
nesting one service's data inside another's managed tree; `sudo`'s glob-expansion-happens-
first gotcha; verifying a device explicitly rather than trusting an implicit `mount
<path>` → `/etc/fstab` lookup on a live migration; and when collapsing to one shared
volume beats textbook per-service isolation. `docs/technical/04-lessons-learned.md`'s
topic index updated to route to it.

## 2026-08-06 (`changelog_rotate.py` could not parse its own generated footer)

Found immediately after writing the entry below: `docs/CHANGELOG.md` tripped `DOC002`'s word
budget, and running the prescribed fix (`ai/tools/changelog_rotate.py --dry-run`) crashed
instead of archiving anything. `render_footer` writes the footer heading as `## Archived
entries`; `parse_changelog`'s block loop only skips a trailing block that does *not* start with
`## ` — so the tool's own output, fed back in on a later run, hit the "not a dated entry"
branch and raised. Bug found and fixed, no requirement redesign: both sites now reference one
`FOOTER_HEADING` constant, and `parse_changelog` explicitly recognizes and discards that exact
block rather than only the no-heading case. Rotation re-run after the fix; archived the five
oldest entries (2026-08-04 through 2026-08-05) to `docs/archive/CHANGELOG-2026-08-04-to-
2026-08-05.md`, confirmed against `docs_check.py` and the full test suite.

## 2026-08-06 (new userdocs guide: Docker storage on a multi-volume host)

Same VPS relocation session that surfaced the `disk-headroom` doctor bug (below): after fixing
`cairn-registry`'s `data_dir`, Brian tried to solve the client VPS's small-root-disk problem
generally by pointing containerd at the big Docker volume too — nesting a directory inside
`/var/lib/docker` and moving files there. That doesn't work: containerd's `root` setting
(`/etc/containerd/config.toml`) is completely independent of Docker's own `data-root`
(`/etc/docker/daemon.json`), and on a host with Docker's containerd image store enabled
(`driver-type: io.containerd.snapshotter.v1`), containerd — not Docker's own graphdriver — is
what actually holds the growing image/container layer bytes. Redirecting only `data-root`
leaves containerd silently defaulting to `/var/lib/containerd`, on whatever volume holds
ordinary `/var/lib` — the small one. Brian: "a huge footgun for anyone running multiple volumes
on a VPS," and asked for it in published docs before it bites someone else.

Not a cairn requirement — this is host-level Docker/containerd configuration, nothing cairn's
own code touches (confirmed: no reference to `containerd` anywhere in `src/` or `docs/`) — so no
`BR`/`ADR` ID, just a new userdocs page: **`userdocs/guides/docker-storage-layout.md`**,
covering how to tell which daemon actually holds the space (`ncdu`, `docker info`, the `moby`
namespace check on containerd's shims) and how to relocate containerd's `root` onto its own
volume rather than nesting it inside `/var/lib/docker` (the same data-root-blast-radius caution
`ADR-060` already applied to `cairn-registry`'s own `data_dir`, here generalized to any
Docker host). Linked from `userdocs/guides/index.md` and, since this needs deciding *before*
first use, from `userdocs/get-started/index.md`'s Prerequisites section. `mkdocs.yml` nav gained
a `Guides` submenu (previously a single flat page) to hold it.

## 2026-08-06 (`cairn-registry doctor`: a `PermissionError` on `data_dir` no longer crashes the disk-headroom check)

Found live while helping Brian relocate a client VPS's `data_dir` off a disk-space-constrained
root filesystem: he'd pointed `[registry] data_dir` at a path under `/var/lib/docker`, which
Docker keeps locked down against non-root traversal by design. `cairn-registry doctor` crashed
with an unhandled `PermissionError` instead of reporting a normal `FAIL` row.

Bug found and fixed, no requirement redesign — `BR-REG-011` already requires `doctor` to report
three checks, not throw: `_check_disk_headroom` (`cli_registry.py`) called `config.data_dir.
exists()` *outside* the function's own `try`/`except OSError` block, so an `EACCES` on an
unreadable parent directory (raised by `exists()` itself, not just the `shutil.disk_usage()`
call two lines below that was already guarded) propagated as an internal-error crash. Fixed by
moving the `.exists()` call inside the existing `try` block — one-line fix, same error-message
shape the `disk_usage()` path already used. New test
(`test_check_disk_headroom_reports_permission_error_as_fail`, `test_cli_registry.py`) exercises
the exact failure mode by monkeypatching `Path.exists` to raise `PermissionError`. Full suite
passes.

## 2026-08-06 (`cairn-build doctor` reports build-timer status; `--all` walks every manifest)

Brian suggested `doctor` mention whether `setup-timer`'s systemd units exist and are
enabled/started — currently only checkable by hand, one `systemctl` call at a time.
`cairn-adopt doctor` already had this for the reconcile timer (`check_reconcile_timer`); the
build side had no equivalent.

Design settled through a short back-and-forth: single-manifest scope (mirroring `github
reachability`) was the obvious first cut, but Brian rejected it — `/srv/cairn/` is a static,
known directory (`BR-CLI-022`), and a build host commonly serves more than one client, so
scoping to one manifest at a time would force an operator to script their own enumeration to
be sure every timer on the host is actually running. Settled on two mutually exclusive scope
flags: `--manifest <path>` (one manifest) and `--all` (every manifest under
`/srv/cairn/*/*.toml`, one result per manifest) — recorded as `ADR-070`. A further question —
whether `--all` should also broaden `config`/`github reachability` into a full per-manifest
host audit — was deliberately deferred rather than folded in; tracked as `ADR-071`
(`docs/open/OPEN_DECISIONS.md`). Bare `cairn-build doctor` (neither flag) is unchanged and
still runs every host-level check, but now reports the build-timer check as skipped, with the
fix, rather than omitting it silently the way `github reachability` does.

**`BR-CLI-007`** (`docs/requirements/06-cli.md`) amended in place: the `cairn-build doctor`
bullet documents the new check and its two scope flags.

**Code:** `provision.build_unit_name`'s naming logic extracted into a pure
`unit_name_for(client, image_name, environment)` so `doctor.py` can compute the same unit name
`setup-timer` would install for any manifest it walks, without duplicating the f-string.
`doctor.py` gains `check_build_timers`/`_check_one_build_timer`/`_known_manifest_paths`; wired
into `run_build_checks`. `cli_build.py`'s `doctor_command` gains `--all`, checked against
`--manifest` via `typer.BadParameter` before either check family runs. Tests added to
`tests/test_doctor.py` and `tests/test_cli_build.py`.

**Same-day follow-up.** Brian, re-reviewing, suspected the *service* also needed to be active,
not just the timer. Checking the actual unit definitions showed both cairn-build's build
service and cairn-adopt's reconcile service are `Type=oneshot` — they run, exit, and return to
`inactive` between firings, so "active" is the unusual state, not the healthy one; his
suggested check would have false-WARNed on every healthy install. The real gap underneath the
hunch was genuine, though: neither check asked whether the *last* run had actually succeeded.
Added `systemctl is-failed` on the service to both `check_build_timers` and — since
`cairn-adopt doctor`'s pre-existing `check_reconcile_timer` had the identical blind spot —
`check_reconcile_timer` too, taking priority over each check's existing enabled/active read. A
failed last run now FAILs the check outright rather than reporting the more benign "not yet
started." `ADR-070` and `BR-CLI-007` amended in place; no new ID minted.

---

## 2026-08-06 (`images` splits by role: `cairn-build` local-only, `cairn-registry` gains `--host`/`--namespace`/`--image`)

Brian flagged `cairn-build images`'s help text as inaccurate — "reads the registry by default"
said nothing about needing a manifest first, and a bare invocation errored outright. First fix
considered was a `--local` fallback; Brian pushed back on the premise instead: examining a
*registry* shouldn't be reached indirectly through a manifest's `image_name`. Settled into a
clean split, restated by Brian as "the builder talks about things the builder owns; the
registry talks about things registries own (a local one, or a remote one)."

**`cairn-build images` (`BR-CLI-005`) becomes `[--json]`, nothing else, unconditionally local.**
No `--manifest`, no `--local` — there is no other mode to flag. `_registry_repository` and the
old registry branch are deleted outright.

**`cairn-registry images` (`BR-REG-005`) gains `--host`/`--namespace`/`--image` and the
provenance detail (frappe/app versions, `cairn-build-owned` marker) the old `cairn-build`
registry mode used to show**, so that capability relocates rather than disappears. Re-reading
the userdocs mid-design surfaced a real constraint: `ghcr-setup.md`/`ghcr-tags-and-
troubleshooting.md` already use the old registry mode against **GHCR**, a real authenticated
third-party registry, which only works because the single-repository read
(`registry.tags`/`inspect`) does the full anonymous-then-bearer-token exchange (`BR-CFG-010`).
`registry.catalog()` — needed to *enumerate* a registry — is anonymous-only by design, scoped
to cairn's own self-hosted registry. Resolved by splitting the lookup: an **exact**
`--namespace` + `--image` (no glob) reads that one repository directly, bypassing the catalog
entirely — this is what keeps GHCR reachable via `docker login`/`podman login`. Any other
combination (no `--image`, or a glob) enumerates via the catalog, which stays limited to
registries that allow anonymous catalog access.

Also fixed incidentally: `cairn-registry images`' "Repository" line printed the bare catalog
name; `userdocs/registry/cli.md` already (incorrectly) documented it as the full reference
with registry host. The rewrite makes the doc's existing claim true.

Recorded as `ADR-069` (`docs/decisions/069-images-splits-by-role-builder-local-registry-remote.md`)
— amends a requirement with a rejected alternative (the `--local`-fallback draft) worth
remembering. `BR-CLI-005`/`BR-REG-005` (`docs/requirements/06-cli.md`,
`docs/requirements/08-registry.md`) rewritten. Code: `cli_build.py`'s `images_command`
simplified; `images.py`'s `registry_as_json` renamed `registry_payload`, now returning a
`dict` so `cli_registry.py` can assemble one multi-repository JSON payload; `cli_registry.py`'s
`images_command` extended, its old `_grouped_tags`/`_repository_json` helpers replaced by
`images.py`'s provenance-aware equivalents. Tests updated in `test_cli_build.py` and
`test_cli_registry.py`. Userdocs updated: `userdocs/builder/index.md` drops its `--local`
example; `userdocs/registry/cli.md`, `ghcr-setup.md`, and `ghcr-tags-and-troubleshooting.md`
now point at `cairn-registry images`.

## 2026-08-06 (`05-implementation-index.md` trimmed — Completion Judgment cells are verdicts, not incident narratives)

Brian flagged the file as wordy/busy right after the `setup-timer` entry below added yet another
paragraph to an already-long cell. Looking at it directly: the "Completion Judgment" column had
drifted from its own stated purpose (a judgment) into full incident retelling — which functions
were renamed, exactly how each bug happened, ADR-by-ADR blow-by-blow — duplicating
`docs/CHANGELOG.md`, which already owns that narrative. The file had grown to 2,271 words,
repeatedly bumping into `docs_check.py`'s word ceiling.

Trimmed every bloated cell to a terse verdict plus a `docs/CHANGELOG.md` pointer for the story
(2,271 → ~1,450 words); table structure, code locations, and test/owner-doc columns untouched.
Process/documentation-hygiene work, not a product decision — no new Decision/ADR file
(`01-documentation-conventions.md`'s own rule). Two guardrails added so this doesn't recur
unnoticed: a short note directly in `05-implementation-index.md`'s intro ("a cell is a verdict,
not a narrative"), and a new "Completion Judgment Cells Stay Terse" section in
`01-documentation-conventions.md` recording this as a cautionary tale, with a checkable rule of
thumb (>~3 sentences in a cell means narrative crept back in) for future documentation review
sessions to catch.

## 2026-08-06 (`setup-timer` output: quieter empty-stop summary, one non-contradictory error message)

Brian's first live `cairn-build setup-timer` run on the Life Scientific test VPS (`W-013`)
refused correctly — a private `erp-lifescientific` repo with no `github-token.env` populated
yet — but the output had two rough edges he flagged as worth polishing while true, not a design
mistake needing a redesign: a `--- summary ---`/`nothing to do` block printed under `Stopped:
...` even though the run had done nothing at all, and the error text gave two remedies that
disagreed — `resolve.py`'s generic hint ("No `$CAIRN_GITHUB_TOKEN` is set — set it and retry")
assumes an interactive build reading the invoking shell, while `setup-timer`'s own check
(`ADR-067`) deliberately reads only the client's token file, never the shell. "Set it and
retry" is actively wrong advice on that path.

Two in-place fixes, no requirement redesign — bugs found and fixed, not a rejected alternative
worth a Decision/ADR file (`01-documentation-conventions.md`'s own rule):

- **`setup_runner.py`**: `execute()`'s `Aborted`/`KeyboardInterrupt` handlers now skip the
  `--- summary ---` block entirely when `Report.is_empty()` — new method, also now the single
  source of truth `_summarize()`'s own "nothing to do" fallback reuses (previously that check
  omitted `report.revert`, a latent inconsistency fixed as a side effect). A stage header
  (`[timers]`, `[preflight]`, …) stays as-is: three existing tests
  (`test_cli_build.py`/`test_cli_adopt.py`/`test_cli_registry.py`) assert on it as proof that
  `setup-timer` runs only its own stage, not `setup`'s — genuinely informative, not noise.
- **`github_auth.py`** gained `missing_token_hint()`, the single source of truth for the
  generic "set it and retry" sentence `resolve.py`'s `_run()` now calls instead of inlining.
  `provision.py`'s `_check_timer_github_reachability` strips that exact sentence
  (`str.removesuffix`) before appending its own file-based remedy, so the operator sees one
  fix, not two. `resolve.py`'s own message is unchanged for every other caller (a plain build
  failure still correctly points at the operator's own shell, per `BR-BUILD-016` point 5).

`docs/requirements/06-cli.md`'s `BR-CLI-023` paragraph amended in place to describe the
stripped hint. `docs/open/OPEN_WORK.md`'s `W-013` row updated; still open (`setup-timer`'s
happy path — a working token file — remains unexercised against a real host).

## 2026-08-06 (recipe tree flattened — no more nested `frappe_docker/`, `images/custom/`, or `resources/core/`)

Follow-on to the same-day trim below: Brian asked to flatten what remained. The nested
`frappe_docker/` subdirectory is gone — `compose.yaml`, `overrides/`, `example.env`,
`images/`, and `resources/` now sit directly under `src/cairn/recipe/`. `images/custom/`
collapsed to `images/` and `resources/core/` to `resources/`, since neither had a sibling
left to be distinguished from (the alternate `bench`/`layered`/`production` Containerfiles and
frappe_docker's own `docs/`-nested `core`/other resource groupings were already dropped in the
trim). `frappe_docker/LICENSE` folded into `ATTRIBUTIONS_FRAPPE_DOCKER.md` verbatim rather than
kept as a separate file. Pure scaffolding reorganization — no new ADR (`01-documentation-
conventions.md`'s own rule for this), `BR-VEND-005` and `BR-VEND-001`/`003` in
`docs/requirements/01-vendoring.md` updated in place instead. Code: `vendor.py`'s
`FRAPPE_DOCKER_DIR`/`FRAPPE_DOCKER_SOURCE` collapsed into one `RECIPE_DIR`;
`CUSTOM_CONTAINERFILE` now `images/Containerfile`; the Containerfile's own `COPY` lines
repointed at `resources/`. `pyproject.toml`'s ruff `extend-exclude` and `ai/tools/
docs_check.py`'s `EXCLUDED_PATHS` both updated to the flattened root. Docs swept for the old
paths: `02-build.md`, `00-coding-standards.md`, lessons-learned `04b`/`04c`, `AGENTS.md`,
`userdocs/builder/index.md`, `userdocs/reference/index.md`. `tests/test_vendor.py` updated to
match; full suite passes.

## 2026-08-06 (recipe tree trimmed to load-bearing files; `ADR-068` grows cairn's scope to initial provisioning)

Two related changes, same session, both prompted by Brian: make `src/cairn/recipe/frappe_docker/`
actually cairn's own rather than the untouched byte-for-byte bootstrap copy `ADR-059` left
behind.

- **Recipe trim + attribution (`BR-VEND-005`).** Deleted everything under
  `src/cairn/recipe/frappe_docker/` that no cairn code path reads and that isn't part of the
  compose scaffolding cairn now commits to owning (see next item): upstream's own docs site,
  test suite, CI workflows, contributor/devcontainer tooling, community-health files, `pwd.yml`
  (the unparameterized quick-start compose shape `ADR-021`'s fork-pressure incident already
  flagged as the wrong one), `docker-bake.hcl` (redundant with cairn's own `build.py` build
  orchestration), and the three alternate Containerfiles (`images/bench`, `images/layered`,
  `images/production`) `BR-BUILD-009` never builds. Kept: the build inputs
  `assert_build_inputs()` already required, plus `compose.yaml`/`overrides/*.yaml`/`example.env`
  (see below), and `LICENSE`. New `src/cairn/recipe/ATTRIBUTIONS_FRAPPE_DOCKER.md` credits
  `frappe/frappe_docker` and links to the preserved `LICENSE`; `BR-VEND-005` added to
  `docs/requirements/01-vendoring.md` requiring both be kept current.
- **`ADR-068`: cairn's scope grows to initial provisioning, not just reconcile.** Trimming the
  compose scaffolding raised the question of whether `compose.yaml`/`overrides/*.yaml` were dead
  weight too, since `cairn-adopt` never reads cairn's own copy — it inspects whatever's already
  on the target host. Brian's answer: no, because cairn replacing `frappe_docker` means owning
  the whole lifecycle, not just build+reconcile-against-whatever-exists. Cairn's owned Compose
  stack is now the intended way to provision a *new* environment, and `cairn-adopt` should
  eventually be able to take over ownership of a pre-existing hand-built deployment rather than
  reading around it forever. Neither is built yet — both queued as `W-032`/`W-033` in
  `docs/open/OPEN_WORK.md`, design work only. The `DATA` boundary (`ADR-022`) and
  `BR-DEPLOY-007`'s `bench new-site`/database-creation clause are explicitly unchanged; only the
  "existing environments only" framing around them was amended.

## 2026-08-06 (`.docs_check_allowlist` relocated into `ai/tools/`)

Brian pointed out the allowlist lived at the repo root while everything that reads or writes
it — `docs_check.py`, `changelog_rotate.py` — lives in `ai/tools/`. Moved the file to
`ai/tools/.docs_check_allowlist` (`git mv`, preserving history) and added `docs_check.py`'s
`ALLOWLIST_REL = Path("ai/tools") / ALLOWLIST_FILENAME`, resolved as `root / ALLOWLIST_REL` so
`--root` still targets the checked project's own copy rather than the script's location.
`changelog_rotate.py` already imported `load_word_count_allowlist` from `docs_check`, so its one
hardcoded write path (`_append_allowlist_entry`) just switched to the same constant. `AGENTS.md`'s
artifact table updated to note `ai/tools/` now also holds the data file, not just the two
scripts. Process/tooling-only per the rule above — this entry, no new ID.

---

## 2026-08-06 (Scribe Coding rules tightened; four process-only decisions and a misfiled plan pruned)

Prompted by the same-day directory reorg (below) touching 46 files just to relocate three
folders — mostly cross-reference upkeep — Brian asked to step back: `docs/decisions/` and
`docs/adr/` are the same kind of artifact split only by weight, and several `decisions/` entries
turned out to be about documentation process or tooling calibration, not `cairn` the product.

**Rule change** (`docs/technical/01-documentation-conventions.md`, new "When A Decision Earns A
Decision/ADR File" section): a Decision/ADR file is now reserved for choices about cairn the
product — a rejected alternative with lasting explanatory value, or a requirement amendment that
needs recorded justification beyond "we found a bug and fixed it." Documentation process, tooling
calibration, and scaffolding/directory changes get one `docs/CHANGELOG.md` entry and nothing
else — no new ID, no standalone file. The rule applies to itself, and to this entry.
`docs/technical/25-documentation-authority.md`'s "Post-Implementation Doc Hygiene" gained a
companion rule: archive or delete a `docs/plans/*.md` file the same session its phase reaches
`Implemented`, rather than leaving it for a backlog item to notice later. `AGENTS.md` gained a
one-line pointer to both.

**Pruned under the new rule** (each already fully covered by its own existing `docs/CHANGELOG.md`
entry, confirmed by reading both side by side before deleting): `docs/decisions/054` (GHCR/
registry docs migrated to `userdocs/`), `055` (`docs_check.py` word-count ceiling), `056`
(`docs/CHANGELOG.md` word-count ceiling), and `068` (today's directory reorg, written earlier
this same session — a direct instance of the pattern just retired). `docs/decisions/README.md`'s
index and ID list updated; dangling `ADR-05x`/`068` citations dropped from `.docs_check_allowlist`
and `docs/technical/05-implementation-index.md` (dates kept, ID pointers removed since nothing
resolves them now); `docs/technical/25-documentation-authority.md`'s "Deviations" bullet
repointed from the deleted `068` file to this entry.

**Plan misfiling fixed**: `docs/plans/phase-1-build.md` already carried `status: archived`
frontmatter (since 2026-07-24) but still lived in the live `docs/plans/` tree — moved to
`docs/archive/phase-1-build.md`, closing `W-011`, which existed solely to ask someone to do this.
`docs/plans/next-steps.md`, a 4-line forwarding stub, was deleted outright (unlike ADR/Decision
IDs, nothing cites a plan by a stable ID that must keep resolving) — its one live inbound
citation was in `decisions/054`, deleted above; `docs/archive/README.md`'s own row already pointed
at the archived copy, not the stub.

Left untouched, checked directly: `docs/decisions/008` (a genuine product constraint, not
process noise); `docs/discussions/discussion-log.md` (read in full — no process/meta entries to
trim); `docs/plans/git-mirror-private-apps.md` (live, blocked on `ADR-044`); `docs/archive/**`
(cheap to keep, outside the active reading path).

## 2026-08-06 (`decisions/`/`open/`/`scratch/` nest under `docs/`; `ai/` added for `CURRENT_CONTEXT.md`/`tools/`)

Brian asked for a root-directory cleanup: `decisions/`, `open/`, and `scratch/` were the only
documentation trees still sitting as siblings of `docs/` at the repo root, an artifact of the
canonical Scribe Coding scaffold rather than a deliberate split — every other tree
(`docs/adr/`, `docs/technical/`, `docs/requirements/`, `docs/discussions/`, `docs/plans/`,
`docs/archive/`) already lived under `docs/`.

`decisions/` → `docs/decisions/`, `open/` → `docs/open/`, `scratch/` → `docs/scratch/`.
`CURRENT_CONTEXT.md` and `tools/` (the docs-hygiene scripts) moved into a new root-level `ai/`
directory, separating the AI-agent-facing session router and tooling from `docs/` itself.
Every relative Markdown link whose depth changed was corrected in the same pass;
`ai/tools/docs_check.py` confirms none are broken. `AGENTS.md`'s artifact table,
`ai/CURRENT_CONTEXT.md`, and `docs/technical/25-documentation-authority.md` (Doc Trees table,
Authority table, Reading Orders, and a new entry in "Deviations From The Canonical Scribe
Coding Template") were updated to match. Historical narrative in this file and in
`docs/archive/**` was left as originally written, except where it held an actual link that
would otherwise break. No standalone Decision/ADR file — this is a documentation/scaffolding
change, not a product decision (see the same day's rule-tightening entry below).

## 2026-08-06 — `ADR-067`: `doctor`/`setup-timer` probe `github.com` reachability live, `OQ-003` resolved

Brian, reviewing `ADR-065`'s `EnvironmentFile=-` path, flagged that it wires a missing token
but never detects one: `cairn-build doctor` had no check at all for a manifest's `github.com`
reachability, and `setup-timer` printed the same unconditional reminder regardless of whether
the manifest needed the file or whether it already existed and was correct. The eventual
failure wasn't silent — `BR-BUILD-016` point 5's `RefResolutionError` already names
`$CAIRN_GITHUB_TOKEN` as a candidate fix — but nothing surfaced it before the timer was
enabled or before it fired unattended for the first time.

Both checks reuse `resolve.resolve_manifest()`, the same function `build` itself calls, at
two different fidelities. `doctor` runs it with whatever `$CAIRN_GITHUB_TOKEN` the invoking
shell has exported, mirroring a manual build. `setup-timer` runs it before writing anything,
simulating only what the eventual unit's `EnvironmentFile=` will supply — the parsed
`github_token_env_file(client)` if present, otherwise none — deliberately not the operator's
own shell env, since the unit never inherits that either. `setup-timer` refuses to write or
enable anything on failure; on success the old unconditional warning is dropped, since a pass
already proves the file is either unneeded or correct. `github_auth.py`, `resolve.py`, and
`build.py` are unchanged. `BR-CLI-007` and `BR-CLI-023` rewritten; full rationale in
`docs/adr/067-doctor-and-setup-timer-probe-github-reachability-before-trusting-it.md`.

## 2026-08-05 — `ADR-066`: `build --push` assigns the declared environment by default, `W-021` resolved

Brian resolved `W-021` (raised and deferred 2026-08-04): since `setup-timer`'s generated
script already assigns the environment tag unconditionally on every poll, opt-in
`--assign-tag` on the manual path only bought the interval between polls of explicitness
before the tag got set regardless.

`build --push` now assigns by default; the CLI flag becomes a tri-state
`--assign-tag/--no-assign-tag`. Unset (the default): assign if `--push` was given and the
manifest declares an environment, silently skipping one that declares none — most manifests
don't participate in the environment model, and that's not a mistake. Explicit
`--assign-tag` still errors on a manifest with no environment (`BR-CLI-009`) and still
requires `--push`. `--no-assign-tag` always skips. `BR-CLI-010`'s `:production` gate needed
no new wiring — it already keys off the target environment, not how assignment was
requested. `BR-CLI-002a` rewritten; full rationale in
`decisions/066-build-push-defaults-to-assign-tag.md`.

## 2026-08-05 — `ADR-065`: per-client `EnvironmentFile=` supplies the build timer's GitHub PAT, `OQ-002` resolved

Brian raised this in two parts. First: the unattended build timer had no path to a GitHub
PAT at all — `github_auth.github_token()` reads `CAIRN_GITHUB_TOKEN` purely from the process
environment, which a systemd unit never inherits from an operator's shell, and nothing in
`provision.build_service()` set `Environment=`/`EnvironmentFile=`. Then, overnight: a single
shared token wouldn't have been the right fix anyway, since a build host can serve more than
one client (`BR-CLI-022`) and different clients' private repos aren't reachable by the same
PAT — the "concrete need" `BR-BUILD-016` point 4 had deferred multi-token support against.

Two designs were weighed: redesigning `github_auth.py` around a per-client env-var naming
scheme (rejected — real code churn, and client-name sanitization becomes cairn's problem),
versus a per-client `EnvironmentFile=` on the generated systemd unit, leaving `github_auth.py`
untouched (chosen). `provision.build_service()` now emits
`EnvironmentFile=-/etc/cairn/<client>/github-token.env` — optional, one per client, never
written by cairn (`ADR-017`). `BR-BUILD-016` point 4 and `BR-CLI-023` updated. Full rationale
in `docs/adr/065-per-client-github-token-via-environmentfile-not-a-shared-token.md`.

## 2026-08-05 — `ADR-064`: build timer's `WorkingDirectory=` and script `cd` corrected; `--workdir` dropped from `cairn-build setup-timer`

Brian caught that `ADR-062`'s fix was incomplete: the rendered `.service`'s
`WorkingDirectory=` and the generated script's own `cd` line both still read
`options.workdir` — the exact `cwd`-at-invocation dependency `ADR-062` was meant to
eliminate, just in two spots the first fix missed. Both now derive from the script's own
(now durable) location instead. Once nothing in the build-timer stage read
`options.workdir` any longer, `--workdir` was dropped from `cairn-build setup-timer`
entirely, matching the precedent `cairn-registry setup` already set for dropping an unused
flag rather than keeping one that's silently ignored. `cairn-adopt setup-timer` was
confirmed unaffected — it never read `options.workdir` for its unit in the first place.
`BR-CLI-023` updated; full rationale in
`decisions/064-build-timer-workingdirectory-and-workdir-flag-both-corrected.md`.

## 2026-08-05 — `ADR-063`: registry maintenance script moves from `cwd` to `/opt/cairn-registry`

Companion review after `ADR-062`, checking `cairn-adopt`/`cairn-registry` for the same class
of bug. `cairn-adopt` was clean (fixed `cairn-reconcile` unit name is correct — one adopt host
serves exactly one deployment — and there is no generated script at all). `cairn-registry`
had the same `cwd`-dependent script bug `ADR-062` fixed in `cairn-build`:
`stage_timers_registry` wrote `registry-maintenance.sh` to `options.workdir`, defaulting to
the operator's `cwd` at invocation. No naming-collision counterpart applied — one registry
role serves one host, so the fixed `cairn-registry-maintenance` unit name was already correct.

Fix: the script now writes to `PROJECT_DIR` (`/opt/cairn-registry`), the durable,
non-user-specific directory `cairn-registry setup` already provisions for `compose.yaml`
(`ADR-053`). `BR-REG-010`/`BR-CLI-027` updated accordingly. Full rationale in
`decisions/063-registry-maintenance-script-moves-to-opt-cairn-registry.md`.

## 2026-08-05 — `ADR-062`: build-automation timer unit name and script both keyed off the manifest's client home

Raised by Brian: `cairn-build setup-timer`'s unit name, `cairn-build-<environment>`, could
collide across two different clients sharing an environment or image name — `ADR-052`,
decided the day after this naming was introduced (`ADR-047`), had already settled uniqueness
as `(client, image_name, environment)`, but the unit name was never updated to match. Second
bug: the generated build script was written to `options.workdir`, defaulting to the invoking
shell's `cwd` — typically an operator's home directory, so a retired account could silently
break build automation with nothing to do with it.

Both are now derived from the manifest's own canonical home, `/srv/cairn/<client>/`
(`ADR-047`): the unit becomes `cairn-build-<client>-<image_name>-<environment>`, the script
is written to `/srv/cairn/<client>/<unit>.sh`, and `setup-timer` hard-stops if the given
`--manifest` doesn't resolve under that layout. `BR-CLI-023` (`06-cli.md`) rewritten
accordingly. Full rationale in `decisions/062-build-timer-unit-name-and-script-key-off-the-manifests-client-home.md`.
No live migration needed — `setup-timer`'s build script has not yet run against a real host
(`W-013`).

## 2026-08-05 — `BR-BUILD-018`/`ADR-061`: a `cairn-build-owned` marker tag, `cairn-build
prune` rewritten around it, `OQ-001` resolved

Raised while working through what a VPS colocating `cairn-build`, `cairn-registry`, and
`cairn-adopt` actually shares: two independently-computed local-image GCs (today's
`cairn-build prune`, and the target-side GC `BR-DEPLOY-006`/`W-003` still describes but does
not yet implement) would share one engine image store on such a host, with neither able to
tell what the other still needs — and `cairn-build images --local` (`OQ-001`) could not tell
"cairn built this" from "cairn built this *here*," since `BR-BUILD-011`'s provenance labels
survive a `docker pull` intact.

New `BR-BUILD-018` (`docs/requirements/02-build.md`): every build additionally applies a
fixed, local-only `cairn-build-owned` tag, never pushed, stripped once that build's own tags
are successfully pushed. This makes "still owned" and "anything `cairn-adopt` could ever
depend on" provably disjoint by construction — a pulled image was, by definition, already
pushed, so it can never carry the marker.

`BR-CLI-018` (`06-cli.md`) is rewritten around it: `cairn-build prune` no longer protects by
tag-presence alone, but by "carries any tag other than the owned marker" — reaching a stale,
never-shared build it previously left alone forever, while continuing to protect anything
pushed exactly as before. `--keep` is now documented as a grace window, not rollback
headroom, since build-machine storage never carried that guarantee. `BR-CLI-005`'s `--local`
now reports the marker per image, closing `OQ-001` (`open/OPEN_QUESTIONS.md`) directly.
`BR-DEPLOY-006` (`03-deploy.md`) gets one guard ahead of its own implementation: it must
never remove a still-owned image.

Full rationale, alternatives considered (per-role rollback tags; a label instead of a tag —
rejected, labels are immutable per digest, only a tag can be stripped after the fact), and
scope in `docs/adr/061-cairn-build-owned-marker-tag-untagged-only-pruning-retired.md`.

---

## 2026-08-05 — `ADR-060`: registry `data_dir` default corrected to `/var/lib/cairn-registry`

`ADR-053` justified defaulting registry blob storage under `/opt/cairn-registry` as mirroring
FHS convention; that citation was wrong — FHS assigns `/opt` to a program's own installed
files, and `/var/lib` to a service's growing runtime state (its own canonical examples include
`/var/lib/docker`, `/var/lib/mysql`). `registry_config.py`'s `_DEFAULT_DATA_DIR` now defaults to
`/var/lib/cairn-registry`; `data_dir` remains fully operator-relocatable. `PROJECT_DIR`
(`/opt/cairn-registry`, the compose project file) is unchanged — `ADR-053`'s config/data split
still holds, only the bulk-data default moved. `docs/requirements/08-registry.md` and
`userdocs/registry/` updated to match; no migration tooling written (pre-1.0, one live
deployment, moved by hand).

---

## Archived entries

Older entries are moved out once this file grows past its word-count budget
(`.docs_check_allowlist`), by `tools/changelog_rotate.py` — each archive covers a
contiguous range, newest-first within it same as here.

- [CHANGELOG-2026-07.md](archive/CHANGELOG-2026-07.md)
- [CHANGELOG-2026-08-03.md](archive/CHANGELOG-2026-08-03.md)
- [CHANGELOG-2026-08-04-early.md](archive/CHANGELOG-2026-08-04-early.md)
- [CHANGELOG-2026-08-04.md](archive/CHANGELOG-2026-08-04.md)
- [CHANGELOG-2026-08-04-to-2026-08-05.md](archive/CHANGELOG-2026-08-04-to-2026-08-05.md)
