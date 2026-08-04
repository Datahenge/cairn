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
| `W-012` | `in_progress` | `DOCS` | Rewrite `README.md` for the `cairn-build`/`cairn-adopt` split (`ADR-046`) — still describes the retired unified `cairn` binary and `cairn-provision` in places | `userdocs/get-started/index.md` now covers prerequisites, install, and `doctor`, verified live against a client test VPS (2026-08-03) — no longer forwards those topics to the stale README. `docs/technical/CONFIGURATION.md` was retired 2026-08-04 rather than rewritten: its content now lives, written correctly against current behavior (including `/etc/cairn/adopt.toml`), at `userdocs/reference/manifest.md`, `builder-config.md`, and `target-descriptor.md`. Remaining scope: `README.md` gets cut down to a pointer at the published site |
| `W-013` | `open` | `CLI` | Verify `BR-CLI-022`/`BR-CLI-023` (`ADR-047`) against a real VPS — code and tests landed 2026-08-03, but `cairn-build setup --client <name>` scaffolding, `setup-timer`, and `doctor`'s known-manifests listing have not yet run against real infrastructure | `src/cairn/provision.py`, `src/cairn/doctor.py`, `src/cairn/cli_build.py`/`cli_adopt.py`; full test suite green, `ruff` clean. Once the new version is published and `pipx upgrade`d on the test VPS, this becomes the next live step in the Builder guide walkthrough |
| `W-014` | `done` | `DOCS` | `docs/CHANGELOG.md` hit its allowlisted word-count ceiling twice (14000→14500 on 2026-08-03, 14500→14550 on 2026-08-04) before being split for real: entries 2026-07-21 through 2026-07-27 moved verbatim to `docs/archive/CHANGELOG-2026-07.md` (with its own dated index), live file dropped to 2026-08-03 onward, allowlist ceiling reset to 4000 | `.docs_check_allowlist`, `docs/CHANGELOG.md`, `docs/archive/CHANGELOG-2026-07.md`, `docs/archive/README.md`; see `docs/technical/01-documentation-conventions.md`'s sprawl-control policy |
| `W-015` | `in_progress` | `REG` | Implement `cairn-registry` (`ADR-048`, `docs/requirements/08-registry.md`): `registry_config.py`, `registry_provision.py` (migrated `stage_registry`), `registry_retention.py`, `registry.py` delete/catalog additions, `cli_registry.py`, `setup-timer`. Then verify against a real box before the client VPS. | `docs/requirements/08-registry.md`, `docs/adr/048-cairn-registry-a-third-cli-for-local-registry-lifecycle.md`; **separate from `W-003`**, which is target-side local-disk GC (`BR-DEPLOY-006`) — do not conflate the two |
