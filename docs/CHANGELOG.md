# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

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

## 2026-08-05 — correction: `cairn-registry setup` was already verified live 2026-08-04; `W-015` narrowed

`docs/technical/05-implementation-index.md`'s Registry row and `open/OPEN_WORK.md`'s `W-015`
both understated progress already made: a real (non-`--dry-run`) `cairn-registry setup` had
already completed cleanly against the client's test VPS on 2026-08-04, alongside that day's
`--dry-run` pass that found and fixed the two dry-run-contract bugs — the index's own prose
already described both, but its "Known Next Gap" cell and `W-015`'s own description still
read as if the real run hadn't happened. Corrected per Brian, 2026-08-05.

- **`docs/technical/05-implementation-index.md`** — Registry row's "Known Next Gap" narrowed
  from "first real-host `setup` run past `--dry-run`, and first `prune`/`gc` run" to just the
  `prune`/`gc` half.
- **`open/OPEN_WORK.md`** — `W-015`'s description rewritten to state plainly that
  implementation and live `setup` verification are both done; only `prune`/`gc` against a
  real registry remain.
- **`CURRENT_CONTEXT.md`** — "Active work" line updated to match.

## 2026-08-05 (`BR-DEPLOY-003b`: convergence verified against the running container, `W-022` closed)

`W-022`, found live the same day (fork-pressure register item 4, `ADR-021`): a target whose
compose file hardcoded `image:` per service, rather than parameterizing it with
`${CUSTOM_IMAGE}`/`${CUSTOM_TAG}`, let `reconcile` report `Converged` while every
erpnext-app container kept running the old image — `running_digest()` only asked the local
image store whether a matching image existed, never what the running container was actually
using.

- **`docs/requirements/03-deploy.md`** — new `BR-DEPLOY-003b`: convergence MUST be
  determined by reading the digest off the **running** `backend` container's own image, not
  merely whether a matching image exists in the local store; a mismatch MUST be treated as
  a convergence failure (`BR-DEPLOY-018`), not a silent `Converged`. Allowlist ceiling for
  the file bumped 2450 → 2600 to fit it (`.docs_check_allowlist`).
- **`src/cairn/reconcile.py`** — `running_digest()` rewritten: `compose ps -q backend` →
  `docker inspect <container> --format {{.Image}}` → `docker image inspect <image>
  --format {{json .RepoDigests}}`, instead of inspecting `descriptor.reference` directly
  against the local store. `tests/test_reconcile.py` updated and extended, including a
  regression test for the exact live failure (a stale container reporting its own older
  digest, not whatever else the store holds).
- **`open/OPEN_WORK.md`** — `W-022` swept to `docs/archive/OPEN_WORK-done.md`.
  **`docs/technical/05-implementation-index.md`** — Reconcile/deploy row's status changed
  from "Verified live (with a caveat)" to "Verified live."

## 2026-08-05 (`ADR-059` code migration: `W-023`..`W-031` landed)

The deferred code migration from the entry below landed same-day: `src/cairn/vendored/` is
now `src/cairn/recipe/`, and every ventwig-era code path it depended on is gone.

- **`src/cairn/vendor.py`** — trimmed to `assert_build_inputs` (`BR-VEND-003`) plus the
  Containerfile-reading helpers it needs; `status`/`sync`/`_refresh_pin_file`/`read_pin`/
  `_tree_hash`/`assert_clean`/`assert_no_nested_git` all removed. New `recipe_commit()`
  reads cairn's own git history for `BR-BUILD-011` provenance, degrading to `""` in an
  installed wheel (no `.git`).
- **`src/cairn/project.py`** — deleted entirely; **`src/cairn/errors.py`** —
  `ProjectRootNotFoundError`/`VendorToolError`/`VendorDriftError` removed as unused.
- **`src/cairn/cli_build.py`** — the `vendor` Typer sub-app, `_run_in_project`, and the
  `find_project_root` import are gone; help text and step messages reworded.
- **`src/cairn/build.py`** — `plan()` drops the `assert_clean`/`assert_no_nested_git`
  calls; `provenance_labels()` stamps `com.datahenge.cairn.frappe-docker.ref`/`.commit`
  from cairn's own `__version__` and `vendor.recipe_commit()` instead of a
  `frappe_docker.pin.toml` read. **`src/cairn/images.py`** follows suit — `vendor_pin`
  became `recipe_commit`, and the local/registry reports now print "built from recipe
  `<commit>`" instead of "built with vendored base `<ref>`".
- **`src/cairn/doctor.py`** — the `vendored tree`/`vendor .git` guards are gone; `build
  inputs` stays.
- **`pyproject.toml`** — `[tool.ventwig]` and the `ventwig` dev dependency removed; the
  `description` field and the ruff `extend-exclude` path updated to match.
- Tests updated alongside each change (`test_vendor.py` rewritten, `test_project.py`
  deleted, `test_build.py`/`test_doctor.py`/`test_cli_build.py`/`test_images.py`/
  `test_timing.py`/`test_cli_adopt.py` adjusted); `tools/docs_check.py`'s hardcoded
  exclusion path fixed (found stale by its own check); `userdocs/index.md`,
  `userdocs/reference/index.md`, and `userdocs/builder/index.md` swept of the `ventwig`/
  `vendor status|sync` walkthrough and the `(ADR-001)` ID leak.
- **`open/OPEN_WORK.md`** — `W-023`..`W-031` swept to
  `docs/archive/OPEN_WORK-done.md`. **`docs/technical/05-implementation-index.md`** — the
  Owned Docker recipe row updated from "code migration pending" to `Implemented`.

## 2026-08-05 (`ADR-059`: cairn owns its Docker build recipe; frappe_docker vendoring retired)

Working through the fork-pressure register's item 4 (below) with Brian surfaced a bigger
question than forking `frappe_docker`: since `cairn-adopt reconcile` never composes against
cairn's own vendored copy at deploy time (it reads the compose directory/filename off the
*target's* descriptor — `descriptor.py`'s `Compose.directory`/`Compose.file`), and since
`BR-DEPLOY-007` already scopes cairn to existing environments only, cairn will always face a
pre-existing compose file regardless. The vendored `compose.yaml` inside cairn's own repo
serves no purpose there. Combined with a direct read of `images/custom/Containerfile`
(~130 lines, one Debian base, six version `ARG`s — smaller and more legible than assumed) and
the observation that `BR-VEND-009` already made upstream delivery to a real VPS a deliberate,
manual act (never automatic), the conclusion reached was: **own the recipe outright, rather
than fork-and-still-track-upstream.**

- **`docs/adr/059-...md`** (new, authoritative) — decision record: cairn owns its Docker
  build recipe and compose YAML permanently, at `src/cairn/recipe/frappe_docker/` (renamed
  from `src/cairn/vendored/`), bootstrapped as a byte-for-byte copy. No `ventwig`, no pin, no
  drift check, no sync obligation — upstream `frappe_docker` becomes an informal, at-will
  reference. Supersedes `ADR-001` (wrap, never modify) and `ADR-007` (vendoring via ventwig);
  resolves `ADR-020` (ventwig pin immutability — moot) and `ADR-021` (fork escape hatch —
  superseded, ownership grants everything a fork would without forking). All four archived
  to `docs/archive/` with forwarding stubs left in place.
- **`docs/00-project-scope.md`** — Purpose, "Is not," and guiding-principle prose rewritten:
  "Never own what we don't own" becomes "Own what we depend on."
- **`docs/requirements/01-vendoring.md`** — full rewrite. The ten `BR-VEND-001..010`
  (ventwig mechanism, tag pin, lock anchor, read-only, drift hard-stop, build-input
  completeness, no upstream `.git`, no package markers, deliberate-upgrades-only, git working
  tree) replaced by four ownership-era requirements: recipe ownership, no tracking obligation,
  build-input completeness (kept, reframed), no nested VCS metadata.
- **`docs/requirements/02-build.md`, `06-cli.md`** — `BR-BUILD-009`/`011`/`013` reworded for
  ownership (provenance labels now stamp the recipe's own git commit/cairn version, not a
  `frappe_docker.pin.toml` upstream pin); `BR-CLI-006` (`vendor status`/`sync`) struck — no
  replacement command ships.
- **`AGENTS.md`, `CURRENT_CONTEXT.md`** — `VEND` area glossary redefined from "vendoring" to
  "the owned Docker build recipe"; artifacts table and Standing Rules updated to the new path.
- Citation touch-ups in `docs/adr/015-...md`, `018-...md`, `029-...md`, `030-...md`,
  `044-...md`, `046-...md`, and `decisions/008-...md` where they referenced the retired
  vendoring model, plus `docs/technical/05-implementation-index.md`'s Vendoring row.
- **`open/OPEN_DECISIONS.md`** — `ADR-020`/`ADR-021` rows removed (resolved). **`open/OPEN_WORK.md`**
  — `W-010` closed (superseded); `W-023`..`W-031` added for the deferred **code** migration
  (renaming `src/cairn/vendored/` → `src/cairn/recipe/`, retiring `vendor.py`/`project.py`/the
  `vendor` CLI sub-app, redesigning `build.py`'s provenance labels, updating tests, fixing a
  pre-existing `(ADR-001)` ID leak in `userdocs/builder/index.md`) — **not executed this pass**,
  per this project's own documentation-precedes-code discipline. Code still lives at the old
  vendored/ventwig paths until that work lands.

## 2026-08-05 (first real target converged; fork-pressure register item 4; `W-001`/`W-002` closed)

The client VPS adopt reached the finish line: `cairn-adopt reconcile` ran against a real target
for the first time ever, and — after one genuine surprise — the site is now actually running the
client's own build, not the pre-existing public image.

- **The surprise:** `reconcile` reported `Converged`, but nothing had changed. The target's
  existing compose file (deployed from something structurally identical to frappe_docker's
  `pwd.yml` quick-start, not its `compose.yaml`) hardcoded the image on every service — no
  `${CUSTOM_IMAGE}`/`${CUSTOM_TAG}` anywhere. `reconcile.running_digest()` only confirms a local
  image exists under the desired tag, not that any container is running it, so the false
  convergence went unnoticed until checked by hand (`docker inspect` vs. the pulled digest).
  Recorded as fork-pressure register item 4 (`docs/adr/021-...md`) and as `W-022` (`reconcile`'s
  own robustness gap, independent of the fork question).
- **The fix, on the client's side:** the compose file's hardcoded `frappe/erpnext:v16.26.1`
  replaced with `${CUSTOM_IMAGE:-frappe/erpnext}:${CUSTOM_TAG:-v16.26.1}` per service (matching
  frappe_docker's own `compose.yaml` convention); a one-time manual `compose up`/`migrate`
  (bypassing `reconcile`'s now-satisfied short-circuit) brought `backend`'s actual running image
  ID to match the desired digest — confirmed by `docker inspect`. A subsequent real
  `cairn-adopt reconcile` correctly reported `Already running`.
- **`W-001`/`W-002` closed** in `open/OPEN_WORK.md` — first live deployment sequence and
  `cairn-adopt doctor`'s target-role checks both verified against real infrastructure.
  `docs/technical/05-implementation-index.md`'s Reconcile/deploy, Examine, and Doctor rows
  updated with completion judgments, including the caveat.
- **`W-007` closed** — `USAGE.md` was never written; superseded by the published user-facing
  docs on GitHub Pages (`userdocs/` → `https://datahenge.github.io/cairn/`, `ADR-045`), which
  already cover installation and per-role walkthroughs. `README.md`'s "How to use" section
  trimmed to match: the inline target walkthrough (stale — it predated `userdocs/target/`)
  replaced with a one-line pointer to the published [Target](https://datahenge.github.io/cairn/target/)
  walkthrough, matching how Builder and Registry already link out instead of duplicating.

---

## 2026-08-04 (`registry_host` made required; `"docker.io"` names Docker Hub, `ADR-058`)

Same thread, hours later: Brian asked whether `ADR-057`'s reasoning for making `registry_host`
optional ("no value would exist for Docker Hub") was actually true. It wasn't — `registry.py`
already had `_DOCKER_HUB_NAMES = frozenset({"docker.io", "index.docker.io"})`, unrelated to this
session, recognizing exactly this. `docker.io` is the canonical name, and precisely what `docker`
itself normalizes a hostless reference to.

- **`ADR-058`** supersedes `ADR-057` the same day — `Descriptor.registry_host` changes from
  `str | None = None` to `str` (required, same as `image`/`tag`/`site`); `registry.split_host()`'s
  hostless fallback changes from `(None, base)` to `("docker.io", base)`; `render()` prints
  `registry_host` unconditionally instead of only when present. `ADR-057` archived in full to
  `docs/archive/057-...md`, forwarding stub left at its original `decisions/` path, matching this
  project's established same-day-supersession pattern (`ADR-049`/`050` → `ADR-052`).
- Every fixture across `test_descriptor.py`, `test_adopt.py`, `test_reconcile.py`,
  `test_provision.py`, `test_doctor.py`, `test_cli_adopt.py`, `test_registry.py` that built a
  `Descriptor`/`Survey`/minimal TOML without `registry_host` updated to include it — the schema
  tightening surfaced every place a test had been implicitly relying on the old default.
  `userdocs/reference/target-descriptor.md` and `userdocs/target/index.md` updated to match.
  Full suite (774) + lint + docs-check + `mkdocs build --strict` all pass.

---

## 2026-08-04 (target descriptor splits `registry_host` from `image`, `ADR-057`, superseded)

Same live-VPS thread: fixing `cairn-registry images`'s missing host (previous entry) prompted
Brian to ask why the descriptor's `image` field was a combined `<host>/<repo>` string at all —
"a key named `image` that's actually 2 things combined into one" — rather than a separate field,
the way the manifest's own `[cairn.registry] host` already is.

- **`descriptor.py`**: `Descriptor` gains `registry_host: str | None = None`. `image` now holds
  the repository path alone. New `repository` property (`registry_host/image`, or `image` alone
  if absent) and `reference` now built from it. Optional, not required — mirroring the
  manifest's own optional `registry` — because a hostless reference is a real case this exact
  session already hit: a pre-cairn deployment running the public `frappe/erpnext:v16.26.1`,
  which genuinely names no host. Requiring one would force a fabricated value onto a fact.
- **`registry.py`**: new `split_host()`, `parse_ref`'s lenient sibling — same host-detection
  heuristic (factored into `_looks_like_host`), but a missing host isn't an error, since this is
  recording what's actually running, not asserting where cairn should push or pull.
- **`adopt.py`**: `Survey.registry_host`, populated by `_survey_image` via `split_host`;
  `render()` prints `registry_host` (when present) and realigned every top-level key to match;
  `report()`'s "Running image" line reassembles the split for display.
- **`reconcile.py`**: `CUSTOM_IMAGE` and the `RepoDigests` match now use `descriptor.repository`
  instead of the bare `.image`, since those need the full pull reference either way.
- **`cairn-registry images`, same session**: repository line split too — `Registry <host>`
  printed once, `Repository <name>` per line, instead of one glued string repeated per
  repository (the shape that made the host easy to miss copying by hand in the first place).
- Backward compatible: an existing descriptor with `registry_host` absent and a full
  `host/namespace/name` string in `image` behaves exactly as before. No live client has
  installed one yet (`open/OPEN_WORK.md`), so this is a clean addition, not a migration.
- New tests across `test_descriptor.py`, `test_adopt.py`, `test_reconcile.py`,
  `test_registry.py`, `test_cli_registry.py`; `userdocs/reference/target-descriptor.md` and
  `userdocs/target/index.md` updated. Full suite (770) + lint pass.

---

## 2026-08-04 (`cairn-registry images`'s repository line was still not copy-pasteable)

Immediate real-world fallout from the previous entry's fix: Brian used `cairn-registry images`
to find the value for a target descriptor's `image`, hand-copied the repository line
(`lifescientific/erpnext-v16`), and `cairn-adopt doctor`'s registry check failed —
`registry.parse_ref` refuses a reference with no registry host, and the printed line never had
one. The grouping fix labeled the line `Repository <name>`, but *name* was always the bare
repository, never `config.host/<name>` — the exact string a descriptor's `image` field needs.

- `images_command` now prints `Repository {base.base}` — the full `<host>/<repository>`
  reference, via `ImageRef.base`, which already existed and was simply unused here. `--json` is
  untouched (`registry` and `name` are already separate, structured fields there; a scripting
  consumer joins them itself rather than needing a third, pre-joined string).
  `userdocs/registry/cli.md`'s example updated to show a host in the repository line. New test
  `test_the_repository_line_is_the_full_copy_pasteable_reference`; full suite + lint pass.

---

## 2026-08-04 (`cairn-registry images` grouped by digest, not one row per tag; `.docs_check_allowlist` fix, `ADR-056`)

Two unrelated items, same session.

- **`BR-REG-005`**: Brian, still mid-adopt, reached for `cairn-registry images` to find the
  right `image`/`tag` for the target descriptor and found the output unlabeled — a bare
  repository name, unheaded tag/digest columns — and structured one row per tag, so three tags
  sharing a build (a content-hash tag, `latest`, and any environment pointer) repeated the same
  digest three times instead of appearing together. Restructured to group by digest: a
  `Repository <name>` header, a `DIGEST`/`TAGS` column header, and one row per unique digest
  listing every tag that names it. `--json`'s shape changed to match (`images: [{digest, tags}]`
  replacing the flat `tags: [{tag, digest}]`) — the full, untruncated digest, since `--json` is
  for scripting and needs precision the human-readable short digest doesn't. `_grouped_tags()`
  is the new shared helper both output paths call. `BR-REG-005` updated to require the grouping.
  `userdocs/registry/cli.md` and `userdocs/target/index.md` (the `image`/`tag` gotcha, now also
  covering the "running a pre-cairn public image" case found earlier this session) updated and
  cross-linked. New tests in `test_cli_registry.py`; full suite + lint pass.
- **`.docs_check_allowlist`** (`ADR-056`): this file's own 2000-word override — dropped that
  low the same day specifically to force frequent archiving — re-tripped within hours,
  mid-session, forcing an archive pass that interrupts the work generating the entries. Tripled
  to 6000 per Brian; no archiving performed, next pass happens on its own schedule.

---

## Archived entries

Older entries are moved out once this file grows past its word-count budget
(`.docs_check_allowlist`), by `tools/changelog_rotate.py` — each archive covers a
contiguous range, newest-first within it same as here.

- [CHANGELOG-2026-07.md](archive/CHANGELOG-2026-07.md)
- [CHANGELOG-2026-08-03.md](archive/CHANGELOG-2026-08-03.md)
- [CHANGELOG-2026-08-04-early.md](archive/CHANGELOG-2026-08-04-early.md)
- [CHANGELOG-2026-08-04.md](archive/CHANGELOG-2026-08-04.md)
