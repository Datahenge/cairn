---
status: archived
owner: technical
purpose: ADR-028 — `cairn doctor` is role-aware, detected from context
---

# ADR-028 — `cairn doctor` is role-aware, detected from context

**Decided:** 2026-07-24
`ADR-018` establishes that one package serves two roles — build/control on the laptop,
`reconcile` on targets. A single fixed preflight therefore reports irrelevant failures:
a target has no vendored tree and no build engine; a build machine has no compose stack.

**Decision:** `cairn doctor` **detects its role from context** and checks accordingly —
build/control (build engine, vendored-tree integrity, config) versus target (Docker +
Compose, systemd, registry reachability). No flag in the common case, per `BR-CLI-014`'s
minimal-typing goal. The target-role branch lands with `DEPLOY`.
*(BR-CLI-007, BR-CLI-014, ADR-018, ADR-027)*

**Superseded 2026-08-03 (`ADR-046`):** context-detection is retired along with the unified
`cairn` binary it existed to serve. `cairn-build doctor` and `cairn-adopt doctor` each run
exactly one role's checks, unconditionally — the binary invoked is now the role signal,
so there is nothing left to detect.
