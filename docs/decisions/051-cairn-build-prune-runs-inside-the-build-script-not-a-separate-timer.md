---
status: authoritative
owner: technical
purpose: ADR-051 — `cairn-build prune` runs inside the build script, not a separate timer
---

# ADR-051 — `cairn-build prune` runs inside the build script, not a separate timer

**Decided:** 2026-08-04

**Problem.** `cairn-build prune` (removes superseded local images on the build machine) has no
automation — `setup-timer` wires only the build/retag script (`ADR-047`), so local disk cleanup
is manual-only today. Raised by Brian alongside the Builder automation-docs discussion, as a gap
worth closing, not just documenting as a known limitation.

**Decision:** no separate timer. `cairn-build prune --keep 1 --yes` becomes a fourth line in the
same script `setup-timer` already writes (`provision.py`'s build script), run immediately after
`build --push` and the pointer-move step.

**Why not a `cairn-registry`-style separate timer.** `cairn-registry`'s prune+gc timer
(`BR-REG-010`) is necessarily separate because a registry has no cadence of its own to hook —
tags can arrive from any build machine, at any time, so it needs an independent schedule.
Local build-machine cruft has no equivalent ambiguity: every image on this disk was put there by
a build *this same machine* ran, so the only moment new cruft can exist is immediately after this
machine's own build script runs. A separate timer would just be polling for an event the script
itself already knows just happened.

**Safety.** Unchanged from the manual command: only untagged, superseded images are removed, and
the newest per input-hash set is always kept (`--keep 1`, `BR-CLI-018`). No new opt-in gate is
added — running `setup-timer` at all is the operator's existing consent, the same as it already
is for the build and retag steps in the same script.

**Scope.** `provision.py`'s `build_script()` gains the `prune` line; `BR-CLI-023` gains a
sentence naming it, since the requirement previously described only the build/retag steps.
Same implementation pass as `ADR-050` (`assign-tag`), since both touch the same generated
script. *(BR-CLI-018, BR-CLI-023, ADR-047, ADR-050)*
