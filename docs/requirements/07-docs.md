---
status: authoritative
owner: requirements
purpose: BR-DOCS requirements — the published documentation site.
---

# BR-DOCS — Published Documentation Requirements

_Status: **approved** 2026-08-03 (living) · Last updated: 2026-08-03_

A high-quality, browsable documentation site for cairn's users — published from a
dedicated source tree, kept structurally separate from the internal Scribe requirements
root. Conventions: see `/CLAUDE.md`. Decisions cited: `ADR-045`.

---

**`BR-DOCS-001`** *(separate source tree)* — Published-documentation source content MUST
live in a dedicated top-level directory, `userdocs/`, and MUST NOT live inside `docs/` or
any of its subdirectories. `docs/` is the internal Scribe requirements/decisions root
(`BR`/`ADR` content that must never reach a user, per `/CLAUDE.md`); keeping the two trees
physically separate makes that boundary structural rather than a matter of authoring
discipline. *(ADR-045)*

**`BR-DOCS-002`** *(no internal identifiers in published output)* — Rendered site content
MUST NOT contain `BR-<AREA>-NNN` or `ADR-NNN` identifiers, matching the existing rule for
all user-visible cairn surfaces (`/CLAUDE.md`). Where a page's content is motivated by a
decision, it states the *reason*, not the ID.

**`BR-DOCS-003`** *(tooling)* — The site is built with **mkdocs** using the
**mkdocs-material** theme, matching the existing pattern already in production for
Datahenge's BTU project. `mkdocs.yml` lives at the repo root and its `docs_dir` points at
`userdocs/`. *(ADR-045)*

**`BR-DOCS-004`** *(publish target)* — The site is published to **GitHub Pages** at the
default project URL (e.g. `datahenge.github.io/cairn`) — no custom domain, no DNS
record to maintain. *(ADR-045)*

**`BR-DOCS-005`** *(build/deploy trigger)* — A GitHub Actions workflow builds the site
with `mkdocs build` and publishes it via the `actions/deploy-pages` action whenever
`userdocs/**` or `mkdocs.yml` changes on the default branch, and MAY also be triggered
manually (`workflow_dispatch`). It MUST NOT require any credential beyond the
workflow's own `GITHUB_TOKEN`/Pages permissions — no external hosting account, no
secrets to provision.

**`BR-DOCS-006`** *(initial scope — lean, not a migration)* — The first version of
`userdocs/` MUST stand up the working site + publish pipeline with minimal placeholder
content (e.g. a landing page and a stub nav). Restructuring the existing user-facing
docs (`README.md` at the repo root; `docs/technical/CONFIGURATION.md`,
`docs/technical/ABOUT_GHCR.md`, `docs/technical/ABOUT_REGISTRIES.md`) into
the site's nav is explicitly **out of scope** for this requirement and deferred to
later, separate work; those files remain the current source of truth for their topics
until that migration happens.

**`BR-DOCS-007`** *(no duplication of authoritative sources)* — The published site MUST
NOT restate content that already has a single source of truth elsewhere in the repo
(e.g. the requirements register, the decision log) — it may *link* to those on GitHub,
but pages are user-facing explanation, not a second copy of internal docs.

---

## Cross-references
- `/CLAUDE.md` — the identifier-visibility rule this area exists to keep structurally
  enforced (`BR-DOCS-001`, `BR-DOCS-002`).
- **Follow-up (later work):** migrating `README.md`/`docs/technical/ABOUT_GHCR.md`/
  `docs/technical/ABOUT_REGISTRIES.md` into `userdocs/`'s nav, once the site itself exists
  (`BR-DOCS-006`). `docs/technical/CONFIGURATION.md` completed this migration on 2026-08-04 —
  its content now lives at `userdocs/reference/manifest.md`, `builder-config.md`, and
  `target-descriptor.md`, and the file itself was retired rather than left as a stub.
