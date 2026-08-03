---
status: authoritative
owner: technical
purpose: ADR-001 — Wrap `frappe_docker`, never modify it
---

# ADR-001 — Wrap `frappe_docker`, never modify it

**Decided:** 2026-07-21
Treat upstream `frappe/frappe_docker` as an untouched dependency. All new
capability is bolted on *around* it; we never fork or patch upstream files.
