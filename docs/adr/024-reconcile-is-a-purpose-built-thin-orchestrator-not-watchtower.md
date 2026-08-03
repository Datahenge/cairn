---
status: authoritative
owner: technical
purpose: ADR-024 — Reconcile is a purpose-built thin orchestrator (not Watchtower/Flux/Argo)
---

# ADR-024 — Reconcile is a purpose-built thin orchestrator (not Watchtower/Flux/Argo)

**Decided:** 2026-07-24
cairn's `reconcile` is built as thin glue over primitives we already stand on:
`docker`/`docker compose`, the **registry manifest API** (the digest poll — ~10 lines),
and **systemd timers**. cairn does **not** adopt an off-the-shelf updater.

**Evaluated and rejected:**
- **Flux / ArgoCD** — Kubernetes-native GitOps controllers; adopting them means adopting
  k8s, rejected by `ADR-002` (single-host Compose).
- **Watchtower** — solves only the trivial part (poll a tag's digest, pull, recreate a
  container) and *fights* the valuable part: it is **per-container**, not per-stack, so a
  post-update `bench migrate` hook would fire once per service (5×) with no coordination;
  it recreates containers outside `docker compose`'s knowledge; and it has no concept of
  environments, `CUSTOM_IMAGE`/`CUSTOM_TAG` composition, `install-app` opt-in, or
  health-gated sequencing.

The polling *pattern* is proven (Watchtower's existence), but the digit-check is trivial
to implement, and the **single-host Frappe orchestration** (pull → `compose up` → `migrate`
once → optional `install-app` → health → rollback-by-repoint) has no off-the-shelf
solution — it is precisely the connective tissue cairn exists to provide.
