---
status: authoritative
owner: technical
purpose: ADR-064 — the build timer's WorkingDirectory= and its script's cd line both corrected off ADR-062's leftover options.workdir dependency; --workdir dropped from cairn-build setup-timer
---

# ADR-064 — the build timer's `WorkingDirectory=` and script `cd` corrected; `--workdir` dropped from `cairn-build setup-timer`

**Decided:** 2026-08-05 (Brian, reviewing the rendered unit files after `ADR-062` landed).
**Amends:** `ADR-062`, `BR-CLI-023`.

## The residual bug

`ADR-062` fixed where the build-automation script's own **file** lives — moved off
`options.workdir` (the invoking shell's `cwd`, typically an operator's home directory) onto
the manifest's durable `/srv/cairn/<client>/` home. It missed two other places the same
`options.workdir` value still leaked into the generated output:

- `build_service()`'s `WorkingDirectory=` — still `options.workdir`.
- `build_script()`'s own `cd {options.workdir}` line, at the top of the generated shell
  script.

Both meant the installed unit still depended on the operator's `cwd` at the moment
`setup-timer` ran, even after the script file itself had been relocated to safety: a retired
account's home directory disappearing would still fail the service (`WorkingDirectory=` must
exist for systemd to start a unit) and the script's own `cd` (with `#!/bin/bash -e`, exiting
immediately). The fix was incomplete, not wrong in kind — same root cause `ADR-062` already
named, just applied to two more spots that reference `options.workdir`.

## Decision

Both now derive from *script*'s own location (`build_service(options, script)` already
receives it as a parameter) rather than `options.workdir`:

- `WorkingDirectory={script.parent}` in the rendered `.service`.
- `cd {options.manifest.parent}` in the rendered script (equal to `script.parent` by
  construction — `stage_timers_build` always writes the script into `options.manifest.parent`).

**`--workdir` is dropped from `cairn-build setup-timer` entirely.** Once both of the above no
longer read `options.workdir`, nothing in the build-timer stage does — a flag that is
accepted but silently ignored is worse than no flag, and `cairn-registry setup` already
established the precedent of dropping a flag once no stage reads it (`ADR-048`). `execute()`'s
header for this command now passes `show_workdir=False`, matching `cairn-registry setup`'s
existing treatment.

## Consequences

- `provision.build_service()`/`build_script()` no longer reference `options.workdir`.
- `cli_build.py`'s `setup_timer_command` drops the `--workdir` parameter.
- `BR-CLI-023` gets a short addendum; no other requirement changes shape.
- `cairn-adopt setup-timer` is unaffected — `stage_timers_adopt`/`systemd.units()` never read
  `options.workdir` in the first place (confirmed by review; the reconcile unit sets no
  `WorkingDirectory=` at all), so it never had this bug to begin with.

*(BR-CLI-023, BR-DEPLOY-009a, ADR-047, ADR-048, ADR-062)*
