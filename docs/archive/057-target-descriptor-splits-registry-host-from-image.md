---
status: authoritative
owner: technical
purpose: ADR-057 — the target descriptor splits registry_host from image
---

# ADR-057 — the target descriptor splits `registry_host` from `image`

**Decided:** 2026-08-04

**Problem.** The target descriptor's `image` field held a full `<registry>/<namespace>/<name>`
string — registry host and repository glued together. Raised by Brian, live on a client VPS:
copying `cairn-registry images`' repository line into `image` and hand-editing `tag` produced a
descriptor `cairn-adopt doctor` correctly refused (`registry.parse_ref` requires an explicit
host) — because there was no separate field for the host to go in, and the combined string was
easy to under-fill by hand. Brian's framing: a key named `image` that's actually two things
combined into one isn't correct, for the same reason the manifest side never does this.

**Decision:** `Descriptor` gains `registry_host: str | None = None`, sibling to `image`/`tag`/
`site`. `image` now holds the repository path alone (e.g. `acmecorp/erpnext-v16`), never a host.
Two new properties assemble the full reference at the point of use rather than storing it
pre-joined: `repository` (`registry_host/image`, or just `image` if `registry_host` is absent)
and `reference` (`repository:tag`) — every existing consumer (`reconcile`'s `CUSTOM_IMAGE`,
`docker image inspect` digest matching, `doctor`'s registry check) already called `.reference`
or now calls `.repository`, so the schema split has almost no call-site fallout.

**`registry_host` is optional, not required — mirroring the manifest's own `[cairn.registry]
host` (`BR-CFG-014`), also optional.** Absent means Docker Hub, exactly as `docker pull` itself
interprets a hostless reference. This isn't a hypothetical: the same live VPS's first-ever
`examine` surveyed a pre-cairn deployment running the public `frappe/erpnext:v16.26.1`, which
genuinely names no registry host at all. Requiring the field would force a fabricated value onto
a descriptor describing a fact, not an assertion — `cairn-registry`'s own registry-write path
(`registry.parse_ref`, `BR-CFG-009`) is the right place to insist on an explicit host, and stays
unchanged; a target's descriptor is a different kind of statement.

**`registry.split_host()` added as `parse_ref`'s lenient sibling.** `examine`'s
`_survey_image` needed the same "is this segment a host" heuristic `parse_ref` already used, but
without `parse_ref`'s hard requirement that one be present — extracted into a shared
`_looks_like_host` predicate rather than duplicated.

**`cairn-registry images`' output split to match**, same session: `Registry <host>` printed
once, `Repository <name>` per line — not one string glued together repeated on every
repository, the shape that had made the host easy to miss copying by hand in the first place.

**Consequences.** Backward compatible: `registry_host` absent, `image` holding a full
`host/namespace/name` string, behaves exactly as before the split (`repository` falls back to
`image` alone). No live client has installed a descriptor yet (`open/OPEN_WORK.md`), so this is
a clean schema addition, not a migration.

**Scope.** `src/cairn/descriptor.py`, `src/cairn/adopt.py`, `src/cairn/reconcile.py`,
`src/cairn/registry.py`, `src/cairn/cli_registry.py`. `BR-DEPLOY-010`/`BR-DEPLOY-010a` (the
descriptor's field-level shape lives in `userdocs/reference/target-descriptor.md`, not spelled
out in the requirement text itself, so no `BR` wording changed) and `BR-REG-005` (registry/
repository line split).
