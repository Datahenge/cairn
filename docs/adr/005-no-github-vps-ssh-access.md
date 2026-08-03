---
status: authoritative
owner: technical
purpose: ADR-005 — No GitHub → VPS SSH access
---

# ADR-005 — No GitHub → VPS SSH access

**Decided:** 2026-07-21
We will **not** give GitHub Actions an SSH key that can reach the VPS. Too risky:
it is an inbound credential into the box, and a CI compromise would reach the server.
