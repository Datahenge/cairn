---
status: archived
owner: technical
purpose: ADR-033 — The declared environment list is a `[cairn.environments]` table in the manifest
---

# ADR-033 — The declared environment list is a `[cairn.environments]` table in the manifest

**Decided:** 2026-07-25
`BR-DEPLOY-009` settled that an environment has **two halves joined only by the env tag
name**, and made the control-side declared list the source of truth that gates
`new-tag`/`retag`/`retire`. It never said where that list lives, and the pointer verbs cannot
be written without knowing.

**Decision:** it is a `[cairn.environments]` table in `cairn.toml`, mapping environment name
to registry tag:

```toml
[cairn.environments]
dev        = "dev"
production = "production"
```

**Why the manifest and not a second file.** The list is portable, shared, and belongs under
review beside the thing it points at — which is exactly what `cairn.toml` already is. It is
discovered by machinery that exists (`BR-CFG-012`, upward from the working directory), so the
common case keeps needing no flags (`BR-CLI-014`). A second file would add a discovery path,
a second thing to keep in sync, and a new way for the two to disagree.

**Why this does not contradict `BR-BUILD-001`.** That requirement calls the **image**
environment-agnostic, not the file. Nothing here reaches the image: the table names pointers
that live in the registry, and no environment name is ever baked into a build. The image
stays one artifact promoted between environments, which is `ADR-010`'s whole point.

**Why not build config.** `~/.config/cairn/builder.toml` (`config.toml` before `ADR-041`)
and `cairn.local.toml` are explicitly machine-local and uncommitted (`BR-CFG-008`). A
source of truth that gates a production retag cannot live somewhere that differs per
laptop and is absent on a colleague's.

**Consequence for the schema:** `[cairn]` accepts a fifth key, and the manifest's
unknown-key rejection must admit it. The table is optional — a manifest that only ever builds
declares no environments, and the pointer verbs then report that none exist rather than
inventing one (`BR-CLI-009`, no auto-vivification).
*(BR-DEPLOY-009, BR-CLI-004, BR-CLI-009, BR-BUILD-001, BR-CFG-008, ADR-010, ADR-015)*

**Amended 2026-08-04 (`ADR-049`):** the table itself is renamed `[cairn.declared_environments]`
— the worked example above shows the name as originally decided here and is left as the
historical record, not rewritten. Everything else on this page — putting the list in the
manifest, as a table, keyed by environment name → registry tag — is unchanged.

**Superseded 2026-08-04 (`ADR-052`):** the table itself is retired — a manifest declares at
most one environment now, as a scalar `[cairn] environment = "..."` field, not a table of any
cardinality. The reasoning above about *where* the fact lives (in the manifest, not a second
file, not build config) still holds; the *shape* it takes does not.
