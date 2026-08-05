---
status: exploratory
owner: project
purpose: Plan for a local git mirror solving private-app reachability, blocked on ADR-044.
---

# Local git mirror for private apps (`BR-BUILD-017`)

> **Status: planned, not yet implemented.** Written 2026-07-27, downstream of `BR-BUILD-016`
> (shipped) and `ADR-044` (full record in `docs/adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md`,
> tracked live in `open/OPEN_DECISIONS.md`, deferred pending exactly this plan).

## Context

`BR-BUILD-016` (shipped) authenticates a private `github.com` app with a single operator PAT,
embedded in the `apps.json` build secret. It works, but only for repos whose owner will issue a
PAT. Brian's actual situation is a client who won't/can't issue a fine-grained PAT easily but
already has an SSH deploy key working on the builder VPS (`git@github-clientrepo:...`). That
already works for `git ls-remote` (a bare host-side subprocess, `resolve.py`) but not for the
actual clone, which runs inside an isolated BuildKit sandbox with no SSH access at all —
forwarding SSH in would mean editing the Containerfile, which was forbidden while it was
vendored read-only (`ADR-007`, now retired). Cairn owns the recipe outright now (`ADR-059`),
so this constraint no longer applies — editing the Containerfile directly is available should
this plan be picked back up.

The idea, validated in-session (`ADR-044`): mirror the private repo locally on the builder — using
the SSH credentials that already work host-side — and serve it to the build over `git://localhost`
with the build run under `--network=host`. Verified against this project's own prior research
(`ADR-015`): bench's `apps.json` handling is a plain `git clone --branch <ref> <url>` with no
scheme restriction, so `git://` works identically to `https://` from bench's side. `--network=host`
is a flag on the `docker build`/`podman build` invocation cairn already constructs — no
Containerfile change, and it makes "localhost" *literally* the host's localhost inside the build,
which is what makes this simpler than address-translation tricks like `host.docker.internal`.

Decided in this session (answers to the open questions `ADR-044` left):
- **Serve over `git://` via `git daemon`** — no CGI, no web server; git ships this specifically for
  local/trusted-network read-only mirrors like this one, and reuses the "stock image, no custom
  Dockerfile" pattern `stage_registry` already established for the OCI registry.
- **`cairn-provision --git-mirror`, opt-in** — most builders never touch a private app; unlike the
  registry (every build needs somewhere to push), nothing forces this to be on by default.
- **Refresh at the start of every `cairn build`** — a `git fetch --prune` against the true upstream
  right before the build, same timing cairn already uses for `git ls-remote`. No new timer/unit.
- **Explicit manifest field**, `mirror = true` on `[[cairn.apps]]` — not inferred from URL scheme.

This is `BR-BUILD-017` in the numbering (`BR-BUILD-016` is the last used ID). It sits alongside,
not instead of, `BR-BUILD-016` — an app can use either mechanism; `mirror = true` and a
`CAIRN_GITHUB_TOKEN`-eligible `github.com` URL are not mutually exclusive, just independently
applied at the same one seam (`BuildPlan.apps_json_secret`).

## New module: `src/cairn/mirror.py`

Owns the on-disk mirror path, the port, and the two operations:

```python
MIRROR_DIR = Path("/opt/cairn-git-mirror")   # one bare repo per app: MIRROR_DIR/<name>.git
MIRROR_PORT = 9418                            # git's own IANA-assigned git:// port

def local_url(app_name: str) -> str:
    return f"git://localhost:{MIRROR_PORT}/{app_name}.git"

def sync(app: App) -> Path:
    """Clone (first time) or fetch --prune (thereafter) into MIRROR_DIR/<name>.git, using
    app.url exactly as given — whatever host git/SSH config already authenticates it, the
    same credential already proven working for git ls-remote. Raises MirrorError on failure."""
```

`errors.py` gets a new `MirrorError(CairnError)`, parallel to `RefResolutionError`.

`provision.py` imports `MIRROR_DIR`/`MIRROR_PORT` from here for the compose file and health
check, the same import shape it already uses for `CAIRN_MANAGED_LABEL` from `adopt.py` — no
circular import risk, same precedent already in the codebase.

## `config.py`: manifest schema

- `App` (line ~77) gains `mirror: bool = False`.
- `_apps()` (line ~373): add `"mirror"` to the `_reject_unknown` allowed-keys set; read
  `entry.get("mirror", False)`, validated as a bool (same style as the existing `install_chromium`
  bool-typed knob check).
- `docs/requirements/02-build.md`: extend `BR-BUILD-002`'s field list to mention `mirror`
  (optional, default false).

## `build.py`: threading it through `BuildPlan`

- New field, **appended last** so every existing `BuildPlan(...)` construction (in `plan()`, and
  the two test fixtures in `tests/test_build.py`/`tests/test_cli.py`) keeps working unchanged:
  `mirrored_apps: tuple[App, ...] = ()`.
- `plan()` populates it: `mirrored_apps = tuple(app for app in manifest.apps if app.mirror)`. Pure
  manifest read, no I/O — safe to compute during `--dry-run`.
- `apps_json_secret` property (already exists, from `BR-BUILD-016`) extended: zip the parsed
  entries against `self.resolution.apps` (both in manifest order, `BR-BUILD-003`) instead of
  iterating alone. For an app whose `ResolvedRef.name` is in `{a.name for a in mirrored_apps}`,
  rewrite its `url` to `mirror.local_url(name)`; otherwise apply the existing
  `github_auth.authenticated()` call as today. `self.apps_json` (dry-run/provenance) stays
  completely untouched either way.
- `command()` and `cache_stage_command()`: append `--network=host` when `self.mirrored_apps` is
  non-empty. Not unconditional — a manifest with no mirrored apps keeps today's networking.
- `run()`: before `appsjson.written(...)`, call `mirror.sync(app)` for each `app in
  build_plan.mirrored_apps`. This is the one real place syncing happens — never during `plan()`,
  consistent with dry-run doing no I/O.
- `render()` (dry-run text) is untouched — it already only reads `self.apps_json`.

## `provision.py`: opt-in stage

- New argparse flag `--git-mirror` (`store_true`, default off), same shape as `--no-admin-group`.
- New `stage_mirror(runner, options)`: builder-only (same `builds(options)` guard as
  `stage_registry`); if `not options.git_mirror`, report skipped and return — the whole stage is a
  no-op by default. Otherwise: write a compose file (new `mirror_compose()` function, mirroring
  `registry_compose()`'s shape) and `docker compose up -d`, then a post-start verification (rule
  6) — exact probe command TBD against a real `git daemon` during implementation; likely
  `git ls-remote git://localhost:{MIRROR_PORT}/` and treating a protocol-level response
  (vs. connection-refused) as "listening."
- `mirror_compose()`: stock `alpine/git` image, entrypoint stays `git` (image default), `command:
  ["daemon", "--reuseaddr", "--base-path=/mirrors", "--export-all", "--listen=0.0.0.0", "--port={MIRROR_PORT}"]`,
  `labels: ["{CAIRN_MANAGED_LABEL}=true"]` (imported from `adopt.py`, same as the registry —
  `cairn adopt`'s existing label-based exclusion (`BR-CLI-020`) picks this project up for free,
  with no stage-ordering concern this time, unlike the registry/descriptor issue earlier this
  session), bind-mount `MIRROR_DIR:/mirrors:ro` (container never writes; only the host-side
  `mirror.sync()` does), port bound `127.0.0.1:{MIRROR_PORT}:{MIRROR_PORT}`.
- Add `"mirror"` to `BUILDER_STAGES` and `BOTH_STAGES` (not `TARGET_STAGES` — builder-only, like
  `registry`), and to the `STAGES` dict.

## Docs

- `docs/requirements/02-build.md`: new `BR-BUILD-017` alongside `BR-BUILD-016`, cross-referencing
  it (same-seam relationship, not a replacement). Note `--network=host` and its one-time
  verification need (default local buildx driver, not `docker-container`, so no extra entitlement
  expected — call out as assumption to confirm empirically during implementation).
- `docs/requirements/03-deploy.md`: `stage_mirror` under the `BR-DEPLOY-021` seven-point contract,
  same as `stage_registry`.
- `docs/adr/044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md` and
  `open/OPEN_DECISIONS.md`: revise `ADR-044` — the "deferred" stance was against an unscoped
  idea; record that it's now being acted on as `BR-BUILD-017`, with today's four scoping decisions
  (git://, opt-in, per-build refresh, explicit field). Whether it fully moves to
  `docs/adr/` `authoritative` status (dropping the `open/OPEN_DECISIONS.md` row) or stays open
  with updated status is a call to make once the code lands and the `--network=host` assumption
  is confirmed.
- `userdocs/reference/builder-config.md`: extend the "Private `github.com` apps" section (added
  for `BR-BUILD-016`) with the `mirror = true` alternative and when to prefer it (client won't
  issue any token, but already has/will make a deploy key).
- `docs/CHANGELOG.md`: entry recording the same reasoning as this plan's Context section.

## Tests

- `tests/test_mirror.py` (new): `sync()` clone-vs-fetch branching, failure → `MirrorError`,
  `local_url()` format — subprocess mocked, same style as `tests/test_resolve.py`.
- `tests/test_config.py`: `mirror` field parses, defaults to `False`, rejects a non-bool value,
  and unknown-key rejection still fires for a typo'd key name.
- `tests/test_build.py`: `mirrored_apps` defaults empty (existing `_plan()` fixture unaffected);
  `apps_json_secret` rewrites only the mirrored entry's URL, by position, leaving a non-mirrored
  app's URL to the existing PAT/plain path; `--network=host` present only when `mirrored_apps` is
  non-empty; `run()` calls `mirror.sync()` for each mirrored app before writing the secret
  (mock `mirror.sync`, assert call args) and never during a dry run (`plan()` alone).
- `tests/test_provision.py`: `--git-mirror` off (default) → stage reports skipped, no compose file
  written, no `docker compose` call; `--git-mirror` on → compose file carries the label and the
  right command args; stage refuses on `--role target` like `stage_registry` does.

## Verification

- `.venv/bin/python -m pytest -q` — full suite.
- `.venv/bin/python -m ruff check src/cairn/ tests/`.
- Manual, once implemented: on a real builder VPS, `sudo cairn-provision --role builder
  --git-mirror`, confirm the `git-mirror` container is labeled and running; add a `[[cairn.apps]]`
  entry with `mirror = true` pointing at a real repo reachable via the host's existing deploy key;
  run `cairn build --dry-run` (confirm `apps.json` shown is still the plain upstream URL, and the
  command shows `--network=host`); then a real `cairn build` and confirm the app actually clones
  inside the container via the local mirror.
