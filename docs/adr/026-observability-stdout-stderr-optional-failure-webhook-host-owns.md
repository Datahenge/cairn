---
status: authoritative
owner: technical
purpose: ADR-026 — Observability: stdout/stderr + optional failure webhook; host owns monitoring
---

# ADR-026 — Observability: stdout/stderr + optional failure webhook; host owns monitoring

**Decided:** 2026-07-24
cairn (especially the remote reconcile) logs **only to stdout/stderr** — never custom log
files. On a target the systemd timer routes output to journald; the **host's owners** own
professional monitoring/alerting/logging. cairn does not reinvent logging. Additionally,
cairn MAY POST to an **optional, operator-configured failure webhook** — a best-effort,
outbound, transport-agnostic POST with a structured payload — so a tech team learns of
failures without writing a journald-parsing cron, while cairn owns none of the delivery
(SMTP/Slack/PagerDuty is the endpoint's job). *(BR-DEPLOY-019/020)*

**Amended 2026-07-25 (`ADR-031`):** as written, this was absolute — no log files, ever —
and that over-reached. Its rationale is *"something else already owns the record"*
(journald on a target), which is true for the daemon and for CI, but false for a human at
a keyboard. `ADR-031` splits the three contexts and permits a **build transcript** in
attended CLI use only. The rule above stands unchanged for `reconcile` and for every
unattended invocation.
