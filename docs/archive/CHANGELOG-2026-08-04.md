---
status: archived
owner: technical
purpose: Archived tail of docs/CHANGELOG.md — entries from 2026-08-04 (12 entries).
---

# Changelog archive — 2026-08-04

Relocated from `docs/CHANGELOG.md` on 2026-08-06 to keep that file under its word-count
budget (`.docs_check_allowlist`), by `tools/changelog_rotate.py`. Content only — nothing
rewritten, nothing summarized. `docs/CHANGELOG.md` carries current entries; this file is
historical-only per `docs/archive/README.md`.

## Index

- 2026-08-04 (`reconcile` no longer assumes the base compose file is named `compose.yaml`)
- 2026-08-04 (`examine` crashed on an unreadable `.env`; two doc corrections)
- 2026-08-04 (`userdocs/target/`: the third CLI's user docs, previously unwritten)
- 2026-08-04 (docs_check.py's word-count ceiling recalibrated; archived early 2026-08-04 entries)
- 2026-08-04 (later — `BR-CLI-003`: push now invokes `--quiet`)
- 2026-08-04 (`BR-BUILD-016` extended: missing-token hint on a failed private-app lookup)
- 2026-08-04 (`ABOUT_GHCR.md`/`ABOUT_REGISTRIES.md` retired; migrated to `userdocs/`)
- 2026-08-04 (later — `ADR-053` captures the registry's `/etc`/`/opt` split; archived 2026-08-03 to `docs/archive/`)
- 2026-08-04 (`cairn-registry setup` scaffolds a starter config and verifies itself with doctor)
- 2026-08-04 (`cairn-build prune` gains automation, via the build script not a new timer)
- 2026-08-04 (env-tag rename and `new-tag`/`retag` merge)
- 2026-08-04 (later still — `cairn-build doctor` gains a free-disk/memory check)

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
  verbatim to [`docs/archive/CHANGELOG-2026-08-04-early.md`](CHANGELOG-2026-08-04-early.md),
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
  [`docs/archive/CHANGELOG-2026-08-03.md`](CHANGELOG-2026-08-03.md), same pattern as
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
