# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

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

## 2026-08-04 (yet later still — `cairn-build setup` was hard-coded to Docker)

While fixing `doctor`'s missing disk check (previous entry), flagged that `setup`'s own
disk-check data-dir lookup (`setup_runner._docker_data_dir`) was docker-only — a podman
build machine would silently measure `/` instead of podman's real storage. Brian asked to
fix it properly rather than patch around it. Investigating further showed the gap was
bigger than the data-dir lookup: `stage_preflight_build` (`provision.py`) unconditionally
required `docker` and `docker buildx`, so a podman-only machine couldn't pass `cairn-build
setup` at all — `ADR-027`'s docker-or-podman pluggability, already honored by `doctor` and
`build`, had never reached `setup`. It also unconditionally required `docker compose`,
which a build never runs (that check belongs to `cairn-adopt setup`/`cairn-registry
setup`, both genuinely fixed to Docker, `ADR-002`).

Presented the choice — patch just the data-dir lookup (fixes little, since the mandatory
`docker` check aborts first) vs. make the whole build preflight engine-aware — and Brian
chose the full fix. `stage_preflight_build` now detects the engine the way `doctor`/`build`
do, checks buildx only when the selected engine needs it, reads free disk from that
engine's own data root, and drops the `docker compose` check. `setup_runner.py`'s
`_check_disk`/`_check_memory` were promoted to public `check_disk`/`check_memory` (dropped
the leading underscore) so `provision.py` could reuse the threshold logic without
duplicating it — `base_preflight_checks` (still docker-only, correctly, for
`cairn-adopt`/`cairn-registry`) is unchanged otherwise. `ADR-027` amended; `BR-DEPLOY-021`
rule 5 reworded so "the engine" doesn't read as docker-only; `userdocs/builder/index.md`'s
`setup` example output updated to match (the `docker`/`docker compose` lines became one
`build engine` line, `docker compose` dropped entirely).

---

## 2026-08-04 (later still — lessons-learned entry on CLI help verbosity)

Added `docs/technical/04c-lessons-process-notes.md` §5: Typer's rich command-list panel
renders a command's entire first `help=` paragraph, not a truncated summary, so the
multi-sentence prose in `cairn-build`/`cairn-adopt`/`cairn-registry`'s `help=` strings
(commit `02584c8`) wrapped every command list across several lines per row. Went unnoticed
for weeks until a user flagged it directly. No requirement changed — this is a technical
finding about a tool cairn builds on (Typer), plus the process note that the fix was to
delete the mechanism-explaining prose rather than relocate it, since `userdocs/` already
owns that content.

---

## 2026-08-04 (later — archived 2026-07-21 through 2026-07-27 to `docs/archive/`)

This file hit its word-count sprawl limit a second time (`W-014`) on the entry below.
Rather than bump the ceiling again, archived the older half verbatim — content only,
nothing rewritten or summarized — to
[`docs/archive/CHANGELOG-2026-07.md`](archive/CHANGELOG-2026-07.md), which carries its
own dated index. This file now holds only 2026-08-03 onward; the allowlist ceiling
dropped back down to match. `W-014` closed.

---

## 2026-08-04 (later still — Builder walkthrough finished; first real build verified)

A real build succeeded end-to-end against a client VPS: `doctor` (9/9), `--dry-run`, then
`cairn-build build` (5m15s, build-only). `userdocs/builder/index.md`'s walkthrough — which
had ended at *"running the first build itself is coming once verified end-to-end"* — now
covers running the build, reading its timing report, where the image lands (local by
default, `cairn/<image_name>`, unless a registry is configured), verifying that with
`cairn-build images --local`, and next steps (push, `new-tag`/`retag`, deploy).

Updated `open/OPEN_WORK.md` `W-013` to `in_progress` and
`docs/technical/05-implementation-index.md`'s manifest-scaffolding row with the completion
judgment — no requirement changed, this is verification catching up to already-implemented
behavior. Client identity kept out of both files; this repo is public.

---

## 2026-08-04 (later — scaffolded manifest defaults to tags, not `version-16`)

Surfaced doing a real first build: `cairn-build build --dry-run` correctly warned that
pinning to the `version-16` branch is non-reproducible (`BR-BUILD-005`), and the shipped
template was pinning to it by example. Changed the one shared template
(`src/cairn/provision.py` `MANIFEST_TEMPLATE`, `README.md`, `userdocs/reference/manifest.md`
— kept in sync per `ADR-047`) to pin Frappe/ERPNext to tags (`v16.25.0`/`v16.26.1`) instead.

No requirement changed — `BR-BUILD-005` already said the manifest *should* pin to tags and
cairn *should* warn on a branch; the template just wasn't following its own advice. Added a
rationale note to `ADR-015` (kept `02-build.md` within its word-count ceiling) and to
`userdocs/reference/manifest.md`'s `ref` row: branch pinning is a **deliberate,
still-supported** choice for a user who wants every build to auto-track a moving target's
latest release, not a mistake cairn merely tolerates — hence warn, not refuse.

---

## 2026-08-04 — `CONFIGURATION.md` retired; reference migrated to `userdocs/`

Retired, not rewritten — resolves `DOCS-01`. Content re-verified against source, split into
`userdocs/reference/{manifest,builder-config,target-descriptor}.md`; inbound references
repointed. Detail: `open/OPEN_WORK.md` `W-012`, `open/OPEN_DECISIONS.md` `DOCS-01`.


Entries from 2026-08-03 are archived at
[`docs/archive/CHANGELOG-2026-08-03.md`](archive/CHANGELOG-2026-08-03.md). Entries from
2026-07-21 through 2026-07-27 are archived at
[`docs/archive/CHANGELOG-2026-07.md`](archive/CHANGELOG-2026-07.md).
