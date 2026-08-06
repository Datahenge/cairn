---
status: authoritative
owner: technical
purpose: ADR-062 — the build-automation timer's unit name and generated script both key off the manifest's client-scoped home, not environment alone or the invoking shell's cwd
---

# ADR-062 — the build-automation timer's unit name and generated script both key off the manifest's client-scoped home

**Decided:** 2026-08-05 (raised by Brian, ahead of a second client onboarding).
**Amends:** `ADR-047`, `BR-CLI-023` — the `setup`/`setup-timer` split and the timer's
substance are unchanged; only the unit-naming rule and the script's write location are
corrected.

## Two bugs

**Unit name collides across clients.** `provision.build_unit_name()` named the timer
`cairn-build-<environment>` — environment alone. `ADR-052`, decided the day after `ADR-047`
introduced this naming, settled uniqueness as **`(client, image_name, environment)`**,
stating plainly that the same name can legitimately repeat across different `image_name`s —
and, by the same logic, across different clients. The unit name was never updated to match.
A build host serving more than one client — the exact scenario `/srv/cairn/<client>/`
(`BR-CLI-022`) exists for — could see two unrelated builds both resolve to
`cairn-build-production.service`, each `setup-timer` call clobbering (or refusing to
replace without `--force`) the other's script.

**Script lives under the invoking shell's cwd.** `stage_timers_build` wrote the generated
build script to `options.workdir / f"{unit}.sh"`, and `workdir` defaults to `Path.cwd()` at
the moment `setup-timer` runs — ordinarily wherever the operator happened to be, often a
personal home directory. Unlike `/srv/cairn/`/`/etc/cairn` (`ADR-043`/`ADR-047`, deliberately
group-shared and non-user-specific), nothing pinned this to durable, host-owned storage: a
retired operator account, or a home directory cleaned up after offboarding, silently breaks
build automation that has nothing to do with that account.

## Decision

Both are derived from the manifest's own canonical home, `/srv/cairn/<client>/`
(`ADR-047`), rather than from environment alone or from cwd.

**Unit name:** `cairn-build-<client>-<image_name>-<environment>` (`.service`/`.timer`).
`client` and `image_name` are read from the manifest's own location and content — never a
second flag that could disagree with it, the same discipline `ADR-052` already applies to
`environment` ("no command takes an `--environment` argument, ever").

**`setup-timer` requires its `--manifest` to resolve under `MANIFEST_ROOT/<client>/`** — the
exact layout `cairn-build setup --client <name>` provisions (`BR-CLI-022`). A manifest
anywhere else is a hard stop (`Aborted`), not a silent fallback to a weaker naming scheme:
a unit and script whose safety depends on a stable, derivable location should not be
installable somewhere that location can't be derived from.

**Script location:** written to the manifest's own directory,
`/srv/cairn/<client>/<unit>.sh`, instead of `options.workdir`. This is already the
group-shared, non-user-specific home `ADR-047` established for exactly this purpose — reused,
not reinvented.

## Consequences

- `SetupOptions` (`setup_runner.py`) gains an `image_name` field, populated by
  `cairn-build setup-timer` from the loaded manifest, alongside the existing `environment`.
- `provision.build_unit_name()` and `provision.stage_timers_build()` both derive `client`
  from `options.manifest`'s parent directory under `MANIFEST_ROOT`, raising `Aborted` when
  the manifest isn't canonically homed.
- `BR-CLI-023` (`docs/requirements/06-cli.md`) is rewritten to describe the corrected
  naming and location rule.
- No migration path is needed: `setup-timer`'s build script has not yet been run against a
  real host (`docs/open/OPEN_WORK.md`'s `W-013`) — this corrects the rule before its first live
  use, not after.

**Amended same day (`ADR-064`):** this decision's script-location fix was incomplete — the
rendered unit's `WorkingDirectory=` and the script's own `cd` line both still read
`options.workdir`, the exact dependency this decision was meant to eliminate. Corrected to
derive from the script's own (now durable) location instead; `--workdir` dropped from
`cairn-build setup-timer` entirely once nothing in the stage read it any longer.

*(BR-CLI-022, BR-CLI-023, BR-DEPLOY-009a, ADR-043, ADR-047, ADR-052)*
