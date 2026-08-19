---
status: authoritative
owner: technical
purpose: ADR-075 — cairn-adopt gains named inspection verbs (console, mariadb, logs) rather than a general compose passthrough
---

# ADR-075 — Named inspection verbs, not a compose passthrough

**Decided:** 2026-08-19 (Brian)

`ADR-073` ruled that a human should not run `docker compose` directly against a cairn-managed
stack, and gave the operator `stop`/`start`/`restart`. `W-037` — a general
`cairn-adopt compose -- <args>` passthrough — was rejected in the same breath.

That left a gap, found in use the same week: Brian needed a SQL console on a client VPS and had
no cairn verb for it, so the only route was the `docker compose` invocation the decision says to
avoid. He was keeping two shell scripts in his home directory on the VPS to paper over it — the
signal that the tool was missing something, not that the operator was misusing it.

**Decision:** `cairn-adopt` gains three **named** verbs — `console`, `mariadb`, `logs` — each
taking its site, project and compose files from the descriptor so none needs an argument.

**Why named verbs rather than reviving `W-037`.** A passthrough makes *arbitrary* compose use
easy, which is what `ADR-073` set out to discourage; named verbs make the **specific** things an
operator legitimately needs easy while leaving everything else deliberately awkward. The
distinction is the whole point: the goal was never to make compose hard, it was to stop cairn's
stack being driven by hand in ways cairn cannot account for. Reading logs and opening a console
are not that.

## Shape

- **No `-T`.** `console` and `mariadb` are interactive. The MariaDB client silently drops into
  batch mode — no banner, no prompt — when stdin is not a TTY, which is indistinguishable from
  a hang; Python's console prints prompts regardless, which is why `bench console` appeared to
  tolerate `-T` while `bench mariadb` did not. Both verbs therefore replace the cairn process
  via `execvp` rather than running compose as a child, handing the terminal, Ctrl-C and Ctrl-D
  over cleanly instead of leaving Python in the middle.
- **No single-flight lock.** `BR-CLI-029`'s lifecycle verbs take it; these must not. A console
  can be open for hours, and holding the reconcile lock for that long would silently block
  every deploy. The tradeoff is acknowledged rather than hidden: an open SQL console during a
  `bench migrate` is genuinely hazardous, but a tool that blocks deploys for as long as a human
  leaves a window open is worse, and arbitrating that is not cairn's job.
- **They work while the stack is held** (`BR-DEPLOY-024`). A maintenance hold is exactly when
  an operator wants a console. These inspect; they do not manage lifecycle.
- **`logs` takes bounded flags** — `--follow`, `--tail`, an optional service — not a
  passthrough after `--`, which would reintroduce `W-037`'s shape through a side door.
- **`mariadb` keeps Frappe's own name** rather than a neutral `db`/`sql`, so there is nothing
  new to learn. cairn's recipe does ship a Postgres override, so the verb refuses with a clear
  message when the descriptor layers `postgres`; a `postgres` verb can follow if a client ever
  needs one. That check is best-effort — a hand-built stack may use Postgres without declaring
  the override — so it is a courtesy, not a guarantee.

## Amended 2026-08-19 — `shell`, and why there is no `config` verb

Brian asked for three more helpers: print `common_site_config.json`, print `site_config.json`,
and a shell in the container. The first two are **refused**, and not on judgment —
`BR-DATA-006` lists **read** among the things cairn must not do to those exact files, and
`BR-DEPLOY-011` forbids handling secret values, which `site_config.json`'s `db_password` is.
Printing it would put a live credential into terminal scrollback and any recording of it.

The third makes the first two unnecessary, which is why the boundary costs nothing here:
`cairn-adopt shell [SERVICE]` hands over a terminal and reads nothing. The operator reads their
own file. Same outcome, no requirement amended, no credential through cairn. A test asserts no
verb's command names either config file, so none can quietly grow a `cat` of them.

*(BR-CLI-029, BR-CLI-030, BR-DATA-006, BR-DEPLOY-011, BR-DEPLOY-024, ADR-073, ADR-074)*
