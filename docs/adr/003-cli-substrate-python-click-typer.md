---
status: authoritative
owner: technical
purpose: ADR-003 — CLI substrate: Python (Click/Typer)
---

# ADR-003 — CLI substrate: Python (Click/Typer)

**Decided:** 2026-07-21
Phase 1 is a Python CLI using Click or Typer, shelling out to `docker`/`buildx`/
`compose`/`bench`. Thin bash only where unavoidable. A TUI may come much later;
not Phase 1.

**Amended 2026-07-24 (`ADR-027`):** the *build* engine is pluggable — `docker build` or
`podman build`, selected per build machine. `compose`/`bench` remain Docker-side on the
target, unchanged.
