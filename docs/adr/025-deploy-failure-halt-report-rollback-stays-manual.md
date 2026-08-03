---
status: authoritative
owner: technical
purpose: ADR-025 — Deploy failure = halt + report; rollback stays manual
---

# ADR-025 — Deploy failure = halt + report; rollback stays manual

**Decided:** 2026-07-24
On a failed deploy (`migrate` error, or health failure/timeout after the swap), cairn
**halts and reports**; it does **not** auto-rollback. Rollback remains a deliberate,
one-command pointer move (`ADR-012`).
**Rationale:** least surprise — cairn never autonomously changes what's deployed; an
auto-rollback would be cairn making a deploy decision on its own and could mask/flap over a
real fault. Cost: a failed environment may be degraded until the operator acts, but rollback
is fast. *(BR-DEPLOY-018)*
