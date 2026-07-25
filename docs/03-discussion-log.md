# Discussion Log

Chronological summaries of the design conversation — the reasoning behind the
decisions, so future readers (and future sessions) don't have to re-derive it.

_Last updated: 2026-07-25_

---

## 2026-07-25 — First real build: transcripts, timing, and three execution contexts (ADR-031)

Brian ran `cairn build` for the first time and reported three things: the output was a
very long wall of text, awkward to scroll, and **lost unless he had thought to `tee`**;
the build took an unknown-but-long time because nothing reported duration; and it was
slow enough to make him want staged, reusable images (parked — see the next entry).

**The transcript collided with an approved decision.** `BR-DEPLOY-019` and `ADR-026` said
cairn MUST NOT write custom log files, full stop. First proposal was to narrow `ADR-026`
to "the target side."

**Brian rejected that as too simplistic**, and was right. Narrowing by *location* ignores
a third case: an **unattended CLI** build in CI (GitHub Actions on a branch push), where
the filesystem is ephemeral and a file is again the wrong answer. His three-way split —
target daemon / attended CLI / unattended CLI — became `ADR-031`.

Sharpening that fell out of it: the discriminator is not *where* the build runs, nor even
whether a human is present, but **whether something else already owns and retains the
record**. journald owns it on a target; the CI system's log viewer owns it in Actions
(with search, permalinks and retention); on a workstation **nobody** does. Note the CI
rationale is *not* "we cannot write there" — Actions has a writable filesystem — but that
the runner is ephemeral and the stream is already captured better than we could.

Two findings shaped the implementation:
- **One `isatty()` on stderr resolves all three contexts.** Neither journald nor a CI
  runner allocates a TTY. Three contexts, two behaviors, one test — with
  `--transcript`/`--no-transcript` as the escape hatch when the proxy is wrong.
- **The scrolling complaint was not about volume.** BuildKit's default `--progress=auto`
  redraws lines in place with ANSI escapes, which is precisely why scrollback was useless
  — and would have turned a teed file into control-character soup. Attended builds force
  plain progress; the other two contexts already default to it with no TTY.

**Location.** `~/.local/state/cairn/builds/` was proposed and rejected by Brian as
"buried and my human brain will forget the path"; cwd rejected as wrong. He was drawn to
`/tmp` for memorability and self-cleaning. Settled on `/tmp/cairn-<uid>/` (uid-scoped and
`0700` against `/tmp` symlink games on shared hosts), a `last-build.log` symlink so the
real filename never has to be typed, and — the actual fix for forgetting — **printing the
path at both start and end**, so it survives a Ctrl-C or a lost terminal. `transcript_dir`
in build config buys durability for anyone wanting history past a reboot. Transcripts are
disposable diagnostics, not project artifacts, consistent with `BR-BUILD-011` keeping
byproducts out of source trees.

**Timing** (`BR-CLI-017`): start, end, total, and per-phase, to terminal and transcript —
but deliberately **not** into provenance labels. Duration is a property of a *run* (cache
state, machine, network), not of the image's inputs, and inputs are what `BR-BUILD-013`
guarantees. Per-phase timing is also the prerequisite for the staging decision below.

## 2026-07-25 — Multi-image staging: where cairn can and cannot make builds faster

**Parked for now** — recorded so the analysis is not re-derived. Prompted by Brian's
first real `cairn build`, which took long enough that he proposed splitting the build
into a sequence of images, each content-addressed, so a later step could reuse an
earlier step whose hash was still valid.

The proposal is sound in principle. Reading the vendored
`frappe_docker/images/custom/Containerfile` shows that **half of it already happens**
and the other half is blocked upstream.

### What the Containerfile actually does

Three stages:

| Stage | Work |
| --- | --- |
| `base` | `python:${PYTHON_VERSION}-slim-${DEBIAN_BASE}`, apt packages, nvm + Node, yarn/pnpm, wkhtmltopdf, optional Chromium, `pip install frappe-bench`, nginx fixups |
| `builder` | build-time apt deps, then **one** `RUN` performing the whole app install |
| `backend` | `COPY --from=builder` the finished bench, move assets, entrypoints |

### Finding 1 — the expensive base is already cached

`ARG CACHE_BUST` is declared in `builder`, *after* every instruction in `base`. A build
arg only invalidates cache from its declaration point onward, so a changed app commit
does **not** rebuild `base`. Apt, Node, wkhtmltopdf and Chromium are paid once per
*base-knob* change, not once per build. This confirms in mechanism what the
2026-07-21 `layered vs custom` entry asserted when `ADR-004` was taken.

Consequence: cairn building its own separate "step 1 base image" would duplicate what
BuildKit's layer cache already provides locally. It would only add value across
machines — which is the registry-cache option below, not a staging redesign.

### Finding 2 — apps cannot be split, and that is the whole problem

The entire app install is a single atomic layer:

```dockerfile
RUN --mount=type=secret,id=apps_json,... \
  : "${CACHE_BUST}" && \
  bench init ${APP_INSTALL_ARGS} --frappe-branch=${FRAPPE_BRANCH} \
    --frappe-path=${FRAPPE_PATH} ... /home/frappe/frappe-bench && ...
```

Frappe clone, *every* app clone, all pip installs, and the yarn/esbuild asset build
happen inside that one `RUN`, guarded by one `CACHE_BUST`. There is **no seam** between
Frappe and the apps, or between one app and the next.

So the sequenced-image model cannot be built for apps without editing the Containerfile
— forbidden by `BR-VEND-004`, ruled out by `ADR-001`. Obtaining it means reopening
`ADR-021` (deliberate fork), whose recorded cost is transferring frappe_docker's
continuous maintenance of a correct recipe onto us. Not justified without measurements.

This is also why `BR-BUILD-007`'s all-inputs `CACHE_BUST` is not over-broad: upstream
offers exactly one cache-bust knob covering exactly one layer. A per-app hash would have
nowhere to attach.

### Options available without a fork

1. **Registry-backed cache** (`--cache-to` / `--cache-from`). No help for a warm local
   rebuild; large help for a **cold** machine — CI, a new workstation, a pruned cache.
   Mature in buildx; weaker in podman, which `ADR-027` requires us to keep supporting.
2. **Short-circuit on an unchanged input hash.** `BR-BUILD-008` makes the primary tag
   `<legible>-<inputhash>` immutable and unique over *all* resolved inputs. If that exact
   tag already exists locally or in the registry, the build is provably redundant: cairn
   can report it and exit 0 in about a second instead of handing a no-op to the engine.
   Cheap, no fork, and it makes the common "did I already build this?" case instant.
   This is Brian's reuse instinct applied where cairn actually holds authority.
3. **`images/layered/Containerfile`** — also vendored; identical to `custom` except it
   starts `FROM frappe/build:${FRAPPE_BRANCH}` and `frappe/base:${FRAPPE_BRANCH}`,
   skipping the base build. **Rejected**, and not merely on speed: `ADR-004` already
   turned it down because those published tags are *mutable*, which defeats
   reproducibility. It also does nothing for the `bench init` layer — the actual cost —
   and would render `PYTHON_VERSION`, `NODE_VERSION`, `INSTALL_CHROMIUM` and the
   wkhtmltopdf knobs inert.
4. **`--target base` prebuild.** Pointless locally; BuildKit already caches that stage.

### Recommendation

**Instrument first.** We do not know how the elapsed time splits between apt/Node/
Chromium, the Frappe clone, pip installs, and the asset build. If assets dominate,
no restructuring helps — nothing caches a yarn build. If the base dominates, it is
already solved. Per-phase timing (agreed the same day, terminal + transcript) is the
prerequisite for this decision, not an unrelated nicety.

Once measured, the durable facts about frappe_docker's cache seams belong in
`04-lessons-learned.md` marked *measured*, and the fork question — if it is still live —
belongs in `02-decisions-open.md` against `ADR-021`. Option 2 is worth doing regardless
of the outcome and needs a `BR-BUILD` requirement of its own.

## 2026-07-24 — Requirements clarity audit

Audited all six requirement docs to be crisp normative statements — migrated inline
rationale, mechanism, verification, and justification into the cited ADRs / this log,
keeping IDs and citations stable (approvals stand; this is a clarity revision). Rationale
trimmed from BRs and retained in ADRs/here includes: the bench `git clone --branch`
mechanism (→ `ADR-015`); provenance "labels travel with the image / registry is the store"
(→ `ADR-011`, `BR-CFG-011`); the configurator/entrypoint volume-reconcile specifics (→ the
2026-07-24 TEST 2→5 entry below); "`migrate` is non-destructive, hence safe" (→ `ADR-014`);
and the sequencing details — **in-place recreate accepts brief downtime** (true blue-green
isn't feasible on one shared `sites` volume + DB, single-host `ADR-002`), and **`bench
migrate` on rollback is safe/idempotent** (already-run patches are recorded and skipped;
older code runs no newer patches; newer schema objects sit unused per no-drop —
`ADR-014`/`ADR-012`).

## 2026-07-24 — CLI drafted; verb model + GHCR delete reality

Designed the `CLI` verb set with Brian's refinements: **`build` just builds** (`--push`
opt-in); **`deploy` → `push`** (GitHub-shared "push to cloud"); **`promote`+`rollback`
collapse into `retag <env>`** with `--latest|--previous|--id|--from` selectors (`--from`
= cross-env promotion). Added **typo-guards**: `new-tag` errors if the env exists; `retag`
errors if it doesn't (no auto-vivification) — source of truth is a **declared environment
list** (sharpened `BR-DEPLOY-009`).

Deletion: Brian asked how tags are deleted. **Verified against GitHub's own docs** that GHCR
deletion is **version-based only** (no per-tag delete; deleting a version removes the image
+ all its tags; public >5,000-download versions can't be deleted). Since an env tag shares
its version with the immutable tag, you *cannot* remove just the env pointer. So a
`delete-tag` would lie — reframed to **`cairn retire <env>`**: decommission from cairn's
declared list, touch no images, and plainly warn the GHCR tag name lingers (inert). Wrote
`BR-CLI-001`…`015` (drafted); recorded the GHCR facts in the deferred cleanup note.

## 2026-07-24 — Single package; naming = datahenge-cairn (ADR-018 closed)

Confirmed cairn stays **one package/repo** (two roles — build/control + reconcile — are
modes of one tool; role separation is enforced by credentials, not code split; build
heaviness is external binaries, not Python deps). Packaged as a pip wheel; `cairn reconcile`
runs under systemd on targets. Split deferred behind an explicit trigger. Naming: `cairn`
is taken on PyPI, and `docker-cairn`/`frappe-cairn` falsely imply Docker/Frappe ownership,
so distribution + repo = **`datahenge-cairn`** (signals Datahenge; doubles the stone motif),
import package `cairn`, command **`cairn`** (+ alias). Renamed prose `docker-cairn` → `cairn`
and the local dir → `datahenge-cairn`; remote left for Brian to recreate later. Closed
**`ADR-018`**.

## 2026-07-24 — DEPLOY opened: pull model, pointer ops, introspection, GC (ADR-010, ADR-024)

Worked through the deploy model. Settled and drafted `BR-DEPLOY-001`…`008`:
- **Pull model mechanics** — the registry is a passive bulletin board; the **target polls**
  the env tag's digest (outbound, cheap); GHCR never contacts the box. Explained why (no
  inbound, self-healing). Closed **`ADR-010`**: desired-state pointer = the environment's
  **moving registry tag**; laptop advances it by server-side retag.
- **Tags** — clarified: many immutable images coexist; each env tag (`:dev/:test/:staging/
  :production`) points at exactly one image at a time; moving a tag doesn't delete the old
  image → rollback = repoint.
- **Don't-reinvent-wheels check** → **`ADR-024`**: reconcile is a thin orchestrator over
  docker/compose + registry API + systemd. Flux/Argo rejected (k8s, `ADR-002`); Watchtower
  rejected (per-container not per-stack; would run migrate 5×; recreates outside compose;
  no env/migrate/install-app/health concept). Polling is trivial to implement; the
  single-host Frappe orchestration is the actual value and has no off-the-shelf tool.
- **Pointer ops** (`BR-DEPLOY-004`) — deploy/promote/rollback are one primitive (repoint a
  tag to an existing image, no rebuild), done as a server-side retag (`docker buildx
  imagetools`/crane/skopeo).
- **Introspection** (`BR-DEPLOY-005`) — `cairn images`/`tags` reads provenance **labels
  remotely without pulling**; the registry is the marker store.
- **GC** (`BR-DEPLOY-006`) — timer-driven prune of old images + stopped containers,
  keep-last-N for rollback headroom; **MUST NEVER touch volumes** (`ADR-022`). GHCR-side
  cleanup deferred as a separate opt-in command (destructive — erases rollback targets).

**Environment model** (`BR-DEPLOY-009`/`010`): an environment is two disconnected halves
joined only by the env tag — a thin control-side (laptop knows registry + env→tag names,
never the target's address) and a substantial target-side **descriptor** on each host.
Chose **(a)**: cairn **renders** the compose stack from the declarative descriptor
(overrides, domain, ports, site, secrets *reference*), rather than the operator
hand-writing compose YAML — the friction-removal cairn exists for.

**Secrets (`ADR-017`, closed):** cairn is **secret-agnostic** — references/wires but never
stores, generates, or handles secret values. Registry pull auth on a target = `docker
login` (Docker's cred store); DB/app secrets via **Docker secrets**
(`compose.mariadb-secrets.yaml`) recommended, `.env` supported; site secrets off-limits.
**Multi-site (`ADR-016`, closed):** single site per environment; multi-site deferred.
**Prod safeguards (`BR-DEPLOY-015`):** moving a `:production` pointer requires explicit
"are you sure?"/flag; `install-app` to prod doubly explicit.

Only **sequencing/health detail** remains open in DEPLOY (plus the deferred GHCR-side
cleanup command).

## 2026-07-24 — TEST 2→5 apps scenario: install-app (opt-in) + volume-write accuracy

Brian posed a concrete case: build a 5-app image locally (frappe, erpnext, btu,
life_scientific, life_scientific_migration) and deploy it to a TEST VPS currently running
a 2-app image. Two findings from the vendored startup scripts:
- **Volume writes are frappe_docker's, not cairn's.** The `configurator` service runs
  `ls -1 apps > sites/apps.txt` + `bench set-config -g …`, and `main-entrypoint.sh`
  relinks `sites/assets`, at every `compose up`. So the volume *does* change on deploy, but
  Frappe's own containers do it — not a violation of "cairn doesn't write volumes." Refined
  `BR-DATA-006` to say so explicitly (Brian: "explicit and accurate is always my
  preference").
- **`migrate` ≠ installing new apps.** The 3 new apps' code ships and `apps.txt` updates,
  but they stay inert until `bench install-app` runs (a DB mutation `migrate` won't do).
  Brian's ruling: least surprise — never auto-install; provide an **opt-in** path so he
  needn't SSH. Captured as **`ADR-023`** + `BR-DATA-008`; delivery via the target's
  reconcile (pull model), a `DEPLOY` detail.

## 2026-07-24 — Data-plane boundary: cairn ships code, not data (ADR-022)

Grounded first: verified `bench backup` emits `site_config_backup.json` **including the
data `encryption_key`** (real v15 backup), and that `bench restore` does *not* auto-apply
it; also clarified two distinct keys (site data `encryption_key` vs backup-file GPG key).
I had begun designing a selective encryption_key merge for cross-env restore — Brian then
**ruled that entire domain out of cairn.** New feature boundaries:
- **Feature 1** = build image + deploy (code only; no SQL export/import/awareness).
- **Feature 2 (Prime Directive)** = cairn **cannot** directly alter any DB — impossible by
  construction; DB movement between environments is cofferdam's/operator's domain.
- **Feature 3** = volumes, site configs, `encryption_key` are *aware-but-untouched*.

**`bench migrate` ruling:** the sole sanctioned DB interaction. cairn MUST run it in a
subprocess right after an image/container swap (all envs incl. Prod). It's required
(else code assumes a missing schema — worse), sanctioned (a normal Frappe command; the
"how" is Frappe's business), and non-destructive (never drops columns/tables/indexes).
"cairn doesn't alter SQL; Frappe does."

Captured: **`ADR-022`** (code/data-plane boundary), closed **`ADR-014`** (bench migrate =
sole DB interaction) and **`ADR-013`** (backup/restore/DB-movement out of scope). Wrote
`DATA` as a boundary area (`BR-DATA-001`…`007`, drafted). Reconciled the ripples:
reframed Pillar 3 in the project scope; revised approved `BR-CFG-005`/`006` (no
two-classes action; no volume seeding); removed "DB snapshot" from the cairn-marker
concept.

## 2026-07-23 — CFG build config approved; ADR-009 closed (GHCR)

Brian signed off build config: cairn never stores registry credentials, but MAY read a
token from env / a local env file to perform a *transient* `docker login` (`BR-CFG-010`
refined). Config location (user-level `~/.config/cairn/config.toml` + optional
`cairn.local.toml`) accepted. Closed **`ADR-009`**: registry-agnostic with **GHCR as the
recommended default** (ERPNext clients/devs already live on GitHub; fits the pull-only
model). Brian is only lightly familiar with GHCR → a GHCR setup runbook is a tracked
Phase-6 user-doc deliverable. `CFG` fully approved.

## 2026-07-23 — CFG: target config (approved) + build config (drafted)

Grounded in real demo benches: the sites volume holds `common_site_config.json`
(bench-wide, derived from compose env by the `configurator` service),
`site_config.json` (per-site — db creds + **`encryption_key`**), and arbitrary local
config/policy files. Approved concepts → `BR-CFG-001`…`007`:
- image is env-agnostic; env config lives on the volume, never clobbered (`ADR-019`);
- **opacity line:** cairn understands *Frappe framework* config (`site_config.json`,
  `encryption_key`) but treats *app* config files opaquely;
- never overwrite Frappe-managed `site_config.json` (data-safety);
- **two config classes** with opposite restore behavior: *data-bound must travel*
  (`encryption_key`) vs *env-authority must not* (policy files) — drives `DATA`;
- provisioning is preserve-first + additive-seed;
- boundary: `common_site_config`/`.env`/secrets belong to `DEPLOY`/`ADR-017`.

Brian added a second config axis: **build configuration** (build-time, local to the
build machine), distinct from target config. Designed `BR-CFG-008`…`011` (drafted):
build config (registry namespace, buildx, cache) lives in a local file *separate from
the portable `cairn.toml`*; cairn is **registry-agnostic** (any OCI registry, not
hardcoded to Docker Hub); **auth delegated to `docker login`** (cairn never stores
registry creds); provenance labels ride with the pushed image, so the registry is the
image-and-metadata store. This narrows `ADR-009` to "recommended default only."

## 2026-07-21 — BUILD Pass 2: manifest, Option A pinning, provenance-as-labels, fork stance

Verified from bench source (`bench/app.py`) that both `FRAPPE_BRANCH` and `apps.json`
clone via `git clone --branch <ref>` with no post-clone checkout, and the Containerfile
strips `.git` in the same `RUN` — so **raw commit SHAs are unsupported** (correcting an
earlier claim that `apps.json` accepts commits). Evaluated Brian's two workarounds
(local-path; mid-build checkout): both are valid for a local bench but require editing
the vendored Containerfile (`ADR-001` forbids) — app repos aren't in the build container,
and `.git` is already stripped. Chose **Option A**: resolve every ref to its commit at
build time and *record* it (drives `CACHE_BUST`, tag, labels); pin by tag for
reproducibility; warn on branch. Rejected Option C (build-time synthetic-ref git mirror)
as too heavy and Option B (own the build) as thesis-defeating.

Markers: Brian rejected storing markers in the cairn tool repo (cairn is a distributable
tool; markers are *deployment* artifacts). Resolved: **provenance is stamped onto the
image as OCI labels** (via `docker build --label`, no Containerfile edit) — travels with
the artifact; optional sidecar in the *deployment* dir; never in cairn's own tree.

Fork question: agreed frappe_docker (MIT) adds no capability — it's a maintenance-heavy
convenience recipe — so a fork is legally harmless and defensible by transparency. Framed
it as the **sanctioned escape hatch** for control we can't get while vendoring unmodified
(e.g. hard commit-pinning), deferred and recorded as **`ADR-021`** (open). Closed
**`ADR-015`** (manifest schema + Option A pinning). BUILD drafted to
`docs/requirements/02-build.md` (`BR-BUILD-001`…`013`).

## 2026-07-21 — Phase 2 begins: VEND requirements (Pass 2)

Started requirements co-creation with `VEND`. Drafted `BR-VEND-001`…`010` from the
settled decisions. Resolutions from Brian's Pass-1 critique:
- **Drift = hard stop, no override** (`BR-VEND-005`). No scenario justifies an override:
  experimenting means editing the vendored tree (forbidden by `ADR-001`), benign drift is
  fixed by `ventwig sync`, and an emergency edit-and-override just discards the
  reproducibility trail. An override's only real effect is silently shipping an
  unreproducible image.
- **Pin immutability** — SHA pinning is the more-correct pin in principle but not required
  (committed tree + lock is the anchor); the cheap high-value guard is *sync-time commit
  verification*. Captured as **`ADR-020`** (open, a ventwig enhancement, non-blocking);
  `BR-VEND-002` written pin-mechanism-agnostic.
- Single vendored source (`frappe_docker`) — no multi-source machinery (YAGNI).
- `BR-VEND-005`/`006` stay in `VEND`, `BUILD` cites them; `cairn vendor` commands are
  `BR-CLI`.

## 2026-07-21 — Build PoC = ERPNext + BTU

With cofferdam ruled out as a PoC (using it would contradict `ADR-019`), Brian proposed
his **BTU** app ([`Datahenge/btu`](https://github.com/Datahenge/btu)). Assessment
confirmed it fits: `version-16` is the default branch (branches back to v12);
`requires-python >=3.14,<3.15` exactly matches the `custom` Containerfile defaults; it is
a released, MIT, long-maintained pure-Frappe app with light pip deps (`cron-descriptor`,
`schema`, `temporal-lib`) and needs no ERPNext. Its companion scheduler
(`btu_scheduler_py`) + RQ workers are runtime-only and out of scope for a *build* PoC;
Brian clarified BTU **degrades gracefully** without the scheduler (DocTypes/buttons fully
usable, only cron firing lost), so an optional runtime smoke-test needs no extra infra.
Chose composition **A: Frappe v16 + ERPNext + BTU** — on-mission (custom ERPNext image +
custom app) and exercises the N>1 apps path. Supersedes the earlier ERPNext-only PoC.

## 2026-07-21 — Strict decoupling from cofferdam (ADR-019)

Brian ruled that cairn must **not** rely on, leverage, or be aware of cofferdam /
cofferdam-app — and cofferdam should stay unaware of Docker. His intent: cofferdam stands
on its own and quietly does its job; if installed + configured it works, otherwise it
doesn't. Agreed, with a strengthening: the one scenario that appeared to need
cofferdam-awareness (restoring a Production DB into non-prod) is met correct-by-
construction via a **generic** rule — *restore replaces the DB (+ optional attachments)
and never overwrites local environment config on the sites volume* — which protects
`site_config.json`, local secrets, and any local policy file (e.g. cofferdam's) as a side
effect, naming no app. This also **retracted** an earlier proposal that cairn
enforce cofferdam policy presence / run `cofferdam validate` as a deploy invariant — that
was exactly the coupling being rejected. cofferdam may still appear as a *non-normative
illustrative example* in docs. → **ADR-019** (closed).

## 2026-07-21 — Adopted Scribe Coding methodology

Brian directed the project to follow **Scribe Coding** (Document-Driven AI Development,
<https://datahenge.com/blog/document-driven-ai-development/>) — his own methodology:
documentation is a living contract that precedes and governs code (docs-first, single
source of truth, Never Assume, small modules; requirements co-created via dialogue and
tagged with business-rule IDs; a CHANGELOG keeps docs living; code and tests cite the
BR IDs). Confirmed: the six BR areas (`VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`)
match his mental model; keep the **dual `BR` (requirements) + `ADR` (decisions/ADRs)**
system, as `cofferdam-app` already does (`BR-API-001` alongside ADRs). Ground-rules
home = root `CLAUDE.md` (auto-loads each session, so it actually binds the workflow).
Implication: **no Phase-1 build code until requirements are solid.** Established the
living-doc infrastructure (`docs/requirements/00-overview.md`, `docs/CHANGELOG.md`).

## 2026-07-21 — Kickoff & direction

Brian framed the project: wrap `frappe_docker` to make three things frictionless —
(1) rebuild a custom ERPNext image (Frappe + ERPNext + N custom apps), (2) handle
CI/CD, image rebuilding, restarting/re-pointing containers at the correct image for a
commit/tag/branch, and (3) easy backup/restore/rollback of SQL databases. Explicit
constraint: **do not modify `frappe_docker`; bolt on around it** (→ ADR-001).

## 2026-07-21 — Grounding in real upstream

Downloaded a fresh copy of upstream to reference actual (not remembered) capabilities.
Gotcha discovered: the official repo is **`frappe/frappe_docker` (underscore)**, not
`frappe-docker` (hyphen) — the hyphen path 404s. Cloned to `./frappe_docker`
(HEAD `c004361`, 2026-07-15).

**What upstream actually provides (the surface we wrap):**
- *Build:* hand-written root `apps.json` (`[{url, branch}]`) passed to
  `images/layered/Containerfile` or `images/custom/Containerfile` as a **BuildKit
  secret** (`--secret=id=apps_json,src=apps.json`) — not the old base64 build-arg.
  Requires Docker v23+. Cache invalidation is a manual `CACHE_BUST` build-arg.
- *Deploy:* mostly documentation. Hand-compose override files
  (`docker compose -f compose.yaml -f overrides/... config > compose.custom.yaml`);
  image pointer is three env vars (`CUSTOM_IMAGE`, `CUSTOM_TAG`, `PULL_POLICY=missing`);
  migrations are the operator's problem (a `compose.migrator.yaml` override exists).
- *Backup:* a sample `backup-job.yml` + a suggested crontab calling
  `bench --site all backup --with-files`. **No restore, no rollback, no retention.**

Conclusion: every one of the three pillars maps to a genuine upstream gap — the
project is not redundant with anything upstream ships.

## 2026-07-21 — layered vs custom (reproducibility)

Explained the two custom-app Containerfiles. `layered` builds `FROM frappe/base:*` /
`frappe/build:*` (fast, but **mutable** published tags). `custom` builds the base from
`python:*-slim` itself (self-contained, deterministic; pins Python/Node ourselves).
Initially defaulted to `layered` for speed, then **reversed**: Brian's requirement for
"absolutely reproducible and immutable state" is incompatible with layered's mutable
base — a rollback could rebuild against a changed base. `custom`'s slower first build
is absorbed by the buildx cache (base stage only rebuilds on base-arg changes).
Brian agreed. → **ADR-004**.

## 2026-07-21 — Vendoring strategy

Concern raised: we will never own `frappe_docker` and must stay synchronized as it
evolves. Recommended treating it as a **pinned, regenerable, read-only dependency**
(SHA pin + sync command + drift status), not a fork/submodule/subtree.

Brian revealed he owns **`ventwig`** (https://github.com/brian-pond/ventwig) — a
dev-time tool that vendors an upstream repo/subdir into a project as **plain committed
files**, pins the commit in `pyproject.toml`, writes `.ventwig.lock` (commit +
content-tree hash), and does **drift detection**. This is the same model, already
built, and Brian's own. Adopted it, with committing the tree (stronger for
immutability: the pinned input lives in our repo, independent of GitHub uptime).
Notes: `create_parent_package_markers = false`; consumer must be a git repo.
→ **ADR-007**, **ADR-008**.

## 2026-07-21 — Trigger architecture (daemon vs SSH)

Brian raised: do we need an agent daemon on the VPS reacting to GitHub events, or must
we SSH in every time to say "update yourself"? Reframed as a false binary. Key moves:
1. Trigger on **image-ready**, not on raw commit (no image exists at commit time).
2. Build one **idempotent, state-driven verb** (`reconcile`) — then every trigger
   (human SSH, CI push, cron poll, future webhook) is just a poke at the same
   converging function; the daemon question becomes a *latency preference*, deferrable.
3. Prefer **pull over push**: CI-over-SSH hands GitHub a key *into* the box (rejected,
   → ADR-005). A systemd-timer pull loop reaches only outward, needs no inbound port,
   and self-heals across missed events.

Recommendation adopted: pull-loop spine + deferred webhook daemon. The desired-state
pointer *is a cairn* — the newest stone the VPS walks to. → **ADR-006**.

## 2026-07-21 — Rollback semantics (ADR-012 closed)

Brian ruled that **rollback does not restore the database**. Production data is
fast-moving; auto-restoring SQL on rollback would discard live transactions. SQL
restore must stay a deliberate, manual last resort. Added domain rationale: a normal
Frappe/ERPNext `bench migrate` does **not** drop tables or columns, so a rolled-back
image whose DocType/DocField JSON no longer matches the live schema just leaves unused
columns/tables behind rather than losing data — image-only rollback is safe by
default. We still snapshot *before* a forward migration so a manual restore is
available, but never auto-applied. → **ADR-012** (closed).

## 2026-07-21 — ventwig wired up (ADR-007 implemented)

Made `cairn` a Python project (`pyproject.toml`) and configured ventwig to
vendor `frappe_docker`. Findings that shaped it:
- ventwig 0.2.0's `clone()` uses `git clone --depth 1 --branch <ref>` — accepts a
  branch or **tag**, not a raw commit SHA.
- Upstream publishes **release tags**; latest is **`v3.2.1`** (`d4a310089f5d`).
  Chose to pin the tag rather than the moving `main` (deterministic re-sync,
  deliberate upgrades). This supersedes the earlier assumption of pinning
  main-HEAD `c004361`.

Synced successfully: `.ventwig.lock` records commit `d4a310089f5d` + tree hash;
`ventwig status` = clean; no nested `.git` in the vendored tree; build files
(`images/custom/Containerfile`, `docker-bake.hcl`, `compose.yaml`) present.
The vendored tree is now committed plain content. Removed the temporary
`.gitignore` entry for it.

## 2026-07-21 — Scaffolding

Created `docs/` scaffolding: project scope, closed decisions, open decisions, and this
discussion log. Confirmed: layered rejected in favor of immutable `custom`; GitHub
must not be able to SSH the VPS; ventwig recommended for vendoring.
