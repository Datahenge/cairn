# Changelog

All notable **software** releases of `datahenge-cairn` are recorded here, following
[Keep a Changelog](https://keepachangelog.com/) and [Semantic Versioning](https://semver.org/).

This file tracks published releases only. Requirement, decision, and design-record revisions
live in `docs/CHANGELOG.md` instead — see `docs/technical/25-documentation-authority.md` for
the full ownership map.

## [Unreleased]

### Changed
- `cairn-registry`'s default `data_dir` (where registry image blobs are stored) changed from
  `/opt/cairn-registry/data` to `/var/lib/cairn-registry`, correcting an FHS misapplication in
  the original default. Still fully operator-relocatable via `[registry] data_dir` in
  `/etc/cairn/registry.toml`.

## [0.3.0]

### Added
- `cairn-build doctor` now reports free disk (under the build engine's own data root) and
  available memory — the same floors `cairn-build setup`'s preflight already gated a build
  on, now visible before `setup` ever runs.

### Fixed
- `cairn-build setup` no longer hard-requires Docker. Its preflight now detects docker or
  podman the same way `doctor`/`build` already did — a podman-only build machine can now
  pass `setup` at all, and free disk is read from whichever engine was actually selected.
  It also no longer checks for `docker compose`, which a build never runs.

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
