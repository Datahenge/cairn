---
status: authoritative
owner: technical
purpose: ADR-076 — cairn's primary branch is named for the ERPNext major it supports (version-16 today); there is no main branch
---

# ADR-076 — The primary branch is `version-NN`, tracking the ERPNext major

**Decided:** 2026-08-20 (Brian).
**Amends:** nothing. `BR-DOCS-005` already says "the default branch" rather than naming one,
so this decision makes an existing requirement true rather than changing it.

## Raised

Brian: *"I want `version-16` to be the primary branch. Cairn has to stay 'pinned' to the ERPNext
target it's currently supporting."*

Raised while reviewing why none of three weeks' user-documentation work had reached the
published site: `.github/workflows/docs.yml` triggered on pushes to `main`, and all the work
was on `version-16`, 53 commits ahead. Repointing the workflow was the immediate fix, but the
branch model underneath it had never been stated anywhere.

## Decision

**cairn's primary branch is named for the ERPNext major version it supports.** Today that is
`version-16`. A future ERPNext major gets its own `version-17` branch, and that branch becomes
primary when cairn's support moves.

**There is no `main` branch.** The existing one — 53 commits behind, missing two user-doc pages
entirely — is deleted once the GitHub default branch flips, rather than left as a stale
ancestor that clones and inbound links would silently resolve to.

This mirrors the convention cairn already consumes: `frappe/frappe` and `frappe/erpnext` both
name their release branches `version-15`, `version-16`, and manifests reference those refs
directly. A tool whose whole job is pinning an ERPNext build should not itself float on a
branch named for no version in particular.

**Why not a `main` that tracks the current major?** Because it would have to be re-pointed at
each ERPNext major anyway, and in the interim it makes two branches claim to be current. The
version-named branch already carries that information in its name; a `main` alongside it adds
a second answer to the question "which line am I on?" without adding a fact.

## Consequences

- `.github/workflows/docs.yml` triggers on `version-16` instead of `main`. **Ordering matters:**
  the `github-pages` environment restricts deployments to the default branch, so the GitHub
  default must be flipped *before* the first push, or the deploy job fails on permissions
  rather than on anything in the site.
- `mkdocs.yml`'s `edit_uri` becomes `edit/version-16/userdocs/`, so the site's "edit this page"
  links resolve.
- `pyproject.toml`'s `Changelog` project URL and `userdocs/registry/index.md`'s link into
  `docs/requirements/08-registry.md` both move off `blob/main/`. Links to
  `frappe/frappe_docker`'s own `blob/main/` paths are upstream's branch and stay as they are.
- Each future ERPNext major is a branch cut plus the same four edits, and the deletion of the
  prior primary branch is *not* implied — an older `version-NN` may legitimately outlive its
  successor's cut while clients are still on it.
- Any external link to a `Datahenge/cairn` `main` URL breaks. Accepted: the repository has no
  published permalinks that predate this, and a broken link is a better signal than a stale
  page that renders as though current.

*(BR-DOCS-004, BR-DOCS-005)*
