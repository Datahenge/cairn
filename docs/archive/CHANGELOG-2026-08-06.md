---
status: archived
owner: technical
purpose: Archived tail of docs/CHANGELOG.md — entries from 2026-08-06 (1 entries).
---

# Changelog archive — 2026-08-06

Relocated from `docs/CHANGELOG.md` on 2026-08-18 to keep that file under its word-count
budget (`.docs_check_allowlist`), by `tools/changelog_rotate.py`. Content only — nothing
rewritten, nothing summarized. `docs/CHANGELOG.md` carries current entries; this file is
historical-only per `docs/archive/README.md`.

## Index

- 2026-08-06 (`images` splits by role: `cairn-build` local-only, `cairn-registry` gains `--host`/`--namespace`/`--image`)

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
