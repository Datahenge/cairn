---
status: archived
owner: technical
purpose: Archived tail of docs/CHANGELOG.md — the earlier half of 2026-08-04's entries.
---

# Changelog archive — 2026-08-04 (early)

Relocated from `docs/CHANGELOG.md` on 2026-08-04 to keep that file under its word-count
sprawl limit — the same day's later entries stayed live, since `docs/CHANGELOG.md`'s own
archive boundary had already moved past whole-date splits (2026-07, 2026-08-03) to a
within-day one. Content only — nothing rewritten, nothing summarized. `docs/CHANGELOG.md`
carries current entries; this file is historical-only per `docs/archive/README.md`.

## Index

- 2026-08-04 (yet later still — `cairn-build setup` was hard-coded to Docker)
- 2026-08-04 (later still — lessons-learned entry on CLI help verbosity)
- 2026-08-04 (later — archived 2026-07-21 through 2026-07-27 to `docs/archive/`)
- 2026-08-04 (later still — Builder walkthrough finished; first real build verified)
- 2026-08-04 (later — scaffolded manifest defaults to tags, not `version-16`)
- 2026-08-04 — `CONFIGURATION.md` retired; reference migrated to `userdocs/`

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
[`docs/archive/CHANGELOG-2026-07.md`](CHANGELOG-2026-07.md), which carries its
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
