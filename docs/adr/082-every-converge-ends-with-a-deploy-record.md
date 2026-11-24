---
status: exploratory
owner: technical
purpose: ADR-082 — every converge prints one machine-readable deploy record, with an optional probe that measures what users saw during the pass
---

# ADR-082 — Every converge ends with a deploy record

**Proposed:** 2026-11-24 (Life Scientific, contributed as a pull request; awaiting Brian).

**Adds:** `BR-DEPLOY-026`. **Relates to:** `ADR-026`, `ADR-081`, `BR-DEPLOY-019`.

## Context

Life Scientific's staging target runs hot swap (`ADR-081`). Testers still report that some
deploys interrupt them. The ones they notice are the deploys that change a schema file, a
print format for example. Converges that skip `bench migrate` go unnoticed.

Nothing on the target says how long a converge's steps took, whether `bench migrate` ran, or
what a user saw meanwhile. The journal holds the progress lines, but reading a duration from
them means subtracting timestamps by hand, and they say nothing about the site's answers. So
"some deploys cause downtime" stays an impression. A change meant to remove downtime cannot
show that it did.

## Decision

**One line per converging pass.** After every pass that starts to converge, `reconcile`
prints `deploy record {…}` to stdout, as the last thing it prints, whether the pass succeeded
or failed. One JSON object on one line, so `journalctl -u cairn-reconcile.service | grep
'deploy record'` yields one row per deploy and `jq` reads it. It holds:

- `environment`, `from` (the running digest, or null on a first deploy), `to`.
- `outcome`: `ok` or `failed`, and `error` with the failure's first line.
- `path`: `recreate` or `hot-swap`, and `path_note` when hot swap was configured but not
  taken (first deploy, stack down, the app list changed).
- `migrate`: whether `bench migrate` ran and how long it took. When it ran, the tables Frappe
  wrote during it, read from the `touched_tables.json` Frappe leaves in the site folder.
- `steps`: seconds per step (pull, configurator, migrate, start, web, retire, workers, finish,
  health; only the steps the path took).
- `probe`, when configured (below).

**An optional probe that sees what users see.** A new optional `[record]` table takes
`probe_url` and `probe_interval_ms` (default 500, minimum 100). With a URL set, a background
thread requests it from the host for the length of the pass: one request at a time, a
10 second timeout, any 2xx or 3xx counted as an answer. The summary holds `requests`,
`failed`, `p50_ms`, `p95_ms`, `max_ms` over answered requests, and `longest_outage_s`, the
longest unbroken run of failures. The operator points it at the public URL, through the outer
proxy, because that is the path users take. The health probe (`BR-DEPLOY-017`) runs inside
the stack on purpose, so it cannot answer this question.

**Observation only.** The record and the probe never change what the pass does. A probe that
cannot start, a `touched_tables.json` that is missing or unreadable, or a record that cannot
be built is reported on stderr and left out of the record.

**Stdout only** (`BR-DEPLOY-019`). Under the timer, journald keeps the record. No file, no
history kept by cairn (`ADR-026`).

## What it does not do

- **No alerting.** The optional failure webhook (`BR-DEPLOY-020`) is a separate decision. The
  record is the data such a webhook would want, but this decision does not send it anywhere.
- **No record for a converged, held or dry-run pass.** Those change nothing, and a record
  every 15 seconds would bury the ones that matter.
- **The probe measures one URL.** A cheap endpoint such as Frappe's `/api/method/ping` shows
  whether the site answers at all, not how a heavy page behaved.

## Rejected alternatives

- **Probe through `compose exec`, as the health check does.** Each probe would spawn a
  process, at about the cost of the interval, and would reach whichever `backend` compose
  picked. That is not what a user's request goes through.
- **Write the record to a file under `/var/lib/cairn`.** Contradicts `BR-DEPLOY-019`; journald
  already keeps it.
- **Human-readable summary only.** The point is to compare deploys over weeks. JSON on one line
  keeps that a `grep` and a `jq` away.

## Open for Brian

1. Is `deploy record` the right marker, or should cairn's machine-readable lines share one
   prefix?
2. Should the record also go to the failure webhook (`BR-DEPLOY-020`) once that exists?

*(BR-DEPLOY-017, BR-DEPLOY-019, BR-DEPLOY-020, BR-DEPLOY-025, BR-DEPLOY-026)*
