---
status: authoritative
owner: technical
purpose: ADR-011 — Image tagging scheme (settled by `BR-BUILD-008`)
---

# ADR-011 — Image tagging scheme (settled by `BR-BUILD-008`)

**Decided:** 2026-07-24
Settled by `BR-BUILD-008`: an immutable primary tag `<legible>-<inputhash>` (legible Frappe
slug + input hash) plus the moving environment tags (`:dev`/`:test`/`:staging`/
`:production`) that serve as desired-state pointers (`ADR-010`). No separate decision
remains. *(BR-BUILD-008, ADR-010)*
