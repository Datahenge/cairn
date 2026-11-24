---
status: exploratory
owner: technical
purpose: ADR-081 — opt-in hot swap; migrate from the new image first, then start the new web containers beside the old ones before retiring them
---

# ADR-081 — Hot swap migrates first, then replaces the web tier side by side

**Proposed:** 2026-11-17 (Life Scientific, contributed as a pull request; awaiting Brian).

**Adds:** `BR-DEPLOY-025`. **Amends:** `BR-DEPLOY-003`, `BR-DEPLOY-016` (both now name
`recreate` as the default strategy). **Relates to:** `ADR-014`, `ADR-025`, `ADR-037`.

## Context

`reconcile` recreates the stack in place (`BR-DEPLOY-016`): `compose up -d` stops each old
container and starts its replacement, then `bench migrate` runs in the new `backend`. Two gaps
follow, and both are visible to users:

1. The site is down from the moment the old `backend` stops until gunicorn has booted the new
   one, preloaded Frappe, and the frontend can reach it.
2. The new code serves requests before `bench migrate` has run, against the old schema.

Life Scientific runs user acceptance testing on its staging target. Every converge there
interrupts the testers.

## Decision

A new optional descriptor table, `[deploy] strategy`, with `recreate` (the default, today's
behavior unchanged) and `hot-swap`. Under `hot-swap`, a pass with a running stack does this:

1. **Pull**, as today.
2. **Preflight, before any change.** Read the rendered compose file. If `backend`,
   `websocket` or `frontend` publishes a host port or sets `container_name`, a second
   container cannot start, so halt and change nothing. If the new image's `apps` directory
   differs from the running image's, take the recreate path for this pass and say so:
   `apps.txt` lives in the shared sites volume, so old and new code cannot both match it, and
   adding an app is the operator's act (`ADR-037`).
3. **Configurator and migrate from the new image**, as `compose run --rm --no-deps` one-off
   containers, while the old stack keeps serving. Migration still follows every image enable;
   it now happens before the new code takes traffic. The old code meets a schema that only
   gained objects (`ADR-014`).
4. **Start the new web containers beside the old ones**, in the order `backend`, `websocket`,
   `frontend`, with `compose up -d --no-deps --no-recreate --scale <service>=<n+1>`. Each must
   answer before the next starts. The new `backend` is probed from inside itself, because the
   service name resolves to both containers during the swap. `frontend` is last because its
   nginx resolves `backend` once, at start.
5. **Retire the old containers**: `frontend` first, so no new request reaches the old
   `backend`, then `backend` with a 30 second stop grace for gunicorn. Reload the new frontend's
   nginx at once, so it stops addressing the old backend, then retire `websocket`. On Life
   Scientific's production target a reload after the `websocket` step left about 30 seconds of
   hung requests: the removed backend's address answers nothing, so nginx waits for its connect
   timeout instead of failing over.
   Then drop Frappe's cached asset map (`frappe.client_cache.delete_value("assets_json", shared=True)`).
   With developer mode off, Frappe 16 keeps `assets.json` in Redis with no expiry, and the
   Redis volume outlives the deploy; on Life Scientific's staging target the Desk then named
   the previous image's bundles and rendered unstyled. It is dropped only once the old backend
   is gone, because the old backend can write its own map back while it still serves. The
   recreate path drops it after migrating, for the same reason.
6. **Recreate the other services that run the image** (workers, scheduler) in place. Only one
   scheduler runs at a time.
7. **Verify health**, as today.

A first deploy, or a stack that is down, has nothing to keep serving and takes the recreate
path whatever the descriptor says.

**A candidate that never answers** is removed, with every candidate started before it, and
the pass halts and reports (`ADR-025`). The old containers never stopped, so the old code keeps
serving. This is cleanup of a container that never took traffic, not a rollback: the image was
never enabled, and the migration is not undone.

The recipe's entrypoint no longer removes and recreates `sites/assets` when the link already
points at the container's baked assets. Without that, every new container started during a
swap would remove the link under the running frontend for a moment.

## What it does not do

- **Mixed versions for a few seconds.** Between step 4's `frontend` and step 5, old and new
  code both serve. A page rendered by one version can ask for JS or CSS bundles that the other
  frontend does not have. This happens only when the bundles changed in the release. Removing
  it needs paired blue/green stacks, which the compose layout does not offer today.
- **The outer proxy must resolve `frontend` per connection.** Caddy and Traefik do. A Caddy
  `lb_try_duration` lets a request that lands as the old frontend stops retry instead of
  failing.
- **Workers are recreated in place.** They get SIGTERM and Docker's stop grace period. A long
  job needs the operator to set `stop_grace_period` on the queue services.
- **Not verified on a live target.** The sequence is unit-tested against a fake compose
  project. Compose's `--scale` with `--no-recreate` is expected to keep the old container and
  add one from the current definition; that needs confirming on a real host.

## Rejected alternatives

- **Hot swap as the default.** It asks more of the compose file and has not run on a real
  target. Opt-in keeps every existing descriptor converging as it does now.
- **Migrate after the swap, as `recreate` does.** That keeps the window where new code serves
  an old schema, which is the window this decision exists to close.
- **Restart only gunicorn inside the running container.** The image is immutable; new code
  means a new container.

## Open for Brian

1. **Paired blue/green** to remove the mixed-version window: worth the compose changes, or is
   a few seconds acceptable?
2. **The 30 second stop grace** for the old web containers: a constant, or a descriptor key?
3. **Removing a failed candidate**: is that consistent with "never roll back", or should the
   pass leave it running for inspection?

*(BR-DEPLOY-003, BR-DEPLOY-003a, BR-DEPLOY-016, BR-DEPLOY-018, BR-DEPLOY-025, BR-VEND-001)*
