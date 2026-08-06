---
status: authoritative
owner: project
purpose: Short entry point for future sessions; routes to the smallest relevant document.
---

# Current Context

Use this file as the first context checkpoint. Keep it short — point to detailed docs instead of repeating them.

## Current Phase

Phase 4 (modular code) is under way, on the three-binary split (`cairn-build` / `cairn-adopt` /
`cairn-registry`, `ADR-046`/`ADR-048`) that replaced the unified `cairn` command and the
separate `cairn-provision` installer. Most recently landed: `ADR-052` (manifest:environment is
1:1; promotion is proof, found in the registry, not an assertion). `cairn-registry setup` was
verified live on the client's test VPS 2026-08-04; active work narrowed to `prune`/`gc`
against a real registry (`W-015`) — see `docs/open/OPEN_WORK.md`. Newly decided:
`ADR-059` retires `frappe_docker` vendoring in favor of cairn owning its Docker build recipe
outright, superseding `ADR-001`/`ADR-007`; both the documentation cascade and the code
migration (`src/cairn/vendored/` renamed to `src/cairn/recipe/`, the `ventwig`-backed `vendor`
command surface retired, `W-023`..`W-031`) are done as of 2026-08-05. The docs tree itself
finished its migration onto the canonical Scribe Coding scaffold (`brian-pond/scribe_coding`) —
this file, `docs/open/`, `docs/scratch/`, `docs/technical/`, `docs/adr/`, `docs/decisions/`, and
`docs/discussions/` are the result. Also 2026-08-05: `ADR-060` corrected the registry's default
`data_dir` (`/opt/cairn-registry/data` → `/var/lib/cairn-registry`, `ADR-053`'s FHS citation was
wrong); `ADR-061`/`BR-BUILD-018` added a `cairn-build-owned` marker tag, stripped on push, so
`cairn-build prune` can safely reach a never-shared stale build (not just duplicate-hash
rebuilds) on a host colocating build/registry/target roles — resolved `OQ-001` in the process.
Same day, `ADR-062` fixed two bugs Brian found in `cairn-build setup-timer`, both corrected to
key off the manifest's own `/srv/cairn/<client>/` home rather than `environment` alone or the
invoking shell's `cwd`: the build timer's unit name is now
`cairn-build-<client>-<image_name>-<environment>` (matching `ADR-052`'s own uniqueness key,
which the old `cairn-build-<environment>` name never did — collision risk across clients
sharing an environment or image name), and the generated script now writes to
`/srv/cairn/<client>/` instead of `options.workdir` (previously the operator's cwd at
invocation, often a personal home directory that could later disappear). `setup-timer` now
hard-stops if `--manifest` isn't canonically homed. A companion review of `cairn-adopt`/
`cairn-registry` found `cairn-adopt` clean but `cairn-registry` carrying the same cwd-dependent
script bug (no naming counterpart needed — one registry per host); `ADR-063` moved
`cairn-registry setup-timer`'s generated script to `PROJECT_DIR` (`/opt/cairn-registry`).
Brian then caught that `ADR-062`'s fix was incomplete: the rendered `.service`'s
`WorkingDirectory=` and the script's own `cd` line still read `options.workdir`. `ADR-064`
corrected both to derive from the script's own (now durable) location, and dropped
`--workdir` from `cairn-build setup-timer` entirely once nothing in the stage read it —
`cairn-adopt setup-timer` confirmed unaffected (it never set `WorkingDirectory=` at all).
Brian then raised, and resolved overnight, `OQ-002`: how an unattended build timer
authenticates against a private `github.com` app, expanded once he realized a build host can
serve more than one client and a single shared `CAIRN_GITHUB_TOKEN` can't be assumed to cover
every client's private repos. `ADR-065`: `github_auth.py` stays unchanged — the generated
`.service` now carries a per-client, optional `EnvironmentFile=-/etc/cairn/<client>/
github-token.env`, never written by cairn, referenced only by that client's own unit.
Also 2026-08-05: `ADR-066` resolves `W-021` — `cairn-build build --push` now assigns the
manifest's declared environment by default (`--no-assign-tag` opts out; a manifest with none
is silently skipped, not errored); the `:production` gate needed no new wiring since it was
already keyed off the target environment rather than how assignment was requested.
2026-08-06: nested `decisions/`/`open/`/`scratch/` under `docs/` and moved this file plus
`tools/` into a new root-level `ai/` directory, closing the scaffold-vs-`docs/` anomaly the
canonical Scribe Coding migration left in place. Same day, tightened the Scribe Coding rules
(when a change earns a Decision/ADR file vs. a `docs/CHANGELOG.md` line only; plans archive the
same session their phase completes) and pruned four process-only decision files that predated
the new rule — see `docs/CHANGELOG.md`.

## Read First

| Task | Read |
| --- | --- |
| General project work | `docs/requirements/00-overview.md`, `AGENTS.md` |
| Writing or changing code | `docs/technical/00-coding-standards.md` |
| Requirements or scope work | `docs/requirements/00-overview.md`, `docs/open/OPEN_QUESTIONS.md` |
| "What's done, what remains?" / implementation status | `docs/technical/05-implementation-index.md`, `docs/open/OPEN_WORK.md` |
| Architecture rationale | `docs/adr/README.md`, `docs/decisions/README.md` |
| Pending decisions needing sign-off | `docs/open/OPEN_DECISIONS.md` |
| Outstanding implementation or cleanup work | `docs/open/OPEN_WORK.md` |
| Documentation ownership / what to read for topic X | `docs/technical/25-documentation-authority.md` |

## Standing Rules

- `BR`/`ADR` identifiers never reach a user — see `AGENTS.md` and `tests/test_conventions.py`.
- The data-plane boundary (`ADR-022`) is a hard invariant, not a preference — cairn cannot touch SQL.
- `src/cairn/recipe/frappe_docker/` is cairn's own Docker build recipe, freely edited by hand
  — no vendoring, no pin, no drift check (`ADR-059`).

## Context Rule

Do not scan the whole project by default. Read only what the current task's row above names.
