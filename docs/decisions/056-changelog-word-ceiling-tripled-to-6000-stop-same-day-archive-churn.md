---
status: authoritative
owner: technical
purpose: ADR-056 — docs/CHANGELOG.md's word-count ceiling tripled from 2000 to 6000
---

# ADR-056 — docs/CHANGELOG.md's word-count ceiling tripled from 2000 to 6000

**Decided:** 2026-08-04

**Problem.** `docs/CHANGELOG.md`'s `.docs_check_allowlist` override was deliberately dropped to
2000 the same day (`ADR-055`'s sibling change, same commit window) specifically to force a
same-day archive cadence. In practice it fired again within hours, mid-session, during a live
debugging thread on a client VPS — the archive pass it demands interrupts exactly the kind of
work that generates the entries in the first place. Raised by Brian: stop hitting this.

**Decision:** `docs/CHANGELOG.md`'s override raised from 2000 to **6000** in
`.docs_check_allowlist`. No archiving performed as part of this change — the existing ~2200
words of live 2026-08-04 entries are left in place; the next archive pass happens on its own
schedule, not forced by a ceiling calibrated too tight for a single active day's entries.

**Why not remove the override, or raise `DEFAULT_MAX_WORDS` instead.** This file's shape is
categorically different from a requirement doc (`ADR-055`'s concern): it grows by dated
append-only entries throughout a single working day, not by revision of stable content, so its
"natural size" before a periodic archive pass is much larger than a settled requirements
document's. A generous, file-specific override reflects that; changing the global default would
not, since every other document `DEFAULT_MAX_WORDS` governs doesn't have this append-only shape.

**Scope.** `.docs_check_allowlist` only. No requirement, code behavior, or archiving-process
convention changed — this file's per-entry archive pattern (`docs/archive/CHANGELOG-*.md`,
`docs/archive/README.md`'s index) is unaffected.
