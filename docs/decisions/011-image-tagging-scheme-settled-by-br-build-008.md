---
status: authoritative
owner: technical
purpose: ADR-011 — Image tagging scheme (settled by `BR-BUILD-008`)
---

# ADR-011 — Image tagging scheme (settled by `BR-BUILD-008`)

**Decided:** 2026-07-24
Settled by `BR-BUILD-008`: a deterministic primary tag `<legible>-<inputhash>` (legible Frappe
slug + input hash) plus the moving environment tags (`:dev`/`:test`/`:staging`/
`:production`) that serve as desired-state pointers (`ADR-010`). No separate decision
remains.

**Correction (`ADR-032`):** "immutable" is the wrong word for the primary tag and was later
retracted — it is a re-pointable *name*, not a content address; the digest is the actual
immutable address. Corrected to **deterministic** throughout. *(BR-BUILD-008, ADR-010,
ADR-032)*
