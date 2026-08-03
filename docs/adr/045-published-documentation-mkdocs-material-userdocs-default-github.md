---
status: authoritative
owner: technical
purpose: ADR-045 — Published documentation: mkdocs-material, `userdocs/`, default GitHub Pages URL
---

# ADR-045 — Published documentation: mkdocs-material, `userdocs/`, default GitHub Pages URL

**Decided:** 2026-08-03

cairn's `docs/` directory is the internal Scribe requirements/decisions root — `BR`/`ADR`
content that `/CLAUDE.md` forbids from reaching a user. A published, browsable
documentation site therefore needs a source tree that cannot be confused with it.

**Decided:**
- **Source tree:** a new top-level `userdocs/` directory, sibling to (not nested under)
  `docs/`. Physical separation makes the never-leak-an-ID rule structural rather than a
  matter of authoring discipline.
- **Tooling:** mkdocs + the mkdocs-material theme — the pattern already proven in
  production for Datahenge's BTU project (same nav conventions, same CI shape, nothing
  new to learn).
- **Publish target:** the default GitHub Pages project URL (e.g.
  `datahenge.github.io/cairn`), not a custom domain. No DNS record to provision or
  maintain, and it works regardless of the repo's visibility settings.
- **Initial scope:** stand up the site and its publish pipeline with lean placeholder
  content only. Restructuring the existing root-level docs (`README.md`,
  `CONFIGURATION.md`, `ABOUT_GHCR.md`, `ABOUT_REGISTRIES.md`) into the site's nav is
  explicitly deferred — separate, later work, once the pipeline itself exists.

See `docs/requirements/07-docs.md` (`BR-DOCS-001` through `BR-DOCS-007`).
