---
status: authoritative
owner: technical
purpose: ADR-068 — cairn's scope grows to include initial provisioning, not just build+reconcile against a pre-existing stack
---

# ADR-068 — cairn owns initial provisioning, not just reconcile

**Decided:** 2026-08-06
**Amends:** `BR-DEPLOY-007` (scope). **Extends:** `ADR-059` (owned recipe), `BR-VEND-001`.
**Does not touch:** the `DATA` boundary (`ADR-022`) or `BR-DEPLOY-007`'s `bench new-site`
clause — both unchanged, see "Out of scope" below.

## Raised

While trimming `src/cairn/recipe/` down to what cairn's own code actually reads
(dropping the byte-for-byte bootstrap copy's dead weight — its docs site, test suite, CI
workflows, contributor tooling, alternate build strategies), the compose scaffolding
(`compose.yaml`, `overrides/*.yaml`) turned out to be in the same boat: nothing in cairn's code
reads cairn's own copy of it either. `cairn-adopt examine`/`reconcile` inspect whatever compose
files are already on the *target* host, under whatever name and directory they happen to have —
`descriptor.py`'s `Compose.directory`/`.file` are read off the live deployment, never assumed to
be cairn's own recipe default.

That raised the question directly to Brian: is the copied compose scaffolding dead weight to
drop along with the rest of the trim? His answer was no, and reframed the session — cairn
*replacing* `frappe_docker` (`ADR-059`) was already the premise; this is the same premise
followed one step further. If cairn is the replacement, cairn should be able to stand up a
deployment with its own owned files, not just converge one that already exists using someone
else's.

## Decision

**Cairn's scope grows from "build + reconcile against an existing stack" to "build + provision +
reconcile."** Two consequences, both queued as design/implementation work rather than built now:

1. **Cairn owns the artifacts a new environment is provisioned with.** The `compose.yaml` and
   `overrides/*.yaml` kept in the recipe trim are not just reference material — they are what a
   fresh target should be stood up with, under cairn's own command surface, rather than an
   operator separately cloning `frappe_docker` to get a compose file to start from.
2. **`cairn-adopt` should eventually be able to take over ownership of a pre-existing, hand-built
   deployment** — converge its compose configuration onto cairn's own owned files, rather than
   reading its arbitrary directory and filename indefinitely the way `examine`/`reconcile` do
   today. Today's behavior (read whatever's there, forever) was the right first cut for adopting
   a host cairn didn't build; it stops being the end state once cairn is willing to provision
   the whole stack itself.

Neither of these ships in this change. Design work for both is queued as Open Work
(`docs/open/OPEN_WORK.md`) — a provisioning command's shape and how it hands off to the existing
`setup`/`examine` flow, and a take-ownership migration's safety story for a *live* site mid
conversion, both need their own design pass before any code, per this project's own
"documentation precedes code" discipline.

## Out of scope

**The `DATA` boundary (`ADR-022`) is unchanged.** `bench new-site`, database creation, and
volume creation stay the operator's act — `BR-DEPLOY-007`'s clause to that effect is not struck,
only its "existing environments only" framing is amended to make room for cairn-provisioned new
ones. This decision is about who owns the *compose/stack plumbing* — which containers run, from
which images, with which Compose files — not who creates a site or touches SQL. Called out
explicitly here because AGENTS.md marks the data-plane boundary as a hard invariant, and "cairn
now provisions deployments" is the kind of sentence that reads as a bigger claim than it is
without this line.

## Consequences

- `docs/requirements/03-deploy.md`'s `BR-DEPLOY-007` reworded in the same change: cairn's scope
  now covers provisioning new environments with its own owned Compose stack, in addition to
  converging existing ones; the `bench new-site`/database-creation clause is carried forward
  verbatim.
- Two new `docs/open/OPEN_WORK.md` items track the follow-on design/implementation: a
  provisioning command using the owned `compose.yaml`/`overrides/`, and `cairn-adopt`'s
  take-ownership migration path. Both `open`, neither `in_progress` — this decision records
  posture, not a build plan.
- `src/cairn/recipe/ATTRIBUTIONS_FRAPPE_DOCKER.md` (added the same session) documents
  `compose.yaml`/`overrides/*.yaml`/`example.env` as part of what cairn now owns and ships,
  alongside the build recipe.
*(BR-DEPLOY-007, BR-VEND-001, BR-VEND-005, ADR-022, ADR-059)*
