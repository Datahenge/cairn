---
status: authoritative
owner: technical
purpose: ADR-016 — Single site per environment; multi-site deferred
---

# ADR-016 — Single site per environment; multi-site deferred

**Decided:** 2026-07-24
Each environment runs **one site** (the environment descriptor names one site;
`FRAPPE_SITE_NAME_HEADER` resolves to it). Multi-site on one bench is **deferred** — not a
Phase-1 concern; revisit if a real need arises. *(BR-DEPLOY-014)*
