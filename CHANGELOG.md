# Changelog

All notable **software** releases of `datahenge-cairn` are recorded here, following
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

This file tracks published releases only. Requirement, decision, and design-record revisions
live in `docs/CHANGELOG.md` instead — see `docs/technical/25-documentation-authority.md` for
the full ownership map.

## [Unreleased]

Nothing recorded yet since this file was introduced.

## [0.2.0]

### Added
- `cairn-build setup --client <name>` now provisions `/srv/cairn/<name>/` and, if that
  directory has no `cairn.toml` yet, scaffolds a starter one there — an existing manifest is
  never modified.
- `cairn-build setup-timer` and `cairn-adopt setup-timer` — install the build/reconcile
  automation timer as their own command, separate from `setup`. The timer is still installed
  enabled but not started; run it only after a manual build or reconcile has succeeded.
- `cairn-build doctor` now also reports which client manifests it finds under `/srv/cairn/`,
  for visibility only.

### Changed
- `cairn-build setup` now **requires** `--client <name>`.
- `cairn-build setup` and `cairn-adopt setup` no longer install the automation timer —
  run the new `setup-timer` command afterward instead.

## [0.1.5] and earlier

Released to PyPI as `datahenge-cairn` prior to this file's introduction. Their content is not
backfilled here; consult `git log` and `docs/CHANGELOG.md` for the documentation-level history
of the work each release shipped.
