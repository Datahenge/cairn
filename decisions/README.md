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
`ADR-055`) continue the same `ADR-NNN` sequence as `docs/adr/` — they were simply judged
lightweight rather than consequential, not a separate numbering track.

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
