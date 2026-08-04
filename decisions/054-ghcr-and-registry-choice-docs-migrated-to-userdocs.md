---
status: authoritative
owner: technical
purpose: ADR-054 — `ABOUT_GHCR.md`/`ABOUT_REGISTRIES.md` retired; content migrated into `userdocs/registry/`
---

# ADR-054 — `ABOUT_GHCR.md`/`ABOUT_REGISTRIES.md` retired; content migrated into `userdocs/registry/`

**Decided:** 2026-08-04 · **Origin:** `DOCS-01` (`open/OPEN_DECISIONS.md`)

**Problem.** `docs/technical/ABOUT_GHCR.md` and `docs/technical/ABOUT_REGISTRIES.md` were
user-facing reference material sitting in the internal `docs/technical/` tree — explicitly
flagged as deferred migration work when the `userdocs/` site was stood up (`ADR-045`,
`BR-DOCS-006`). Brian asked for that migration now, plus a `README.md` sweep for content the
new pages make redundant.

**Decision:** retired both files, not rewritten in place — same precedent as
`CONFIGURATION.md`'s 2026-08-04 retirement (`docs/CHANGELOG.md`). Content re-verified against
source and migrated:

- `ABOUT_REGISTRIES.md` → `userdocs/registry/choosing-a-registry.md` (single page — no
  natural sub-topic split).
- `ABOUT_GHCR.md` → three pages, per `DOCS-01`'s pre-approved split:
  `userdocs/registry/ghcr-setup.md`, `ghcr-ownership-and-cost.md`,
  `ghcr-tags-and-troubleshooting.md`.

Inbound references were repointed rather than left as stubs: `mkdocs.yml` nav,
`docs/technical/25-documentation-authority.md`, `docs/technical/README.md`, `AGENTS.md`,
`docs/requirements/05-config.md`, `docs/requirements/07-docs.md`,
`docs/technical/high-level-motivations-and-workflows.md`, `docs/plans/next-steps.md`,
`docs/adr/009`, `docs/adr/048`, and every `userdocs/**` page that linked to the old
GitHub-blob URLs. `README.md`'s two registry sections (`Where images are pushed`, `Where your
images live`) were consolidated into one, pointing at the published pages instead of restating
their content (`BR-DOCS-007`).

**Why retire rather than leave a stub.** `docs/technical/` is the internal Scribe tree; a
stub there pointing out to `userdocs/` would itself be exactly the kind of user-facing content
that tree isn't for. The published site is now the single source of truth for registry choice
and GHCR mechanics.

**Scope.** Documentation only, no code change. *(ADR-045, BR-DOCS-006, BR-DOCS-007)*
