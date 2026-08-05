---
status: authoritative
owner: technical
purpose: ADR-008 — `cairn` is itself a git repository
---

# ADR-008 — `cairn` is itself a git repository

**Decided:** 2026-07-21
The project is version-controlled — desirable regardless of any one tool's requirements.
Our scaffolding, CLI, config, and the owned `frappe_docker` recipe tree are all tracked.

**Note (2026-08-05):** originally also required by `ventwig`, the vendoring tool this
requirement predates. `ventwig` is retired (`ADR-059`); the underlying decision to be a git
repository stands on its own merits and is unaffected.
