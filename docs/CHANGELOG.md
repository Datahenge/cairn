# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-07-21

- **Adopted Scribe Coding** (Document-Driven AI Development) as the project methodology;
  added the ground-rules contract at `/CLAUDE.md`. Established the dual identifier
  system: `BR-<AREA>-NNN` (requirements) and `ADR-NNN` (decisions/ADRs).
- **Established the living-documentation infrastructure:** created
  `docs/requirements/` with `00-overview.md` (requirements root + ToC + conventions)
  and this `docs/CHANGELOG.md`.
- Requirements areas defined: `VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`.
  Per-area requirement documents are pending Phase-2 co-creation.
- **Renamed the decision-record prefix `D-NNN` → `ADR-NNN`** across all docs
  (`ADR-001`…`ADR-018`), for an explicit, self-describing identifier that matches
  `cofferdam-app`'s ADR convention. No IDs or numbering changed — prefix only.

### Predating this changelog (context)

The following were created before the changelog existed and are its baseline:
`docs/00-project-scope.md`; the decision register `docs/01-decisions-closed.md`
(`ADR-001`…`ADR-008`, `ADR-012`) and `docs/02-decisions-open.md`
(`ADR-009`…`ADR-011`, `ADR-013`…`ADR-018`); `docs/03-discussion-log.md`; and the Phase-1
build plan `docs/plans/phase-1-build.md`. Vendored upstream `frappe_docker` pinned to
`v3.2.1` via ventwig.
