# docker-cairn — Phase 1: the Build pillar (`cairn build`)

## Context

`docker-cairn` wraps the vendored, pinned `frappe_docker` (v3.2.1, managed by
ventwig — see `docs/01-decisions-closed.md` ADR-007) to make a custom ERPNext
deployment reproducible and low-thought. The three pillars are build, deploy, and
data lifecycle. Deploy and backup both stand on a **reproducible, immutably-tagged
image**, so Phase 1 delivers exactly that — end to end, on the workstation, with no
VPS or registry dependency.

Today, building a custom image with `frappe_docker` means hand-writing `apps.json`,
remembering the BuildKit-secret + `CACHE_BUST` incantation, choosing a Containerfile,
and inventing a tag — with nothing recording *what went into* the resulting image.
Phase 1 replaces all of that with one declarative manifest and one command, and makes
the **cairn marker** (a durable record binding resolved inputs → image) a first-class
artifact that later deploy/rollback phases will consume.

**Scope decisions this phase assumes** (to be reflected in the decision docs):
`custom` Containerfile (ADR-004); single site per bench (ADR-016); registry deferred /
local-only, GHCR as eventual default (ADR-009); CLI command is `cairn` (ADR-018);
apps pinned to commit for immutability (ADR-015); input-hash immutable tag (ADR-011).
Out of scope this phase: deploy/reconcile, migration, backup/restore, VPS, registry
push.

## Verification target

Frappe `version-16` + **ERPNext only** (no custom app), Python 3.14.2 (matches the
`custom` Containerfile defaults). Shipped as `cairn.toml.example`. ERPNext is itself
an `apps.json` entry, so this still exercises the full resolve → apps.json → build →
tag → marker path; a trivial throwaway scaffold app can be added later to exercise the
N>1 apps case.

> **Why not `cofferdam-app` as the build PoC?** It was initially proposed for
> version-alignment reasons, but that under-read its function. `cofferdam-app` is
> restore-safety infrastructure (see the Pillar-3 note below), not a neutral build
> payload — using it here would be circular (baking a restore guard before the restore
> feature exists) and would couple the tool's first build to an alpha, in-flight app.
> It is relocated to a **Pillar-3 design input**.

---

## Architecture

### 1. Deployment manifest — `cairn.toml`
Human-friendly declaration of *what image to build*. Read with stdlib `tomllib`.

```toml
[cairn]
name = "erpnext-v16"             # logical image/deployment name

[cairn.frappe]
branch = "version-16"            # -> build-arg FRAPPE_BRANCH/FRAPPE_PATH
# url = "https://github.com/frappe/frappe"

[[cairn.apps]]                   # ERPNext and every custom app listed here
name = "erpnext"
url  = "https://github.com/frappe/erpnext"
ref  = "version-16"              # branch/tag; resolved to a commit at build time

# Later, custom apps are added as further [[cairn.apps]] entries, e.g. cofferdam-app.

[cairn.build]
python_version   = "3.14.2"
node_version     = "24.13.0"
install_chromium = true
```

### 2. Ref → commit resolution (immutability)
`resolve.py`: for each app, `git ls-remote <url> <ref>` → concrete commit SHA. These
resolved commits are what get recorded in the marker and drive the cache-bust, so a
given manifest state maps to a deterministic set of inputs. (Honest limit: this pins
*declared inputs*, not the Debian base/apt layer — it is input-deterministic, not
hermetic.)

### 3. `apps.json` generation
`appsjson.py`: compile `[[cairn.apps]]` into the `[{url, branch}]` array
`frappe_docker` expects, written to a temp file passed **only** as a BuildKit secret
(`--secret id=apps_json,src=...`) — never a build-arg (upstream security note). Frappe
itself goes via `FRAPPE_BRANCH`/`FRAPPE_PATH` build-args, not `apps.json`.

### 4. Build invocation
`build.py` + `docker.py` shell out to:
```
docker build \
  --build-arg FRAPPE_PATH=... --build-arg FRAPPE_BRANCH=version-16 \
  --build-arg PYTHON_VERSION=3.14.2 --build-arg NODE_VERSION=24.13.0 \
  --build-arg INSTALL_CHROMIUM=true \
  --build-arg CACHE_BUST=<hash of resolved app commits> \
  --secret id=apps_json,src=<tmp>/apps.json \
  --tag <image_base>:<immutable-tag> --tag <image_base>:<name>-latest \
  --file frappe_docker/images/custom/Containerfile \
  frappe_docker
```
- **Context = `frappe_docker/`** (the vendored dir has the `resources/` the
  Containerfile COPYs). The `apps.json` secret `src` is a temp file *outside* the
  context, which is fine.
- **`CACHE_BUST` = hash of the resolved app commits** (upstream technique #5, adapted):
  the app layer rebuilds exactly when app pins change — deterministic, no `--no-cache`.

### 5. Tagging (registry-agnostic, registry-ready) — ADR-011
- `image_base` defaults to `cairn/<name>` locally; a later `registry` setting makes it
  `ghcr.io/<owner>/<name>` with no other change.
- Immutable primary tag = `<name>-<inputhash>` where `inputhash` is a short digest of
  {frappe commit, each app commit, build args}. Same inputs ⇒ same tag ⇒ reproducible.
- Moving convenience tag = `<name>-latest`.

### 6. Cairn marker (first-class) — ADR-011 concept
`marker.py`: after a successful build, write `.cairn/markers/<tag>.toml` (and append an
index) recording: manifest name, resolved frappe + app commits, build args,
`image_base`, both tags, the image **digest** (`docker inspect`), the `frappe_docker`
pin from `.ventwig.lock`, and a timestamp. `.cairn/` is git-committable — markers become
the versioned history of what was built. Deploy/rollback phases will read these.

### 7. CLI (Typer) — the `cairn` command
`cli.py` wires:
- `cairn build [--manifest cairn.toml] [--no-cache] [--dry-run]` — resolve → apps.json
  → build → tag → write marker. `--dry-run` prints the resolved `apps.json`, the exact
  `docker build` command, the computed tags, and the marker it *would* write — no build.
- `cairn doctor` — preflight: Docker Engine ≥ v23 + buildx present, `ventwig status`
  clean (vendored tree unmodified), manifest valid.
- `cairn markers list` / `cairn markers show <tag>` — inspect build history.
- `cairn vendor status` / `cairn vendor sync` — thin wrappers over ventwig so vendored
  upstream management is one CLI surface.

---

## Files to create / modify

```
pyproject.toml                 # MODIFY: [project.scripts] cairn; deps typer, tomli-w
src/cairn/__init__.py
src/cairn/__main__.py          # python -m cairn
src/cairn/cli.py               # Typer app + command wiring
src/cairn/config.py            # load/validate cairn.toml -> dataclasses
src/cairn/resolve.py           # git ls-remote ref -> commit
src/cairn/appsjson.py          # manifest -> apps.json (temp file)
src/cairn/build.py             # cache-bust, tags, orchestration
src/cairn/docker.py            # subprocess helpers (docker/buildx)
src/cairn/marker.py            # .cairn/ marker read/write + index
src/cairn/vendor.py            # thin ventwig wrapper (status/sync)
src/cairn/doctor.py            # preflight checks
src/cairn/errors.py
cairn.toml.example             # v16 + ERPNext + cofferdam-app target
tests/                         # config, appsjson, marker round-trip, inputhash determinism
docs/01-decisions-closed.md    # MODIFY: close/annotate ADR-011, ADR-015, ADR-016, ADR-018
docs/02-decisions-open.md      # MODIFY: mark ADR-009 deferred (local-only Phase 1)
docs/03-discussion-log.md      # MODIFY: Phase 1 scope decisions
```

Reuse: stdlib `tomllib` (read), `tomli-w` (write markers), `subprocess` for docker/git,
and delegate all vendored-tree management to **ventwig** (already installed in `.venv`).

## Verification

1. **Unit tests** (`pytest`): `cairn.toml` parsing + validation; `apps.json` generation
   shape; marker round-trip; **inputhash determinism** (same manifest ⇒ same tag; a
   changed app ref ⇒ changed tag/cache-bust).
2. **`cairn doctor`** reports Docker/buildx present and `ventwig status` clean.
3. **`cairn build --dry-run`** on `cairn.toml.example` prints correct `apps.json`, the
   full `docker build` command, computed tags, and the intended marker — no Docker
   needed, CI-safe.
4. **Real build** (manual, needs Docker; heavy): `cairn build` on the example →
   `docker images` shows `cairn/erpnext-v16:<tag>`; a marker exists with resolved
   commits + digest; re-running unchanged reuses cache and yields the **same tag**
   (reproducibility check).

## Not in this phase (later phases, already scoped in docs)
Deploy/reconcile pull-loop (ADR-006), migration orchestration (ADR-014), backup/restore
(ADR-013) with rollback = image-only (ADR-012), desired-state pointer (ADR-010), registry
push/GHCR (ADR-009), secrets on VPS (ADR-017), multi-site (ADR-016).

## Pillar-3 design input: cofferdam outbound guard (informs later phases)

`cofferdam-app` is the outbound guard (email + Frappe webhooks) that makes
**Prod→non-prod database restore safe**, and is intended to become a required guard on
any such restore docker-cairn performs. Facts from the source that constrain Pillars 2–3:

- **Config is a local `environment_policy.toml`** (TOML, *not* YAML), at the fixed path
  `sites/<site>/environment_policy.toml` — no env-var override. That path is inside the
  persistent `sites` **VOLUME** the `custom` Containerfile declares, so the policy is
  **environment-specific runtime config, never baked into the image.**
- **Fails closed:** a missing/invalid policy blocks all outbound and logs. So policy
  *presence + validity* must become a deploy invariant (assert file exists and
  `cofferdam validate` passes before a site is called healthy).
- **Never in DB backups by design** ("restored data owns business intent; local config
  owns outbound"). Therefore Pillar-3 restore must stay DB(+files)-only and **explicitly
  never overwrite** `environment_policy.toml`, so the target env's own guard survives.
- **Per-worker cache:** live policy edits need `cofferdam_app.policy.reload_policy()`;
  a normal deploy restart picks it up automatically.

**Proposed new open decision `ADR-019` — environment-specific config management in Docker
(starting with the cofferdam policy file):** how docker-cairn provisions/versions each
environment's `environment_policy.toml` onto the sites volume, enforces presence as a
deploy invariant, and guarantees restore never clobbers it. To be opened in
`docs/02-decisions-open.md`.
