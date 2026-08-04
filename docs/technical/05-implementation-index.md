---
status: authoritative
owner: technical
purpose: Current implementation inventory — what's built, where, how tested, what remains.
---

# Implementation Index

This is a **navigation and inventory system**, not a specification. Requirements documents
specify *what's needed* (`docs/requirements/`); ADRs and decisions explain *why* (`docs/adr/`,
`decisions/`); this index answers *what exists now and where*.

**Completion is a judgment, not a grep.** Record a completion judgment in the table below the
moment one is reached — through testing, review, or discussion — even in a session with no
code change. Do not re-derive it from scratch in a later session; update this index instead.

> **Seeding caveat (2026-08-03):** this initial version is transcribed from
> `docs/plans/next-steps.md`'s already-written status notes (as of 2026-07-25) and updated only
> for the `cairn-build`/`cairn-adopt` binary split (`ADR-046`) and the `cairn-provision` →
> `setup` retirement. It is **not** a fresh audit of `src/cairn/` against current requirements.
> Treat the "Completion Judgment" column as provisional until re-verified in a follow-up
> session.

## Recommended Workflow

1. Read `CURRENT_CONTEXT.md` and this index first in a fresh session.
2. Consult the owner documents named in the "Owner Docs" column for the relevant area.
3. Jump directly to the named code location and run the validation command.
4. Never infer completion from the `Status` column alone — read the "Completion Judgment" cell.

## Index

| Area | Requirement IDs | Status | Completion Judgment | Code Location | Tests / Validation | Owner Docs | Known Next Gap |
|---|---|---|---|---|---|---|---|
| Vendoring | `BR-VEND-*` | Implemented | Judged working 2026-07-21+; drift check re-verified against `frappe_docker.pin.toml` after the in-package move (`ADR-007`, `ADR-018`) | `src/cairn/vendor.py`, `src/cairn/project.py` | `tests/test_vendor.py`, `tests/test_project.py` | `docs/requirements/01-vendoring.md` | — |
| Build | `BR-BUILD-*` | Implemented | Working end-to-end against a real registry (2026-07-25) | `src/cairn/build.py`, `src/cairn/engine.py`, `src/cairn/resolve.py`, `src/cairn/appsjson.py`, `src/cairn/tagging.py`, `src/cairn/timing.py`, `src/cairn/transcript.py` | `tests/test_build.py`, `tests/test_engine.py`, `tests/test_resolve.py`, `tests/test_appsjson.py`, `tests/test_tagging.py`, `tests/test_timing.py`, `tests/test_transcript.py` | `docs/requirements/02-build.md` | — |
| Push / registry | `BR-CLI-003`, `BR-DEPLOY-004/005` | Implemented | Registry client working; retag path **never run against a real registry** | `src/cairn/push.py`, `src/cairn/registry.py` | `tests/test_push.py`, `tests/test_registry.py` | `docs/requirements/03-deploy.md` | First live retag/rollback against a real registry |
| Images / prune | `BR-CLI-005/018` | Implemented | `cairn-build images --local` and `prune` verified on the real machine 2026-07-25; registry-side `images` **never run against a real registry** | `src/cairn/images.py`, `src/cairn/prune.py` | `tests/test_images.py`, `tests/test_prune.py` | `docs/requirements/02-build.md`, `docs/requirements/06-cli.md` | Registry-side `images` real-world verification |
| Reconcile / deploy | `BR-DEPLOY-*` | Written, unverified live | Heavily tested and mutation-checked; **never run on a real target** | `src/cairn/reconcile.py`, `src/cairn/descriptor.py`, `src/cairn/environments.py` | `tests/test_reconcile.py`, `tests/test_descriptor.py`, `tests/test_environments.py` | `docs/requirements/03-deploy.md` | First live deployment — see `open/OPEN_WORK.md` |
| Examine (formerly `adopt`) | `BR-CLI-020` | Written | Prints a descriptor read off a running stack; not yet run against a real hand-built deployment | `src/cairn/adopt.py` | `tests/test_adopt.py` | `docs/requirements/03-deploy.md`, `docs/requirements/06-cli.md` | Real-world `examine` run |
| Doctor | `BR-CLI-007` | Implemented | Role-specific checks per binary (`ADR-046` retired context-detection) | `src/cairn/doctor.py` | `tests/test_doctor.py` | `docs/requirements/06-cli.md` | — |
| systemd units | `BR-CLI-019` | Implemented | Prints units, installs nothing | `src/cairn/systemd.py` | `tests/test_systemd.py` | `docs/requirements/03-deploy.md` | — |
| Setup (privileged installer) | `BR-DEPLOY-021` | Implemented, folded into both CLIs | Was the standalone `cairn-provision`; now `cairn-build setup` / `cairn-adopt setup` per `ADR-046` — **never run on a real host** | `src/cairn/provision.py` | `tests/test_provision.py` | `docs/requirements/03-deploy.md` | First real-host `setup` run |
| Data-plane boundary | `BR-DATA-*` | Implemented (by construction) | No SQL client, no `bench execute`, no data-manipulation code path exists | (absence is the implementation — see `ADR-022`) | — | `docs/requirements/04-data.md` | — |
| Config | `BR-CFG-*` | Implemented | `/etc/cairn/` fully explicit, host-shared model (`ADR-042`) | `src/cairn/config.py` | `tests/test_config.py` | `docs/requirements/05-config.md` | — |
| GitHub auth (private apps) | `BR-BUILD-016` | Implemented | Shipped; PAT-based, redacted from output | `src/cairn/github_auth.py` | `tests/test_github_auth.py` | `docs/requirements/02-build.md` | `BR-BUILD-017` local git mirror — planned, see `docs/plans/git-mirror-private-apps.md` |
| CLI surface (both binaries) | `BR-CLI-001/002/021` | Implemented | `cairn-build`/`cairn-adopt` two-entry-point split shipped (`ADR-046`) | `src/cairn/cli_build.py`, `src/cairn/cli_adopt.py`, `src/cairn/cli_support.py` | `tests/test_cli_build.py`, `tests/test_cli_adopt.py` | `docs/requirements/06-cli.md` | — |
| Manifest home + setup-timer split | `BR-CLI-022/023` | Implemented | `cairn-build setup --client <name>` provisions `/srv/cairn/<name>/`, scaffolds a starter `cairn.toml` only if absent; `setup-timer` split off both CLIs' `setup`; `doctor` lists known manifests informationally | `src/cairn/provision.py` (`stage_manifest`, `MANIFEST_ROOT`, `MANIFEST_TEMPLATE`, `_require_root`), `src/cairn/doctor.py` (`check_known_manifests`), `src/cairn/cli_build.py`, `src/cairn/cli_adopt.py` | `tests/test_provision.py`, `tests/test_doctor.py`, `tests/test_cli_build.py`, `tests/test_cli_adopt.py` | `docs/requirements/06-cli.md`, `docs/adr/047-canonical-manifest-home-srv-cairn-scaffolding-and-setup-timer.md` | Not yet exercised against a real VPS (`W-013`) |
| Conventions guard | (project-wide) | Implemented | AST-based `BR`/`ADR` leakage guard, proven able to fail | `tests/test_conventions.py` | self | `docs/technical/00-coding-standards.md` | — |
| Published docs site | `BR-DOCS-*` | Implemented (lean scope) | Pipeline stood up with placeholder content; restructuring root docs into the nav deferred | `mkdocs.yml`, `userdocs/` | manual `mkdocs build` | `docs/requirements/07-docs.md` | Nav restructuring (deferred, `BR-DOCS-006`) |

## Cross-cutting gap

**Everything in the deploy path is unexercised against real infrastructure** as of this
seeding. It is heavily tested and mutation-checked, which establishes that it does what it was
written to do — not that what it was written to do is right. The first live run is the test
that matters; see `open/OPEN_WORK.md` for the ordered sequence.
