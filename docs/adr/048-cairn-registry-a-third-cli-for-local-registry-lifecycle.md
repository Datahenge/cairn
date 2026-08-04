---
status: authoritative
owner: technical
purpose: ADR-048 — `cairn-registry`, a third CLI entry point for local-registry provisioning, retention, and garbage collection
---

# ADR-048 — `cairn-registry`, a third CLI entry point for local-registry provisioning, retention, and garbage collection

**Decided:** 2026-08-03
**Amends:** `ADR-046` (the same way `ADR-046` amended `ADR-018`). **Relates to:** `ADR-009`,
`ADR-036`, `ADR-038`, `ADR-039`.

Raised ahead of the first live client deployment (`open/OPEN_WORK.md`'s `W-001`), which plans
to use cairn's self-hosted local-registry option (`docs/technical/ABOUT_REGISTRIES.md`,
"Registry on the client's own VPS"). Two problems surfaced together:

1. The local registry (`stage_registry` in `src/cairn/provision.py`) is provisioned only as a
   stage of `cairn-build setup`, with a hardcoded port, no configurable storage location (an
   anonymous Docker volume rather than an operator-chosen path), and a `127.0.0.1`-only bind
   that only works when builder and target are the same machine.
2. cairn has never deleted a registry tag anywhere, by deliberate design (`cairn-build retire`
   warns rather than deletes, since one digest can carry several tags) — so every build's
   content-hash tag (`BR-BUILD-008`) accumulates in the registry forever. On a self-hosted
   registry this is unbounded disk growth with no mitigation.

**Decision.** Still **one package**, `datahenge-cairn` — a third console-script entry point,
`cairn-registry`, alongside `cairn-build` and `cairn-adopt`. Same reasoning `ADR-046` already
established for two roles told apart "by what's configured on a machine rather than by what's
installed" extends cleanly to a third: a registry host is provisioned independently, is
sometimes colocated with a builder or target (as with this client) and sometimes is not, and
its own config, retention policy, and timer cadence belong to it, not borrowed from whichever
CLI happened to provision it first.

**Registry-lifecycle code was already a clean island.** Following `ADR-018`'s own measurement
method (it justified deferring the build/adopt split by checking the target's dependency graph
for a "closed island of modules"): registry lifecycle needs only `docker compose` orchestration
and the registry's own HTTP API (`registry.py`, `ADR-036`) — it needs no `cairn.toml`, no
`[cairn.environments]`, no manifest reading of any kind. That is what makes the safety design
below possible, and it is also what makes the split cheap: nothing in `registry_config.py`,
`registry_provision.py`, or `registry_retention.py` imports `config.py` or `environments.py`.

**Command allocation:**

| `cairn-registry` |
| --- |
| `setup` (privileged) |
| `status`, `start`, `stop`, `restart` |
| `images` |
| `prune` |
| `gc` |
| `setup-timer` |
| `doctor` |

`stage_registry`/`registry_compose()` move out of `provision.py` entirely; `cairn-build setup`
no longer has a `"registry"` stage. Pre-1.0 (`0.2.0`, Alpha) and no live deployment has used it
yet (`W-001` is still open), so this is a clean cut — no deprecation shim.

**Retention is solved without tracking downstream consumers.** The question that made this
look hard: a registry has no way to know which images are "in use," the same way Docker Hub
does not track who pulled a given image. The resolution is that it doesn't need to — the
registry API deletes by **digest**, and deleting a digest removes every tag that currently
points at it (this is exactly why `cairn-build retire` already refuses to delete a tag: "a
registry version can carry several tags"). So the only safe rule, fully derivable from the
registry's own tag list with no external state:

> A digest is eligible for deletion only if **every** tag currently pointing at it matches
> cairn's own disposable content-hash shape (`<series>-<12-hex-inputhash>`, `BR-BUILD-008`).
> Any digest still carrying a moving series tag or a declared-environment tag — both plain
> names, never hash-shaped — is categorically protected, with no configuration able to
> override it.

An environment tag is created by `retag()`'s server-side manifest copy onto the *same* digest
a content-hash tag already names (`registry.py:190-211`), so checking "does this digest have
more than one tag, or a non-hash-shaped one" is sufficient — cairn-registry never reads which
environments exist. Within the eligible set, a `keep_last` floor (mirroring `BR-DEPLOY-006`'s
existing "keep last N for rollback headroom" language, applied here to the registry rather than
the target's local disk) and a `max_age_days` ceiling, both operator-configured in
`/etc/cairn/registry.toml`, decide what's actually deleted. Which tag *shapes* are eligible is
not configurable — it's a built-in invariant, since cairn itself defines that shape.

**Garbage collection is mechanical and separate from retention.** `registry:2`'s own
`registry garbage-collect` reclaims blobs after a manifest delete. It runs after toggling the
registry into read-only maintenance mode (pulls still served; pushes briefly blocked), which
`cairn-registry gc` must report before running.

**Storage becomes a configured bind mount**, not an anonymous Docker volume — `data_dir` in
`/etc/cairn/registry.toml` — closing the original complaint that an operator had no way to put
registry data on a specific disk.

**The split-trigger question doesn't apply the same way here as it did to `ADR-018`/`ADR-046`.**
Those decisions weighed splitting two roles that *could* run on the same machine forever. A
registry host is different: `ABOUT_REGISTRIES.md` already documents it as one of several
registry choices an operator picks per client, independent of where building or adopting
happens. Giving it its own binary is not a bet on future multi-machine topology — it's already
true today that "runs a registry" is a decision made per-deployment, separate from "builds
images" or "is a deploy target."
*(BR-CLI-024, BR-REG-001–BR-REG-0NN, BR-BUILD-008, BR-DEPLOY-006, ADR-018, ADR-036, ADR-038,
ADR-039, ADR-046)*
