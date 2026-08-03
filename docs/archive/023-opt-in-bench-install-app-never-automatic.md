---
status: archived
owner: technical
purpose: ADR-023 — Opt-in `bench install-app`; never automatic
---

# ADR-023 — Opt-in `bench install-app`; never automatic

**Decided:** 2026-07-24
Adding an app that is present in the image but not yet installed on a target **site**
requires `bench install-app` — which `bench migrate` does not do (migrate only patches
already-installed apps). To let an operator activate such apps **without SSHing into the
box**, cairn provides an **explicit opt-in** path to run `bench install-app <apps>` on the
target.

**Rules:**
- It MUST **never** run automatically. A default deploy is code-swap + `migrate` only and
  MUST NOT change a site's installed-app set (least surprise — Brian's directive).
- Like `migrate`, `install-app` is a sanctioned Frappe command cairn invokes **opaquely**
  (Frappe does the work; the "how" is none of cairn's business).
- The opt-in is delivered through the target's own reconcile/one-shot tooling (not the
  laptop reaching in), preserving the pull model (`ADR-005`/`ADR-006`). The exact delivery
  mechanism and any prod-specific confirmation are `DEPLOY` concerns.

**Motivating case:** deploying a 5-app image (frappe, erpnext, btu, life_scientific,
life_scientific_migration) to a TEST site that currently has only frappe + erpnext
installed — the three new apps' *code* ships in the image and `apps.txt` updates, but they
remain inert until `install-app` runs.

**Superseded 2026-07-25 (`ADR-037`):** the opt-in path this decision proposed is struck
entirely, not merely gated further — see `ADR-037` and `BR-DEPLOY-003a`. Activating a
newly-shipped app is now always a manual, by-hand operator act; cairn carries no path to it
at all, opt-in or otherwise.
