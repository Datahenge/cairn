---
status: archived
owner: technical
purpose: ADR-049 — The declared environment list is `[cairn.declared_environments]`, not `[cairn.environments]`
---

# ADR-049 — The declared environment list is `[cairn.declared_environments]`, not `[cairn.environments]`

**Decided:** 2026-08-04
**Amends:** `ADR-033` (renames the table it introduced; the reasoning for putting the list in
the manifest, as a table, is unchanged).

**Problem.** `[cairn.environments]` reads as if declaring a row makes that environment exist —
it doesn't. Adding a line to this table only makes a name a legal argument to `assign-tag`/
`retire` (`BR-CLI-009`); no registry pointer is created, moved, or touched until one of those
commands runs. Raised by Brian while writing the Builder user docs: the table's own name was
the thing misleading a reader, independent of any prose fix around it.

**Decision:** rename the table to `[cairn.declared_environments]`:

```toml
[cairn.declared_environments]
dev        = "dev"
production = "production"
```

**Why this name and not `[cairn.allowable_environment_tag_names]`** (the alternative raised in
the same discussion): that name describes the table as an enumeration of tag *names* only, but
each row is a `name = "tag"` **mapping** — the key is the `<env>` argument every pointer command
takes, the value is the registry tag it resolves to, and the two are allowed to differ. A name
built only around "tag names" undersells the key side of that mapping. `declared_environments`
instead reuses the exact vocabulary the requirements already use for this table everywhere else
— "the declared environment list" (`BR-DEPLOY-009`), "the declared list" (`ADR-033`) — so the
config key now matches the term operators already read in every surrounding document, and still
carries the "declaration, not action" meaning that motivated the rename.

**Why now.** This is a breaking config-key rename, but the cheapest possible time to make it:
no client has a live `cairn.toml` yet (`open/OPEN_WORK.md`'s `W-001`, first live deployment, is
still open). Pre-1.0 (`0.2.x`, Alpha), so this is a clean cut, not a deprecation shim.

**Scope.** Requirements text (`BR-BUILD-002`, `BR-DEPLOY-009a`), the manifest parser
(`config.py`), `environments.py`, tests, and every `userdocs/` reference all update in the same
change. `ADR-033`'s own worked example is left as the historical record of what was decided
2026-07-25; it carries a forwarding note to this record rather than being rewritten.
*(BR-BUILD-002, BR-DEPLOY-009, BR-DEPLOY-009a, BR-CLI-009, ADR-033)*

**Superseded 2026-08-04 (`ADR-052`), the same day:** the table itself is retired, not just
renamed again — a manifest declares at most one environment now, as a scalar field. The naming
reasoning above (reuse "declared" vocabulary, avoid a name that undersells the mapping) no
longer applies to a scalar with nothing left to map.
