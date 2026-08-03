---
status: authoritative
owner: technical
purpose: ADR-017 — Secrets are operator-provisioned; cairn is secret-agnostic
---

# ADR-017 — Secrets are operator-provisioned; cairn is secret-agnostic

**Decided:** 2026-07-24
cairn MUST NOT store, generate, persist, prompt for, or handle secret **values** — it only
**references and wires** secrets the operator provisions. Registry pull auth on a target is
delegated to Docker's credential store (`docker login ghcr.io` / read-only pull token, set
at provisioning), mirroring the build side (`BR-CFG-010`). DB/app secrets are
operator-provisioned and wired by cairn via the mechanism the environment descriptor
names: **Docker secrets** (`overrides/compose.mariadb-secrets.yaml`) **recommended** (esp.
Production), with plain **`.env`** supported for simple/dev setups. Site-level secrets
(`site_config.json`) remain off-limits (`ADR-022`/`BR-DATA-006`). *(BR-DEPLOY-011..013)*
