---
status: authoritative
owner: technical
purpose: ADR-066 — cairn-build build --push now assigns the manifest's declared environment by default; --no-assign-tag opts out
---

# ADR-066 — `cairn-build build --push` now assigns the manifest's declared environment by default

**Decided:** 2026-08-05 (Brian, resolving `W-021`, raised and deferred 2026-08-04).
**Amends:** `BR-CLI-002a`.

## Raised

`W-021` (`open/OPEN_WORK.md`): `--assign-tag` on `build --push` was opt-in, but
`setup-timer`'s generated script (`ADR-052`) already passes it unconditionally on every poll
(`build --manifest "$MANIFEST" --push --assign-tag --yes`). Brian's point: since the
automated path assigns it anyway, opt-in on the manual path only buys the interval between
polls (default `15min`) of explicitness before the tag gets set regardless — the flag's
opt-in-ness wasn't protecting anything a human would notice in time to matter.

## Decision

**`build --push` assigns by default; `--no-assign-tag` opts out.** The CLI flag becomes a
tri-state `--assign-tag/--no-assign-tag`, unset by default:

- **Unset** (the common case): assign if `--push` was given *and* the manifest declares an
  environment. A manifest declaring none is silently skipped — most manifests don't
  participate in the environment model at all (`userdocs/reference/manifest.md`), and that
  was never a mistake worth surfacing as an error just because assigning became the default.
- **`--assign-tag`** (explicit): still requires `--push` (refused as a contradiction
  otherwise, unchanged), and still errors if the manifest declares no environment
  (`BR-CLI-009`) — an explicit ask deserves the loud failure it already got.
- **`--no-assign-tag`** (explicit): never assigns, regardless of what the manifest declares.

**The `:production` gate needed no new wiring.** `BR-CLI-010`'s confirmation prompt already
lives in `_apply_assignment`, keyed off `assignment.environment.is_production` — it fires
identically whether the assignment came from the new default or an explicit `--assign-tag`.
The concern flagged when `W-021` was first raised ("an automatic assign would need to either
fire that prompt on a plain push, or bypass it") turned out to already be handled: the gate
was never conditioned on *how* assignment was requested, only on *which* environment it
targets.

**Standalone `cairn-build push` is unaffected.** It has no `--assign-tag` surface today and
none is added here — it isn't manifest-environment-aware in the way `build` is (it doesn't
call `environments.check_known`), and `W-021`'s comparison point was specifically `build
--push` against the timer's generated script, not the bare upload command.

## Consequences

- `cli_build.py`'s `assign_tag` parameter changes from `bool = False` to `bool | None = None`.
- `BR-CLI-002a` (`docs/requirements/06-cli.md`) rewritten to describe the default/opt-out/
  explicit-error three-way split.
- `setup-timer`'s generated script is unaffected — its explicit `--assign-tag --yes` is now
  redundant but harmless, and is left as-is rather than simplified in the same change.
- `W-021` resolved.

*(BR-CLI-002a, BR-CLI-009, BR-CLI-010, ADR-052)*
