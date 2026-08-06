---
status: authoritative
owner: technical
purpose: ADR-070 — cairn-build doctor's new build-timer check takes an explicit --manifest (one) or --all (every manifest under /srv/cairn/) rather than defaulting to a scope
---

# ADR-070 — `cairn-build doctor`'s build-timer check: `--all` walks every manifest, not just the one given

**Decided:** 2026-08-06 (Brian).
**Amends:** `BR-CLI-007`.

## Raised

Brian asked `cairn-build doctor` to report whether the systemd units `cairn-build setup-timer`
(`BR-CLI-023`) installs exist and are enabled/active — currently invisible short of a manual
`systemctl` check per manifest. The obvious first design mirrored the existing `github
reachability` check: scope to whichever single manifest `--manifest`/`$CAIRN_MANIFEST` names.

Brian rejected that scope: `/srv/cairn/` is a static, known directory (`BR-CLI-022`), and a build
host commonly serves more than one client/environment (the same fact that drove `ADR-062`'s
unit-naming scheme). Scoping the check to one manifest at a time would force an operator to
script their own enumeration — loop over every `.toml` under `/srv/cairn/`, derive each unit
name, shell out to `systemctl` — just to be sure every timer on the host is actually running.
That script is exactly the kind of manual toil `doctor` exists to replace.

A follow-up question — should `--all` also broaden the other manifest-scoped checks
(`config`, `github reachability`) to a full per-manifest audit — was raised and deliberately
deferred rather than folded into this change; see `docs/open/OPEN_DECISIONS.md`.

## Decision

`cairn-build doctor` gains two mutually exclusive scope flags for the new build-timer check:

- `--manifest <path>` — report that one manifest's timer only (its `.service`/`.timer`
  existence, and the timer's enabled/active state).
- `--all` — walk every manifest found under `/srv/cairn/*/*.toml` (the same enumeration
  `check_known_manifests` already performs) and report one result per manifest.

Giving both is a usage error, not a silent precedence rule — an operator should never have to
guess which one doctor honored.

Neither flag is required. Bare `cairn-build doctor` keeps running every host-level check exactly
as before (`ADR-028`/`ADR-046`'s "no context-sniffing" rule is unchanged) — but rather than
silently omitting the build-timer check the way `github reachability` does today when no
manifest is found, doctor's output notes that the check was skipped and how to run it. The two
checks differ here on purpose: `github reachability` needs a real manifest to resolve refs
against, so silence is the only honest answer with none; the build-timer check has a knowable,
static universe of manifests to report on (`--all`) even with none named explicitly, so silence
would hide that the option exists.

## Consequences

- `provision.py`: `build_unit_name(options)`'s naming logic is extracted into a pure
  `unit_name_for(client, image_name, environment)`, so `doctor.py` can compute the same unit
  name for every manifest it walks without duplicating the f-string or risking drift from the
  name `setup-timer` actually installs.
- `doctor.py`: new `check_build_timers()` (or equivalent), wired into `run_build_checks()`,
  driven by the CLI's `--manifest`/`--all` flags rather than inferring scope from what
  `check_config` already loaded.
- `cli_build.py`: `doctor_command` gains `--all`, validated against `--manifest` via
  `typer.BadParameter` before either check family runs.
- `docs/requirements/06-cli.md`'s `BR-CLI-007` cairn-build bullet documents the flags and the
  bare-invocation reminder.

*(BR-CLI-007, BR-CLI-022, BR-CLI-023, ADR-028, ADR-046, ADR-062)*
