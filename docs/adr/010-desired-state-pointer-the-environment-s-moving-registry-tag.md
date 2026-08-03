---
status: authoritative
owner: technical
purpose: ADR-010 — Desired-state pointer = the environment's moving registry tag
---

# ADR-010 — Desired-state pointer = the environment's moving registry tag

**Decided:** 2026-07-24
The desired-state pointer is the environment's **moving image tag** in the registry
(`:dev`/`:test`/`:staging`/`:production`). The target's `cairn reconcile` **polls the tag's
digest** (outbound, cheap) and converges when it changes; nothing is pushed into the box.
The laptop advances the pointer by a **server-side retag** (no image pull) — the registry
is the bulletin board both sides touch outbound. Immutable input-hash tags are the durable
identities; the env tag is the movable pointer. Rollback/promote = repoint the tag
(`BR-DEPLOY-004`).

**Why (vs a git state-repo or object/file):** reuses GHCR (no extra infra or inbound),
fits "the registry is the image-and-metadata store" (`BR-CFG-011`), and keeps everything
outbound-only (`ADR-005`/`ADR-006`). Cost: convergence latency = the poll interval;
sub-minute pushes remain the deferred option from `ADR-006`.
