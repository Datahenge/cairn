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
| `W-001` | `open` | `DEPLOY` | First live deployment: decide registry → `cairn-build setup`/`cairn-adopt setup` → `cairn-build build --push` → `cairn-build new-tag` → `cairn-adopt reconcile` on a real VPS, in that reversible order | `docs/plans/next-steps.md` §4; everything in the deploy path is tested but unexercised against real infrastructure |
| `W-002` | `open` | `CLI`, `DEPLOY` | Exercise `cairn-adopt doctor`'s target-role checks against a real target post-`ADR-046` split | `docs/plans/next-steps.md` §4a |
| `W-003` | `open` | `DEPLOY` | `BR-DEPLOY-006` — target-side image GC pass (keep last N, never touch volumes); `cairn-build prune`'s analogue | `docs/plans/next-steps.md` §4a |
| `W-004` | `open` | `DEPLOY` | `BR-DEPLOY-020` — optional failure webhook; opt-in, best-effort, must never crash `reconcile` or alter deploy behavior | `docs/plans/next-steps.md` §4a |
| `W-005` | `deferred` | `BUILD` | Registry-backed build cache (`--cache-to`/`--cache-from`) — helps a cold CI runner, not a warm local rebuild; weaker on podman | `docs/plans/next-steps.md` §5; not yet a requirement |
| `W-006` | `open` | (testing) | Decide whether to add a `--cov-fail-under` coverage floor, given `--cov` in `addopts` would break a plain `pytest` run without the plugin installed | `docs/plans/next-steps.md` §5 |
| `W-007` | `open` | `DOCS` | Decide whether `USAGE.md` is still needed separately from `README.md`, or was superseded by it | `docs/plans/next-steps.md` §5 |
| `W-008` | `deferred` | `DEPLOY` | Dedicated service account for `reconcile` instead of `root` — needs `docker` group membership regardless, so the security delta is smaller than it looks; document as a hardening option, not a default | `docs/plans/next-steps.md` §5 |
| `W-009` | `blocked` | `BUILD` | `BR-BUILD-017` — local git mirror for private-app reachability | Blocked on `ADR-044` (`open/OPEN_DECISIONS.md`); full plan in `docs/plans/git-mirror-private-apps.md` |
| `W-010` | `open` | `VEND` | Measure fork-pressure register item 1: time a rebuild after a single custom-app commit, against a first build | `docs/adr/021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md`; feeds the `ADR-021` fork-vs-no-fork decision |
| `W-011` | `open` | `DOCS` | Refresh `docs/plans/phase-1-build.md` into a focused Phase-4 implementation plan, or fold its remaining content elsewhere and archive it | Was due "at Phase-4 start" per the file's own banner; Phase 4 is now under way and this was never done |
| `W-012` | `done` | `DOCS` | `README.md` cut down to a pointer at the published site (2026-08-04), closing the remaining scope | `userdocs/get-started/index.md` covers prerequisites, install, and `doctor`, verified live against a client test VPS (2026-08-03). `docs/technical/CONFIGURATION.md` was retired 2026-08-04 rather than rewritten, replaced by `userdocs/reference/manifest.md`/`builder-config.md`/`target-descriptor.md`. `README.md`'s `## Configuration` section and the builder/registry command blocks under `## How to use` — all now covered, with tested example output, by `userdocs/builder/index.md`, `automation.md`, and `registry/index.md` — were trimmed to pointers; the `## Three roles, one install` table and the target-side command block were kept, since no single userdocs page reproduces the former and no target walkthrough is published yet for the latter |
| `W-013` | `in_progress` | `CLI` | Verify `BR-CLI-022`/`BR-CLI-023` (`ADR-047`) against a real VPS — code and tests landed 2026-08-03 | `src/cairn/provision.py`, `src/cairn/doctor.py`, `src/cairn/cli_build.py`/`cli_adopt.py`. **2026-08-04**: verified live on a client VPS — `cairn-build doctor` (9/9 checks), `--dry-run`, then a real `cairn-build build` (5m15s, no `--push`). Remaining: `setup-timer` and `doctor`'s known-manifests listing still unexercised; picks up from `W-001`'s push → `new-tag` → `reconcile` sequence next |
| `W-014` | `done` | `DOCS` | `docs/CHANGELOG.md` hit its allowlisted word-count ceiling twice (14000→14500 on 2026-08-03, 14500→14550 on 2026-08-04) before being split for real: entries 2026-07-21 through 2026-07-27 moved verbatim to `docs/archive/CHANGELOG-2026-07.md` (with its own dated index), live file dropped to 2026-08-03 onward, allowlist ceiling reset to 4000 | `.docs_check_allowlist`, `docs/CHANGELOG.md`, `docs/archive/CHANGELOG-2026-07.md`, `docs/archive/README.md`; see `docs/technical/01-documentation-conventions.md`'s sprawl-control policy |
| `W-018` | `done` | `BUILD`, `CLI` | `ADR-051` implemented 2026-08-04: `cairn-build prune --keep 1 --yes` runs as the third line of `provision.py`'s generated build script, after `build --push` and `assign-tag` | `decisions/051-cairn-build-prune-runs-inside-the-build-script-not-a-separate-timer.md`; landed together with `W-016`/`W-017` in one pass, since all three touched the same generated script; unexercised against a real host, same as the rest of `setup-timer` (`W-013`) |
| `W-016` | `done` | `CFG`, `CLI` | **Superseded by `W-019`/`ADR-052` the same day.** The `[cairn.environments]` → `[cairn.declared_environments]` rename (`ADR-049`) landed 2026-08-04, but the table itself (any name) is retired hours later by `ADR-052` in favor of a scalar `[cairn] environment` field. Left `done` as a true record of what was implemented and verified at the time — the table shape it produced no longer exists in the codebase. | `decisions/049-...md` (now archived); superseding work is `W-019` |
| `W-017` | `done` | `CLI` | **Superseded by `W-019`/`ADR-052` the same day.** The `new-tag`/`retag` → `assign-tag` merge (`ADR-050`) landed 2026-08-04, but its selector menu (`--latest`/`--previous`/`--id`/`--from`) and positional `<env>` argument are retired hours later by `ADR-052` in favor of a no-build resolve-and-check operation taking `--manifest`. The `setup_runner.execute` `verb` param fix (drive-by, unrelated to the selector design) stands unaffected. Left `done` as a true record of what was implemented and verified at the time. | `docs/adr/050-...md` (now archived); superseding work is `W-019` |
| `W-019` | `done` | `CFG`, `CLI` | `ADR-052` implemented 2026-08-04 (manifest:environment 1:1, promotion is proof not assertion): `config.py` (scalar `environment` field), `environments.py` (trimmed to `declared`/`require`/`check`/`check_known`/`apply`/`retire`), `build.py` (`existing_in_registry` fallback, used by both `build` and `environments.check`), `cli_build.py` (`assign-tag`/`retire` take `--manifest`; `build --assign-tag`; `setup --client --environment` scaffolding; `setup-timer` drops `--environment`, derives it from the manifest), `provision.py` (`cairn_<environment>.toml` scaffolding, two-line build script, parameterized systemd units per environment), `doctor.py` (duplicate `(image_name, environment)` check per client, case-insensitive). Full suite (803 tests) + ruff clean; manually verified scaffolding/duplicate-detection against a real filesystem and the CLI's own `--help` surface | `docs/adr/052-manifest-environment-1-1-proof-not-assertion-promotion.md`; supersedes `W-016`/`W-017`; unexercised against a real registry, same gap as `W-001` |
| `W-020` | `done` | `DOCS` | `userdocs/builder/index.md`, `automation.md` (now the multi-environment worked guide: three manifests, three `setup --client --environment` calls, three `setup-timer` calls, no GitHub Actions, promotion-by-proof explained plainly), `reference/manifest.md`, `reference/target-descriptor.md`, `registry/index.md`, root `README.md` all updated for `ADR-052` | Landed together with `W-019` |
| `W-015` | `in_progress` | `REG` | Implement `cairn-registry` (`ADR-048`, `docs/requirements/08-registry.md`): `registry_config.py`, `registry_provision.py` (migrated `stage_registry`), `registry_retention.py`, `registry.py` delete/catalog additions, `cli_registry.py`, `setup-timer`. Then verify against a real box before the client VPS. | `docs/requirements/08-registry.md`, `docs/adr/048-cairn-registry-a-third-cli-for-local-registry-lifecycle.md`; **separate from `W-003`**, which is target-side local-disk GC (`BR-DEPLOY-006`) — do not conflate the two |
