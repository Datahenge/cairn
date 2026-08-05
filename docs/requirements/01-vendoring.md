---
status: authoritative
owner: requirements
purpose: BR-VEND requirements — cairn's owned Docker build recipe.
---

# BR-VEND — Owned Docker Build Recipe Requirements

_Status: **approved** 2026-07-21 (living — may be revised via CHANGELOG) · Last updated:
2026-08-05_

Requirements for cairn's Docker build recipe (`Containerfile`) and compose configuration.
Cairn owns this recipe directly — it is not vendored, pinned, or synced from upstream
`frappe_docker` (`ADR-059`, which supersedes `ADR-001` and `ADR-007`). Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-004`, `ADR-059`. Scope: `src/cairn/recipe/frappe_docker/`
is the single owned recipe tree.

---

**`BR-VEND-001` — Recipe ownership.** Cairn owns the Docker build recipe and compose
configuration at `src/cairn/recipe/frappe_docker/` as ordinary source. Cairn MAY create,
modify, or delete any file within it, subject to the same review discipline as any other part
of the codebase — there is no read-only restriction. *(ADR-059)*

**`BR-VEND-002` — No tracking obligation.** Cairn is under no obligation to track, pin, or
periodically sync with upstream `frappe/frappe_docker`. Consulting or borrowing from upstream
is an informal, at-will act the operator performs by hand (e.g. a manual `git clone` and diff)
when convenient — never a scheduled, automated, or tooling-mediated one. There is no pin file,
lock file, or drift check. *(ADR-059)*

**`BR-VEND-003` — Build-input completeness.** Before producing an image, cairn MUST verify the
recipe tree contains the required build inputs (at minimum `images/custom/Containerfile` and
the `resources/` it references), and MUST abort with a clear error if any are absent. This is
an ordinary sanity check on cairn's own source, not a precondition tied to any external sync.
*(ADR-004)*

**`BR-VEND-004` — No nested version-control metadata.** The recipe tree MUST NOT contain a
nested `.git` directory. This is a hygiene rule carried from how the tree was originally
bootstrapped (a one-time copy from upstream `frappe_docker`, `ADR-059`), not an ongoing sync
constraint — the recipe's own history lives in cairn's own git history from that point forward.

---

## Cross-references
- `BR-VEND-003` is enforced at build time; `BUILD` cites it.
- The command surface that once wrapped this pillar (`cairn-build vendor status | sync`) is
  retired (`ADR-059`) — there is no longer a `vendor` subcommand.
