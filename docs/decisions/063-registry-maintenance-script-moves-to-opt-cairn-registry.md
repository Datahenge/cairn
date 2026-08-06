---
status: authoritative
owner: technical
purpose: ADR-063 — the registry maintenance script moves from the invoking shell's cwd to /opt/cairn-registry
---

# ADR-063 — the registry maintenance script moves from the invoking shell's `cwd` to `/opt/cairn-registry`

**Decided:** 2026-08-05 (found during a companion review of `cairn-adopt`/`cairn-registry`,
raised right after `ADR-062` fixed the same class of bug in `cairn-build`).
**Amends:** `BR-CLI-027`, `BR-REG-010`. **Relates to:** `ADR-062`, `ADR-053`, `ADR-060`.

## The bug

`registry_provision.stage_timers_registry` wrote the generated maintenance script to
`options.workdir / "registry-maintenance.sh"`, and `workdir` defaults to `Path.cwd()` at the
moment `cairn-registry setup-timer` runs — ordinarily wherever the operator happened to be,
often a personal home directory. Same defect `ADR-062` corrected in `cairn-build`: a retired
operator account, or a home directory cleaned up after offboarding, silently breaks
maintenance automation that has nothing to do with that account.

## What's different from `cairn-build`

`ADR-062` fixed two bugs in `cairn-build` — a unit-naming collision *and* the cwd-dependent
script. Only the second half applies here: `cairn-registry-maintenance` is already a fixed,
un-parameterized unit name, and correctly so — one registry role serves one host
(`ADR-048`), with one `/etc/cairn/registry.toml`. There is no multi-tenant scenario for it to
collide against, so no naming change is needed.

## Decision

The script moves to `PROJECT_DIR` (`/opt/cairn-registry`) — the directory `cairn-registry
setup` already provisions and writes `compose.yaml` into, and the same directory `docker
compose --project-directory` already targets (`registry_provision.py`). `ADR-053` split this
role's files into `/etc/cairn` (config/secrets) and `/opt/cairn-registry` (the installed
application's own tree — FHS's actual meaning of `/opt`, not growing runtime data, which
`ADR-060` separately routed to `/var/lib/cairn-registry`). A generated maintenance script is
exactly this shape: a static file belonging to the installed application, same category as
`compose.yaml` — reusing `PROJECT_DIR` needed no new directory or convention.

`options.workdir` is unaffected in every other respect — it keeps its existing job in the
generated script's `cd {workdir}` line and the reported `workdir` line; it no longer
determines where anything is written.

## Consequences

- `stage_timers_registry` writes `registry-maintenance.sh` to `PROJECT_DIR`, not
  `options.workdir`.
- `BR-REG-010`/`BR-CLI-027` (`docs/requirements/08-registry.md`/`06-cli.md`) updated to
  state this.
- No migration path needed: `cairn-registry setup-timer` has not yet been run against a real
  host (`docs/open/OPEN_WORK.md`'s `W-015` covers `prune`/`gc` themselves, not the timer).

*(BR-CLI-027, BR-REG-010, ADR-048, ADR-053, ADR-060, ADR-062)*
