---
status: authoritative
owner: technical
purpose: Index for lightweight dated decisions in cairn.
---

# Decisions

Short decision records for durable choices that affect design, data handling, naming, or scope,
but do not need full ADR-style alternatives analysis. Consequential decisions instead live in
[../docs/adr/](../docs/adr/).

Pending approvals belong in [../open/OPEN_DECISIONS.md](../open/OPEN_DECISIONS.md). Once
approved and implemented, durable decisions are promoted into a numbered record here, carrying
the original ID into the new file's `origin` field so a citation made while it was open still
resolves.

These ID numbers (`ADR-008`, `ADR-011`, `ADR-041`, `ADR-049`, `ADR-051`, `ADR-053`, `ADR-054`,
`ADR-055`, `ADR-056`, `ADR-057`, `ADR-058`, `ADR-060`, `ADR-062`) continue the same `ADR-NNN`
sequence as `docs/adr/` — they were simply judged lightweight rather than consequential, not a
separate numbering track.

## Records

| Decision | Status | Summary |
|---|---|---|
| [008-cairn-is-itself-a-git-repository.md](008-cairn-is-itself-a-git-repository.md) | `authoritative` | `cairn` is itself a git repository |
| [011-image-tagging-scheme-settled-by-br-build-008.md](011-image-tagging-scheme-settled-by-br-build-008.md) | `authoritative` | Image tagging scheme (settled by `BR-BUILD-008`) |
| [041-the-machine-build-config-file-is-named-builder-toml-not-config.md](041-the-machine-build-config-file-is-named-builder-toml-not-config.md) | `archived` | `builder.toml` rename — superseded same day by `ADR-042` |
| [049-the-declared-environment-list-is-cairn-declared-environments-not.md](049-the-declared-environment-list-is-cairn-declared-environments-not.md) | `archived` | `[cairn.environments]` renamed to `[cairn.declared_environments]` — superseded same day by `ADR-052` |
| [051-cairn-build-prune-runs-inside-the-build-script-not-a-separate-timer.md](051-cairn-build-prune-runs-inside-the-build-script-not-a-separate-timer.md) | `authoritative` | `cairn-build prune` runs inside the build script, not a separate timer |
| [053-registry-splits-etc-cairn-config-from-opt-cairn-registry-data.md](053-registry-splits-etc-cairn-config-from-opt-cairn-registry-data.md) | `authoritative` | The registry role splits `/etc/cairn` (config + secrets) from `/opt/cairn-registry` (compose project + relocatable data) |
| [054-ghcr-and-registry-choice-docs-migrated-to-userdocs.md](054-ghcr-and-registry-choice-docs-migrated-to-userdocs.md) | `authoritative` | `ABOUT_GHCR.md`/`ABOUT_REGISTRIES.md` retired; content migrated into `userdocs/registry/` |
| [055-docs-check-word-count-default-raised-to-2200.md](055-docs-check-word-count-default-raised-to-2200.md) | `authoritative` | `docs_check.py`'s default word-count ceiling raised from 1800 to 2200 |
| [056-changelog-word-ceiling-tripled-to-6000-stop-same-day-archive-churn.md](056-changelog-word-ceiling-tripled-to-6000-stop-same-day-archive-churn.md) | `authoritative` | `docs/CHANGELOG.md`'s word-count ceiling tripled from 2000 to 6000 |
| [057-target-descriptor-splits-registry-host-from-image.md](057-target-descriptor-splits-registry-host-from-image.md) | `archived` | The target descriptor splits `registry_host` from `image`, made optional — superseded same day by `ADR-058`, which makes it required |
| [058-target-descriptor-registry-host-is-required-docker-io-for-hub.md](058-target-descriptor-registry-host-is-required-docker-io-for-hub.md) | `authoritative` | `registry_host` is required; `"docker.io"` is the explicit name for Docker Hub |
| [060-registry-data-dir-default-corrected-to-var-lib-cairn-registry.md](060-registry-data-dir-default-corrected-to-var-lib-cairn-registry.md) | `authoritative` | Registry's default `data_dir` corrected from `/opt/cairn-registry/data` to `/var/lib/cairn-registry` — amends `ADR-053`'s FHS citation |
| [062-build-timer-unit-name-and-script-key-off-the-manifests-client-home.md](062-build-timer-unit-name-and-script-key-off-the-manifests-client-home.md) | `authoritative` | Build-automation timer unit name (`cairn-build-<client>-<image_name>-<environment>`) and generated script location both key off the manifest's `/srv/cairn/<client>/` home — amends `ADR-047`/`BR-CLI-023` |
