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
to Phase-6 user documentation. (Delivered as `docs/technical/ABOUT_GHCR.md`.)

**Amended 2026-07-25 (`ADR-038`, `ADR-039`) — GHCR is no longer the recommended default.**
The registry-agnostic premise stands unchanged. The recommendation does not: GitHub
Packages prices multi-gigabyte artifacts badly (roughly 2.5× a purpose-built registry on
storage, plus per-GB egress on every pull), and `frappe_docker` has no per-app layer seam,
so every build is a fresh full-size layer that gets none of the benefit layer-sharing would
otherwise give GHCR. `ADR-038` also surfaced that no registry decision to that point had
ever stated *whose account* the image lands in — a client-ownership question this ADR
never asked. cairn now takes no position on the registry product; a client-owned cloud
registry (ECR/Artifact Registry/ACR) is the default recommendation, with a client-owned
GitHub org as a documented alternative. See `docs/technical/ABOUT_REGISTRIES.md` for the
current guidance and `docs/technical/ABOUT_GHCR.md` for GHCR's mechanics specifically.
