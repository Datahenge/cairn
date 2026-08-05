---
status: active
owner: project
purpose: Central backlog for implementation and cleanup work that is not blocked on a pending decision.
---

# Open Work

Source-controlled backlog for unfinished implementation, cleanup, and operating work. Work that
cannot proceed until Brian chooses between options belongs in
[OPEN_DECISIONS.md](OPEN_DECISIONS.md) instead. Current system state by area lives in
[../docs/technical/05-implementation-index.md](../docs/technical/05-implementation-index.md);
this file tracks the discrete tasks that get you there. Seeded 2026-08-03 from
[../docs/plans/next-steps.md](../docs/plans/next-steps.md).

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
record of everything ever finished.

## Backlog

| ID | Status | Area | Work | Notes / Links |
| --- | --- | --- | --- | --- |
| `W-001` | `done` | `DEPLOY` | First live deployment: decide registry → `cairn-build setup`/`cairn-adopt setup` → `cairn-build build --push` → `cairn-build new-tag` → `cairn-adopt reconcile` on a real VPS, in that reversible order | Done 2026-08-05, with a real caveat: the target's pre-existing compose file didn't consume `CUSTOM_IMAGE`/`CUSTOM_TAG` for any service (fork-pressure register item 4, `ADR-021`), so the first `reconcile` falsely reported convergence — see `docs/technical/05-implementation-index.md`'s Reconcile/deploy row and `W-022`. Compose file hand-fixed, convergence confirmed by `docker inspect`, a subsequent real `reconcile` correctly reported `Already running` |
| `W-002` | `done` | `CLI`, `DEPLOY` | Exercise `cairn-adopt doctor`'s target-role checks against a real target post-`ADR-046` split | Verified live 2026-08-05 against the same target — all 6 checks (descriptor, docker, compose, reconcile timer, registry, shared config) pass, both before and after descriptor install |
| `W-003` | `open` | `DEPLOY` | `BR-DEPLOY-006` — target-side image GC pass (keep last N, never touch volumes); `cairn-build prune`'s analogue | `docs/plans/next-steps.md` §4a |
| `W-004` | `open` | `DEPLOY` | `BR-DEPLOY-020` — optional failure webhook; opt-in, best-effort, must never crash `reconcile` or alter deploy behavior | `docs/plans/next-steps.md` §4a |
| `W-005` | `deferred` | `BUILD` | Registry-backed build cache (`--cache-to`/`--cache-from`) — helps a cold CI runner, not a warm local rebuild; weaker on podman | `docs/plans/next-steps.md` §5; not yet a requirement |
| `W-006` | `open` | (testing) | Decide whether to add a `--cov-fail-under` coverage floor, given `--cov` in `addopts` would break a plain `pytest` run without the plugin installed | `docs/plans/next-steps.md` §5 |
| `W-007` | `done` | `DOCS` | Decide whether `USAGE.md` is still needed separately from `README.md`, or was superseded by it | Closed 2026-08-05 — never written; superseded by the published user-facing docs on GitHub Pages (`userdocs/` → `https://datahenge.github.io/cairn/`, `ADR-045`), which already cover installation and per-role walkthroughs. `docs/plans/next-steps.md` §5 |
| `W-008` | `deferred` | `DEPLOY` | Dedicated service account for `reconcile` instead of `root` — needs `docker` group membership regardless, so the security delta is smaller than it looks; document as a hardening option, not a default | `docs/plans/next-steps.md` §5 |
| `W-009` | `blocked` | `BUILD` | `BR-BUILD-017` — local git mirror for private-app reachability | Blocked on `ADR-044` (`open/OPEN_DECISIONS.md`); full plan in `docs/plans/git-mirror-private-apps.md` |
| `W-010` | `done` | `VEND` | Measure fork-pressure register item 1: time a rebuild after a single custom-app commit, against a first build | Closed 2026-08-05 — measurement superseded by `ADR-059`; cairn now owns the recipe outright, no fork-vs-no-fork decision to gate |
| `W-011` | `open` | `DOCS` | Refresh `docs/plans/phase-1-build.md` into a focused Phase-4 implementation plan, or fold its remaining content elsewhere and archive it | Was due "at Phase-4 start" per the file's own banner; Phase 4 is now under way and this was never done |
| `W-013` | `in_progress` | `CLI` | Verify `BR-CLI-022`/`BR-CLI-023` (`ADR-047`) against a real VPS — code and tests landed 2026-08-03 | `src/cairn/provision.py`, `src/cairn/doctor.py`, `src/cairn/cli_build.py`/`cli_adopt.py`. **2026-08-04**: verified live on a client VPS — `cairn-build doctor` (9/9 checks), `--dry-run`, then a real `cairn-build build` (5m15s, no `--push`). Remaining: `setup-timer` and `doctor`'s known-manifests listing still unexercised; picks up from `W-001`'s push → `new-tag` → `reconcile` sequence next |
| `W-015` | `in_progress` | `REG` | Implement `cairn-registry` (`ADR-048`, `docs/requirements/08-registry.md`): `registry_config.py`, `registry_provision.py` (migrated `stage_registry`), `registry_retention.py`, `registry.py` delete/catalog additions, `cli_registry.py`, `setup-timer`. Then verify against a real box before the client VPS. | `docs/requirements/08-registry.md`, `docs/adr/048-cairn-registry-a-third-cli-for-local-registry-lifecycle.md`; **separate from `W-003`**, which is target-side local-disk GC (`BR-DEPLOY-006`) — do not conflate the two |
| `W-020` | `open` | `BUILD` | Discuss with Claude: a `systemd` timer for build-side cleanup (analogous to `cairn-build prune`/`setup-timer`), scoped correctly against `HOME` directories and the per-client-environment namespace under `/srv/cairn/` (`ADR-047`) — not yet a requirement, needs scoping first | Raised by Brian 2026-08-04; relates to existing `systemd.py`/`setup_runner.py` timer machinery — do not conflate with `W-003` (target-side image GC) |
| `W-021` | `open` | `CLI` | Discuss with Brian: should `cairn-build push`/`build --push` default to assigning the environment tag (today opt-in, `--assign-tag`, `BR-CLI-002a`/`BR-CLI-003`), given `setup-timer`'s generated script already does it unconditionally every poll (`ADR-052`) — Brian's point: since the timer assigns it anyway, opt-in on the manual path only buys the interval between polls (default `15min`) of explicitness before the tag gets set regardless | Raised by Brian 2026-08-04, deferred — "come back to this later"; likely touches `BR-CLI-010`'s `:production` confirmation gate (an automatic assign would need to either fire that prompt on a plain `push`, or bypass it) — this is Claude's inference, not a cited prior decision; no existing doc records why the manual path is opt-in |
| `W-022` | `open` | `DEPLOY` | `reconcile.running_digest()` verifies a local image with the desired tag+digest *exists*, not that any container is actually *running* it — on a target whose compose file doesn't consume `CUSTOM_IMAGE`/`CUSTOM_TAG` for every service (fork-pressure register item 4, `ADR-021`), this let a real `reconcile` report `Converged to sha256:...` while every erpnext-app container was still running the old image. Comparing the `backend` container's actual running image ID against the desired digest post-convergence would turn this into a loud failure instead of a silent false-positive | Found live 2026-08-05 on a client VPS adopt; `src/cairn/reconcile.py` (`running_digest`, `converge`); independent of whether `ADR-021`'s fork question is ever revisited — this is a `reconcile` correctness gap on its own |
| `W-023` | `open` | `VEND` | Rename `src/cairn/vendored/` → `src/cairn/recipe/` (mechanical); update `pyproject.toml`'s package-data path | `ADR-059`; documentation cascade for the ownership decision is already done — this is the first code-migration step, block the rest of `W-024`..`W-031` on it |
| `W-024` | `open` | `VEND` | Retire `src/cairn/vendor.py`'s ventwig-wrapping functions (`status`, `sync`, `_refresh_pin_file`, `read_pin`, the drift check inside `assert_clean`, `_tree_hash`); keep `assert_build_inputs` (`BR-VEND-003`), reframed as an ordinary sanity check, not a vendoring precondition | `ADR-059`, `docs/requirements/01-vendoring.md`; blocked by `W-023` |
| `W-025` | `open` | `VEND` | Retire `src/cairn/project.py` entirely (`find_project_root`, `read_vendor_sources` — both `[tool.ventwig]`-shaped, no longer needed) | `ADR-059`; blocked by `W-023` |
| `W-026` | `open` | `CLI` | Remove the `vendor` Typer sub-app from `src/cairn/cli_build.py` (`vendor_app`, `vendor_status`, `vendor_sync`, `_run_in_project`) | `BR-CLI-006` (struck), `ADR-059`; blocked by `W-024`/`W-025` |
| `W-027` | `open` | `BUILD` | Update `src/cairn/build.py`: `plan()` drops the `assert_clean`/`assert_no_nested_git` drift-gate calls; `provenance_labels()` redesigned to stamp the recipe's own git commit/cairn version instead of reading `frappe_docker.pin.toml` | `BR-BUILD-009`, `BR-BUILD-011`, `ADR-059`; blocked by `W-024` |
| `W-028` | `open` | `CLI` | Update `src/cairn/doctor.py`: drop the three vendor-drift guard checks tied to ventwig; keep a build-input-completeness check if still valuable | `ADR-059`; blocked by `W-024` |
| `W-029` | `open` | `VEND` | Remove `[tool.ventwig]` section and the `ventwig>=0.2,<0.3` dev dependency from `pyproject.toml` | `ADR-059`; blocked by `W-023`..`W-026` |
| `W-030` | `open` | `VEND` | Update/retire tests: `tests/test_vendor.py`, `tests/test_project.py`, the vendor-related parts of `tests/test_build.py`, `tests/test_cli_build.py` (`test_vendor_status_outside_a_project_exits_two`, `test_vendor_command_forwards_the_source_and_exit_code`), and `tests/test_doctor.py`'s vendor guard fixtures/assertions | `ADR-059`; blocked by `W-024`..`W-028`, should land alongside each corresponding code change rather than as one final pass |
| `W-031` | `open` | `DOCS` | Fix the `userdocs/` ID leak and rewrite user-facing description: `userdocs/index.md`, `userdocs/reference/index.md` (drop the `ventwig`/`vendor status\|sync` walkthrough), `userdocs/builder/index.md` (remove the literal `(ADR-001)` citation — already a standing violation of "IDs never reach a user" independent of this pivot) | `ADR-059`; blocked by `W-026` since the user-facing CLI description must match the actual command surface |
