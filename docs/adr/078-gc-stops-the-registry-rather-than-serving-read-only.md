---
status: authoritative
owner: technical
purpose: ADR-078 — gc stops the registry for the collect instead of serving read-only, amending BR-REG-009
---

# ADR-078 — `gc` stops the registry rather than serving read-only

**Decided:** 2026-09-28 (Brian, after the first real `cairn-registry gc` against the Life
Scientific registry host crash-looped the registry).

**Amends:** `BR-REG-009`. **Relates to:** `ADR-048`, `BR-REG-004`, `BR-REG-006`, `BR-REG-010`,
`BR-DEPLOY-006`.

## The incident

The first `cairn-registry gc` ever run against a live registry left the registry down. Three
successive attempts produced three different errors, none of which named the cause:

```text
FailedPrecondition: container e6d80e27… init process is not running: failed precondition
OCI runtime exec failed: exec failed: cannot exec in a stopped container
cannot exec in a stopped state
```

The container logs did name it:

```text
registry-1  | panic: readonly config key must contain additional keys
registry-1  | github.com/docker/distribution/registry/handlers.NewApp(…)
registry-1  |     github.com/docker/distribution/registry/handlers/app.go:141
```

`registry_compose()` expressed `BR-REG-009`'s read-only maintenance mode as a flattened
environment variable:

```yaml
REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED: "true"
```

distribution requires `storage.maintenance.readonly` to be a **map** containing `enabled`. The
flattened form leaves `readonly` with no nested keys, and `NewApp` panics before the HTTP server
starts. With `restart: unless-stopped` on the service, the container entered a crash loop, and
`gc`'s next step — `compose exec` into it — hit a container that was restarting, exited, or
stopped depending on timing. Hence three errors for one fault.

Two aggravating factors, both now fixed:

- **`gc()` had no `try`/`finally`.** It died at the collect and never ran its return-to-read-write
  step, so `/opt/cairn-registry/compose.yaml` was left carrying the read-only variable. Every
  subsequent `cairn-registry start` faithfully reproduced the panic. The operator had to hand-edit
  a cairn-generated file to recover — exactly what cairn exists to avoid.
- **Nothing verified the container was serving** after the recreate and before the `exec`. A
  startup panic was therefore reported as an exec failure.

## The decision

`gc` no longer reconfigures the running registry. It **stops** the registry, runs
`garbage-collect` in a throwaway container mounting the same `data_dir`, and starts the registry
again in a `finally`. It then verifies the registry is serving before reporting success.

```text
compose stop
docker run --rm -v <data_dir>:/var/lib/registry <registry image> \
    registry garbage-collect /etc/docker/registry/config.yml
compose up -d                       # in a finally
GET https://<host>/v2/              # must answer
```

Three properties follow:

1. **No `REGISTRY_*` maintenance variable is involved at all**, so the class of fault that caused
   this incident cannot recur. The registry runs in exactly one configuration, the one `setup`
   wrote.
2. **The write guarantee is stronger than read-only.** Read-only mode refuses pushes; a stopped
   registry cannot accept one. `garbage-collect` walks the blob store deleting anything no
   manifest references, and a push landing a blob before its manifest is written during that walk
   is precisely what corrupts a store.
3. **`gc` stops needing to write the compose file**, so `_write_compose`'s deliberate bypass of
   the overwrite protection every other generated file gets (`BR-DEPLOY-021` rule 3) is gone with
   it. The compose file is now written only by `setup`, through `runner.write`, under `--force`.

The throwaway container deliberately passes no environment. It uses the image's own baked
`/etc/docker/registry/config.yml`, whose `rootdirectory` is `/var/lib/registry` — which is where
`data_dir` is mounted. The one-shot container and the serving container must use the same image
for this to hold, so the image reference is now a single module constant rather than a literal in
the compose template.

## What this costs

`BR-REG-009` previously promised that **pulls continue throughout** the maintenance window,
including `cairn-adopt reconcile`'s polling. That promise is withdrawn: during gc the registry
answers nothing.

The consequence is bounded. `reconcile.current_state()` raises `ReconcileError` when
`registry.digest_of()` cannot be read, so a reconcile tick landing inside a gc window fails,
deploys nothing, and changes nothing; the timer's next tick succeeds. A target is never left
half-deployed by an unreachable registry — it is left alone. Weighed against a maintenance mode
that could not be entered at all without crashing the registry, an unavailability window a
retry absorbs is the better trade.

This is a real reduction in availability and is recorded as such rather than presented as
free.

## Alternative considered and rejected

**Keep read-only mode and fix the variable's shape** — emit
`REGISTRY_STORAGE_MAINTENANCE_READONLY: '{"enabled":true}'` so the value parses as a map. This
would have preserved `BR-REG-009` exactly as written, pulls included, and is a smaller diff.

Rejected because it keeps three liabilities the stop-based design removes outright: it still
recreates the serving container twice per gc; it still depends on distribution's environment
values being YAML-parsed into nested maps, a behavior cairn does not control and had already
guessed wrong about once; and it still leaves `gc` able to rewrite the compose file, which is
what turned a startup panic into a wedged host needing a hand-edit. Preserving a promise about
pulls was not worth retaining the mechanism that broke the registry.

## Consequences

- `BR-REG-009` is rewritten: stop, collect, restart, verify — and the "pulls continue" clause is
  struck.
- `registry_compose()` loses its `read_only` parameter; `_write_compose()` is deleted.
- `cairn-registry gc`'s operator-facing warning changes from "pushes are briefly refused" to the
  registry being briefly unavailable. Still gated behind `--yes` or `--dry-run`.
- `BR-REG-010`'s maintenance timer is unchanged — it still runs `prune` then `gc` — but its
  window is now a short full outage rather than a read-only period. Because the schedule is
  operator-chosen (`[registry.gc] schedule`, `weekly` by default), no default changes.
