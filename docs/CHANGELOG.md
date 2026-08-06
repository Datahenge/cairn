# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

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

## 2026-08-04 (`reconcile` no longer assumes the base compose file is named `compose.yaml`)

Continuing the same live-VPS adopt: past the `.env` fix and the doc corrections, `cairn-adopt
examine --environment test` (run with `sudo`) succeeded cleanly against
`/opt/vps-setup/gitops/` — a hand-built deployment, one YAML file, no `overrides/` directory.
That file is named `erpnext.yaml`, not `compose.yaml`. `reconcile.py:_compose_command` hard-coded
`directory / "compose.yaml"`, so installing the printed descriptor as-is would have made the
first real `reconcile` fail (file not found) — a failure `examine` could never have caught,
since its own `docker compose ls`/`ps`/`exec` probes go through the daemon by **project name**
and never needed the literal filename at all (`adopt.py`'s own stated rationale for that
choice). Brian caught the gap before installing anything by asking `examine` to name it.

- **`descriptor.py`**: `Compose` gained a `file` field, defaulting to the new
  `DEFAULT_COMPOSE_FILE = "compose.yaml"` constant when a descriptor doesn't set it — existing
  hand-written or previously-generated descriptors keep working unchanged. `[compose] file` is
  now an accepted, validated key.
- **`reconcile.py`**: `_compose_command` now passes `directory / descriptor.compose.file`
  instead of the hard-coded literal.
- **`adopt.py`**: `Survey` gained `compose_file`, captured in `_survey_project` from the same
  `ConfigFiles` entry `directory` already comes from (`files[0]`'s basename, not just its
  parent) — `examine` no longer discards the one fact that would have mattered here. `render()`
  now always prints `file = "..."` explicitly (never silently defaulted, matching `BR-CLI-019`'s
  "report the values assumed" precedent), and the plain-text `report()`'s "Compose files" line
  now names the actual file instead of only the directory — the exact ambiguity that made this
  investigation take three round trips to pin down.
- Covered by new tests in `test_descriptor.py`, `test_adopt.py`, and `test_reconcile.py`,
  including a round-trip test using `erpnext.yaml` specifically. Full suite (751) and lint pass.
- `userdocs/reference/target-descriptor.md` and `userdocs/target/index.md` updated to document
  and demonstrate the `file` key.

---

## 2026-08-04 (`examine` crashed on an unreadable `.env`; two doc corrections)

Brian ran `cairn-adopt examine` live against an existing deployment on a client VPS and hit
`PermissionError: [Errno 13] Permission denied: '/opt/vps-setup/gitops/.env'` — a crash, not a
report.

- **Root cause**: `adopt._survey_project`'s `env_file.is_file()` check. `pathlib.Path.is_file()`
  swallows a *missing* path (`ENOENT`) but **re-raises a permission error** (`EACCES` is not in
  its ignored-error set) — confirmed by reproduction. `.env` is the one path `examine` probes
  that cairn did not create and does not own — an existing deployment's is routinely root-only —
  so this was reachable on the very first real adopt, not an edge case.
- **Fix**: wrapped the check in `try`/`except OSError`, recording a `Finding("env file", ...)`
  instead of crashing — consistent with `adopt.py`'s own stated discipline ("gaps are reported,
  never filled"), which this one call site violated. `env_file` is optional in the descriptor
  (`BR-DEPLOY-010`), so a gap here was never fatal to begin with.
  `tests/test_adopt.py::test_an_unreadable_env_file_is_a_finding_not_a_crash` covers it.
- **Two `userdocs/` corrections**, prompted by a question about how to choose `examine
  --environment`'s value: (1) `target/index.md` now explains, before the command, that
  `--environment` is an operator-chosen label matched to the build-side manifest's `[cairn]
  environment` — not detected or validated against the host, and not what selects the watched
  tag. (2) `reference/target-descriptor.md` had claimed `"production"` gates an extra
  `reconcile` confirmation; checked the code — `Descriptor.is_production` exists and is
  unit-tested but has no call site in `reconcile.py`/`cli_adopt.py`, and `reconcile` runs
  unattended with no interactive gate of any kind. Corrected to say so; the real `:production`
  gate is build-side only, at `assign-tag`/`retire` (`BR-CLI-010`).

---

## 2026-08-04 (`userdocs/target/`: the third CLI's user docs, previously unwritten)

Brian: build and push were already exercised live on a client VPS; adopt/reconcile is next.
Wrote the target-role walkthrough `userdocs/index.md` had flagged as still a placeholder.

- **`userdocs/target/index.md`** — the full walkthrough: `doctor` before a descriptor exists
  (a `FAIL`, not a warning, since `check_descriptor` has no missing-file leniency the way
  build's `check_config` does), `examine` to survey the running stack, installing the
  descriptor either by hand or via `setup` (which also takes the pre-migration backup),
  `doctor` again with the registry check now present, then `reconcile --dry-run` and a real
  pass. Calls out a real gotcha: `examine`'s emitted `tag` is whatever tag is *actually
  running*, not derived from `--environment` — installing it as-is only tracks future deploys
  if the host was already brought up against the moving environment tag.
- **`userdocs/target/automation.md`** — `setup-timer` (single host-wide timer, no
  per-environment units the way build's are), the `systemd-units`-only manual path, and the
  shared timer-verification pattern already documented for build/registry.
- `mkdocs.yml` nav gained a **Target** section; `builder/index.md`, `get-started/index.md`,
  and `userdocs/index.md` had their "not yet written" pointers to this page corrected.
- Written from `BR-DEPLOY-*`, `BR-CLI-008/019/020/021/023`, and the actual behavior in
  `cli_adopt.py`/`adopt.py`/`reconcile.py`/`systemd.py`/`provision.py` — not yet run against a
  real target, same caveat `registry/index.md` already carries.

---

## 2026-08-04 (docs_check.py's word-count ceiling recalibrated; archived early 2026-08-04 entries)

Two related housekeeping items:

- **DOC002 default recalibrated** (`ADR-055`): `DEFAULT_MAX_WORDS` 1800 → 2200 — the old
  default drew the line through the middle of the project's normal doc sizes, not around its
  actual outliers, and was being "fixed" by repeated same-day `.docs_check_allowlist` bumps
  instead. `06-cli.md`'s override raised 3150 → 4000 with a named ~4500-word split point;
  `02-build.md`'s override dropped (clears the new default unaided).
- **This file archived again**: adding the entry above would have tripped this file's own
  2000-word ceiling, which had no headroom left. Archived the six oldest 2026-08-04 entries
  (`cairn-build setup`'s engine-detection fix through `CONFIGURATION.md`'s retirement)
  verbatim to [`docs/archive/CHANGELOG-2026-08-04-early.md`](archive/CHANGELOG-2026-08-04-early.md),
  same pattern as the earlier `CHANGELOG-2026-07.md`/`CHANGELOG-2026-08-03.md` passes.

---

## 2026-08-04 (later — `BR-CLI-003`: push now invokes `--quiet`)

Brian ran `cairn-build push` and saw raw engine per-layer output twice — once per tag
(`BR-BUILD-008` pushes both, deliberately) — the second showing "Layer already exists" per
layer. Correct, but noise a newcomer reads as an error.

- **`BR-CLI-003`** gained a clause: `push.push()` now invokes `--quiet`, suppressing
  per-layer progress at cairn's floors (Docker v23+, podman v4+) — verified it doesn't
  suppress errors/exit codes there (docker/cli#2284, fixed in 20.10.0). cairn's own
  `Pushing …`/`Pushed …` framing already names the
  reference; the digest was already reported, once, after the build (`BR-BUILD-011`).
- `BR-BUILD-008`'s dual-tag push is unchanged — that behavior is correct.

---

## 2026-08-04 (`BR-BUILD-016` extended: missing-token hint on a failed private-app lookup)

Brian hit a failed `cairn-build build` against a private `github.com` app and, reading only
git's own `ls-remote` failure ("could not read Username for 'https://github.com'"), suspected a
URL-construction bug. Root cause was operator error — the wrong environment variable was set —
but git's wording names the symptom, not the fix, and led straight to a wrong diagnosis.

- **`BR-BUILD-016` gained a 5th point.** When a `github.com` `ls-remote` fails and no
  `$CAIRN_GITHUB_TOKEN` is configured, cairn's error now also names the missing variable as a
  candidate fix, alongside git's own failure line. Scoped to exactly the same host/scheme
  `authenticated()` already uses (`github_auth.targets_github`, factored out of
  `authenticated()` for this).
- No change to the URL-construction itself (`token@host`, no separate username) — verified
  correct and already the documented/tested form; the earlier `terminal prompts disabled` error
  was simply the token never reaching `authenticated()` because the wrong env var was set.

---

## 2026-08-04 (`ABOUT_GHCR.md`/`ABOUT_REGISTRIES.md` retired; migrated to `userdocs/`)

Resolves `DOCS-01` (promoted to `ADR-054`). Retired, not rewritten — same precedent as
`CONFIGURATION.md`'s retirement earlier the same day. Content re-verified against source:

- `docs/technical/ABOUT_REGISTRIES.md` → `userdocs/registry/choosing-a-registry.md`.
- `docs/technical/ABOUT_GHCR.md` → `userdocs/registry/{ghcr-setup,ghcr-ownership-and-cost,
  ghcr-tags-and-troubleshooting}.md`, per `DOCS-01`'s pre-approved topic split.

Inbound references repointed rather than left as stubs (`mkdocs.yml`, the documentation
authority map, `AGENTS.md`, requirements, ADRs, and every `userdocs/**` page that linked out to
the old files). `README.md`'s two registry sections were also consolidated into one, since
their content now duplicated the published pages (`BR-DOCS-007`). Detail: `open/OPEN_DECISIONS.md`
(row removed), `decisions/054-ghcr-and-registry-choice-docs-migrated-to-userdocs.md`.

---

## 2026-08-04 (later — `ADR-053` captures the registry's `/etc`/`/opt` split; archived 2026-08-03 to `docs/archive/`)

Two housekeeping items, requested together:

- **New `ADR-053`** (`decisions/`, lightweight): formally records the rationale behind
  `cairn-registry`'s two directories — `/etc/cairn` for config/secrets (low-churn, shared,
  mirrors every other role), `/opt/cairn-registry` for the compose project and relocatable
  bulk data — reaffirming a layout `registry_provision.py` already implements but had no
  decision record for, raised when Brian asked whether the split was worth keeping. `BR-REG`'s
  cited-decisions line updated to include it.
- **Archived 2026-08-03** to
  [`docs/archive/CHANGELOG-2026-08-03.md`](archive/CHANGELOG-2026-08-03.md), same pattern as
  the earlier July archive — this file was approaching its word-count sprawl limit again.

---

## 2026-08-04 (`cairn-registry setup` scaffolds a starter config and verifies itself with doctor)

Follow-up from the first real `cairn-registry setup --dry-run` (`W-015`) — see the
`05-implementation-index.md` Registry row for the dry-run-contract bugs found the same day.
Two new requirements, both detailed in `08-registry.md`: `BR-REG-002a` — `setup` scaffolds a
starter `/etc/cairn/registry.toml` the first time none exists, never touched again once
present (mirrors `cairn-build setup`'s starter manifest, `BR-CLI-022`); confirmed with Brian
the shipped default stays `port = 5000`, not the `5001` copied from an earlier illustrative
example. `BR-REG-003a` — a real full `setup` run (or `--only registry`) now finishes by running
`doctor` and adopting its exit code. `BR-REG-003` also now notes `setup` takes no `--workdir`.
No ADR recorded for the `/etc/cairn` vs `/opt/cairn-registry` split Brian also asked about —
reaffirmed, but the rationale was never written down; open item if he wants it captured.

---

## 2026-08-04 (`cairn-build prune` gains automation, via the build script not a new timer)

Same discussion as the env-tag rename (next entry): `cairn-build prune` (local build-machine
image cleanup) has no automation, unlike `cairn-registry`'s prune+gc timer. Decided against a
parallel timer (`ADR-051`) — local cruft only ever exists because this machine's own build
script just ran, so there's no independent cadence for a separate timer to hook. `prune --keep 1
--yes` becomes a fourth step in the same generated script `setup-timer` writes. `BR-CLI-023`
updated to name it. Tracked as `W-018`, alongside `W-017` since both touch the same script.

---

## 2026-08-04 (env-tag rename and `new-tag`/`retag` merge)

Raised while reviewing the Builder user docs' "Next steps" section for clarity: Brian found
`[cairn.environments]` and the `new-tag`/`retag` split both confusing, and asked for a rename
and a possible command merge rather than just clearer prose around the existing names.

Checked both against the actual implementation before deciding, per the working agreement's
"ask, don't guess" rule for anything code-shaped:

- **`[cairn.environments]` → `[cairn.declared_environments]`** (`ADR-049`, amends `ADR-033`).
  The table only declares which environment names are legal — nothing happens automatically
  when a row is added — and the old name read as if it did. `declared_environments` reuses
  vocabulary the requirements already use everywhere for this table. Declined Brian's own
  alternative, `[cairn.allowable_environment_tag_names]`: accurate, but undersells that each row
  is a `name = "tag"` mapping, not just a list of tag names, and is long to hand-type.
- **`new-tag` + `retag` → `assign-tag`** (`ADR-050`). Tracing `_pointer_move` in `cli_build.py`
  showed the two verbs differ on exactly one axis — whether the registry pointer already exists
  — while the axis Brian's stated rationale described (declared-name legality) is already
  enforced identically by both. Found a concrete cost of the split while tracing this:
  `setup-timer`'s script calls `retag --yes` on every run, which fails on the first automated
  run against a brand-new environment because the pointer doesn't exist yet — an undocumented
  manual `new-tag` was required first. `assign-tag` creates or moves, reports which, and keeps
  the `:production` confirmation gate for both (tightening `BR-CLI-010`, which previously said
  only "moves or retires" though the code already gated creation too).

`BR-CLI-004/009/010`, `BR-DEPLOY-009/009a`, `BR-BUILD-002`, and `BR-REG-001` updated to match.
Requirements and decision records only — `environments.py`, `cli_build.py`, tests, `README.md`,
and `userdocs/` still describe the current, shipped surface and update in a separate, code-paired
pass (`open/OPEN_WORK.md`).

---

## 2026-08-04 (later still — `cairn-build doctor` gains a free-disk/memory check)

`userdocs/builder/index.md` claimed `cairn-build doctor` already named the local image
store's disk headroom "as part of their disk-space check" — a user ran `doctor` and found
no such line. Traced to `BR-CLI-007`: the requirement, and `doctor.py`'s implementation,
only ever specified this for `cairn-build setup`'s preflight (`setup_runner.py`); `doctor`
never had it. Not a regression — the docs described a check that was never built. Checked
whether this was a stable-vs-dev version mismatch instead (local `pyproject.toml` and the
latest PyPI release both sit at `0.2.1`, and `doctor.py`'s git history shows the check was
never present at any point) — ruled out.

Brian confirmed a preference for `doctor` actually having the check rather than the docs
being walked back, and chose to add both free disk and available memory (setup's preflight
bundles them together; a memory-starved box is as unbuildable as a full one). `BR-CLI-007`
updated to list them for `cairn-build doctor`; `doctor.py` gained `check_disk`/
`check_memory`, reusing `setup_runner.MINIMUM_DISK_GB`/`MINIMUM_MEMORY_GB`/
`read_available_memory_gb` rather than duplicating the thresholds. Along the way, `doctor`'s
own disk-root lookup was made podman-aware (`podman info --format '{{.Store.GraphRoot}}'`)
where `setup`'s data-dir lookup remains docker-only — a pre-existing, separate gap, flagged
to Brian but not fixed here since it wasn't what was asked. `userdocs/builder/index.md`'s
`doctor` example output updated (9 checks → 11).

---

Entries from 2026-08-03 are archived at
[`docs/archive/CHANGELOG-2026-08-03.md`](archive/CHANGELOG-2026-08-03.md). Entries from
2026-07-21 through 2026-07-27 are archived at
[`docs/archive/CHANGELOG-2026-07.md`](archive/CHANGELOG-2026-07.md). Earlier 2026-08-04
entries are archived at
[`docs/archive/CHANGELOG-2026-08-04-early.md`](archive/CHANGELOG-2026-08-04-early.md).
