---
status: authoritative
owner: technical
purpose: ADR-009 — Container registry: registry-agnostic; GHCR recommended default
---

# ADR-009 — Container registry: registry-agnostic; GHCR recommended default

**Decided:** 2026-07-23
cairn is **registry-agnostic** — the registry + namespace is a local build-config value
(`BR-CFG-009`), with auth delegated to `docker login` (`BR-CFG-010`), so any OCI registry
works and nothing is hardcoded to Docker Hub. The **recommended default is GHCR** (GitHub
Container Registry): ERPNext clients/developers already use GitHub heavily; GHCR's auth
fits the pull-only model (`ADR-005`/`ADR-006` — a read-only pull token for the VPS); and
it co-locates images with source.

**Follow-up:** a GHCR setup runbook is needed (PAT creation, `docker login ghcr.io`,
package visibility, VPS pull token) — Brian is only lightly familiar with GHCR. Deferred
to Phase-6 user documentation.
