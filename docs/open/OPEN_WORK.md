---
status: active
owner: project
purpose: Central backlog for implementation and cleanup work that is not blocked on a pending decision.
---

# Open Work

Source-controlled backlog for unfinished implementation, cleanup, and operating work. Work that
cannot proceed until Brian chooses between options belongs in
[OPEN_DECISIONS.md](OPEN_DECISIONS.md) instead. Current system state by area lives in
[../technical/05-implementation-index.md](../technical/05-implementation-index.md);
this file tracks the discrete tasks that get you there. Seeded 2026-08-03 from
[../archive/next-steps.md](../archive/next-steps.md).

## Status Values

| Status | Meaning |
| --- | --- |
| `open` | Work remains and is not currently blocked. |
| `blocked` | Work cannot proceed until a named decision, dependency, or condition resolves. |
| `in_progress` | Work has started and should be completed or deliberately paused. |
| `done` | The behavior is specified in its owner doc, code cites the relevant `BR-*` identifier, tests cover it, lint/type checks pass, and a completion judgment has been recorded in `docs/technical/05-implementation-index.md`'s `Completion Judgment` column. `docs/CHANGELOG.md` is updated. |
| `deferred` | Intentionally not part of the current scope. |

Sweep `done` rows out on the next cleanup pass — but only after the completion judgment is
recorded in the implementation index. This file tracks what's outstanding, not a permanent
record of everything ever finished; swept rows move to
[../archive/OPEN_WORK-done.md](../archive/OPEN_WORK-done.md).

## Backlog

| ID | Status | Area | Work | Notes / Links |
| --- | --- | --- | --- | --- |
| `W-003` | `in_progress` | `DEPLOY` | `BR-DEPLOY-006`/`BR-CLI-028` — `cairn-adopt prune`: reclaim `cairn-adopt-owned` images (`BR-DEPLOY-023`), keeping the currently-running image plus the newest `--keep <n>`. Never touch volumes/containers; never remove an image still carrying `cairn-build-owned` (`BR-BUILD-018`, `ADR-061`). Landed and unit-tested 2026-08-08 (`ADR-072`); remaining: a real run against a live target | `src/cairn/adopt_prune.py`, `src/cairn/reconcile.py`, `src/cairn/cli_adopt.py`; `docs/archive/next-steps.md` §4a |
| `W-004` | `open` | `DEPLOY` | `BR-DEPLOY-020` — optional failure webhook; opt-in, best-effort, must never crash `reconcile` or alter deploy behavior | `docs/archive/next-steps.md` §4a |
| `W-005` | `deferred` | `BUILD` | Registry-backed build cache (`--cache-to`/`--cache-from`) — helps a cold CI runner, not a warm local rebuild; weaker on podman | `docs/archive/next-steps.md` §5; not yet a requirement |
| `W-006` | `open` | (testing) | Decide whether to add a `--cov-fail-under` coverage floor, given `--cov` in `addopts` would break a plain `pytest` run without the plugin installed | `docs/archive/next-steps.md` §5 |
| `W-008` | `deferred` | `DEPLOY` | Dedicated service account for `reconcile` instead of `root` — needs `docker` group membership regardless, so the security delta is smaller than it looks; document as a hardening option, not a default | `docs/archive/next-steps.md` §5 |
| `W-009` | `blocked` | `BUILD` | `BR-BUILD-017` — local git mirror for private-app reachability | Blocked on `ADR-044` (`docs/open/OPEN_DECISIONS.md`); full plan in `docs/plans/git-mirror-private-apps.md` |
| `W-013` | `in_progress` | `CLI` | Verify `BR-CLI-022`/`BR-CLI-023` (`ADR-047`) against a real VPS — code and tests landed 2026-08-03 | `src/cairn/provision.py`, `src/cairn/doctor.py`, `src/cairn/cli_build.py`/`cli_adopt.py`. **2026-08-04**: verified live on a client VPS — `cairn-build doctor` (9/9 checks), `--dry-run`, then a real `cairn-build build` (5m15s, no `--push`). **2026-08-06**: first live `setup-timer` run, against Life Scientific's test VPS — correctly refused on a private repo with no `github-token.env` yet, but Brian flagged the output as noisy and self-contradicting; fixed (see `docs/CHANGELOG.md`). Remaining: `setup-timer`'s happy path (a working token file, or a public-only manifest) and `doctor`'s known-manifests listing still unexercised; picks up from `W-001`'s push → `new-tag` → `reconcile` sequence next |
| `W-015` | `in_progress` | `REG` | `cairn-registry` (`ADR-048`, `docs/requirements/08-registry.md`) is fully implemented and unit-tested; a real (non-`--dry-run`) `cairn-registry setup` completed cleanly on the client's test VPS 2026-08-04, so provisioning is verified live. Remaining: a first real `prune` run and a first real `gc` run against a live registry with real pushed images | `src/cairn/registry_retention.py`, `src/cairn/cli_registry.py`; **separate from `W-003`**, which is target-side local-disk GC (`BR-DEPLOY-006`) — do not conflate the two |
| `W-020` | `open` | `BUILD` | Discuss with Claude: a `systemd` timer for build-side cleanup (analogous to `cairn-build prune`/`setup-timer`), scoped correctly against `HOME` directories and the per-client-environment namespace under `/srv/cairn/` (`ADR-047`) — not yet a requirement, needs scoping first | Raised by Brian 2026-08-04; relates to existing `systemd.py`/`setup_runner.py` timer machinery — do not conflate with `W-003` (target-side image GC) |
| `W-032` | `open` | `DEPLOY` | Design and build a "provision a new environment" path using cairn's owned `compose.yaml`/`overrides/*.yaml` (`src/cairn/recipe/`) — stands up the Compose stack on a target that has nothing running yet. Does NOT create sites/DBs (`BR-DEPLOY-007` unchanged). Needs a design pass first: CLI surface, and how it hands off to the existing `examine`/`setup` flow once the stack exists | `ADR-068`; recipe trim landed 2026-08-06 |
| `W-033` | `open` | `DEPLOY` | Design `cairn-adopt`'s take-ownership path: converge an already-adopted, hand-built deployment's compose configuration onto cairn's own owned files, rather than reading its arbitrary directory/filename indefinitely the way `examine`/`reconcile` do today. Needs a design pass on migration safety (a live site mid-conversion) before any code | `ADR-068`. **Live instance identified 2026-08-18**: Life Scientific's test VPS runs a `pwd.yml`-descended file at `/opt/vps-setup/gitops/erpnext.yaml`, authored by the client for a disposable demo before cairn existed, surrounded by orphaned client tooling cairn superseded but never displaced. See `ADR-073` |
| `W-035` | `blocked` | `DEPLOY` / `CLI` | Give the target stack a lifecycle an operator can actually use: an "intentionally down" state `reconcile` honours instead of converging (today `State.is_converged` requires `stack_up`, so the timer resurrects a deliberately-stopped stack and runs `bench migrate`), and the commands that set/clear it. Needs a design pass — see the ADR for the two candidate shapes | Blocked on `ADR-073` (`docs/open/OPEN_DECISIONS.md`). Raised by Brian 2026-08-18 after a Compose YAML config change on a client VPS had no supported stop/start path. Touches `src/cairn/reconcile.py`, `src/cairn/cli_adopt.py`, `src/cairn/doctor.py` |
| `W-036` | `open` | `VEND` | cairn's owned recipe silently falls back to another vendor's image: `src/cairn/recipe/compose.yaml:5` and `overrides/compose.migrator.yaml:9` both carry `${CUSTOM_IMAGE:-frappe/erpnext}:${CUSTOM_TAG:-$ERPNEXT_VERSION}`, and `example.env` ships `ERPNEXT_VERSION`, so an unset `CUSTOM_IMAGE` resolves to stock `frappe/erpnext` with no warning (a `:-` default suppresses Compose's unset-variable message). Inherited byte-for-byte from `frappe_docker`, but `ADR-059` made cairn the owner, so it is cairn's to fix. **The exact form needs Brian's call** — drop the default outright so it fails loudly, or keep a default and have `reconcile`/`doctor` detect the substitution | Found 2026-08-18 while tracing `ADR-073`; `W-032` would propagate this to every newly-provisioned host. Live instance: Life Scientific's test VPS, via its own `pwd.yml`-descended file |
| `W-034` | `open` | (tooling) | `ai/tools/changelog_rotate.py`'s `parse_changelog` crashes on `docs/CHANGELOG.md`'s own machine-generated `## Archived entries` footer ("entry header does not start with a date, refusing to guess") — its skip-non-dated-block logic only skips blocks that don't start with `"## "`, but the footer heading does. Confirmed pre-existing against `HEAD`, not caused by any one session's entries; blocks the normal rotate-instead-of-bump path, so `docs/CHANGELOG.md`'s allowlist ceiling was bumped 2026-08-06 as a stopgap instead | Found 2026-08-06 while landing the `cairn-build doctor` build-timer check; `.docs_check_allowlist`'s `docs/CHANGELOG.md` entry has the detail |
