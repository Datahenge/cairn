---
status: authoritative
owner: technical
purpose: ADR-004 — Image build strategy: `custom`, not `layered`
---

# ADR-004 — Image build strategy: `custom`, not `layered`

**Decided:** 2026-07-21
Use `images/custom/Containerfile` (self-contained, `FROM python:*-slim`, builds
the entire base itself), **not** `images/layered/Containerfile`.

**Rationale:** `layered` builds `FROM frappe/base:version-16` / `frappe/build:*`,
which are **mutable tags** Frappe re-pushes over time. The same cairn commit
could then produce a *different* image later, and a rollback could rebuild against a
base that has changed underneath us — fatal to reproducibility/rollback. `custom`
pins Python/Node/wkhtmltopdf ourselves and is deterministic. Its only cost (slower
first build) is absorbed by the buildx layer cache, since the base stage only
rebuilds when base args change, not when apps change.
