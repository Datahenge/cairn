# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-07-24

- **CLI help no longer leaks `BR` identifiers.** `/CLAUDE.md` requires internal docstrings
  to cite `BR` IDs while *external* descriptions omit them; because Typer renders a
  command's docstring as its `--help` text, every command was showing its `BR` ID to
  users. Commands now carry a user-facing `help=` on the decorator, leaving docstrings
  free to stay internal. Caught while reviewing `cairn --help` output, not by a test —
  worth a check before the Phase-6 user docs.
- **`ADR-030` records a rejected alternative: a per-deployment label namespace**
  (`com.microsoft.cairn.*` for a client Microsoft). Brian raised it and spotted the risk;
  the decisive objection is that **cairn reads these labels, not just writes them** — a
  target running `reconcile` holds an environment descriptor, not the build manifest, so
  it cannot know which prefix its own images used. The bootstrap never closes either:
  discovering a configured namespace still requires one fixed key to look it up under.
  Also recorded: a typo produces a perfectly valid label that fails silently, surfacing at
  rollback; and a namespace names *who defines the keys*, not who owns the image. The
  legitimate need underneath — recording whose image it is — belongs in
  `org.opencontainers.image.vendor`/`.title`/`.url`, which cairn could make settable later.
  Blast radius clarified: a wrong namespace does not make an image incompatible; it blinds
  cairn's own introspection, promotion, and rollback.
- **`ADR-030` — provenance label schema settled before the first push.** cairn-specific
  keys use **`com.datahenge.cairn.*`**, alongside standard `org.opencontainers.image.*`
  where one already fits. Reasoning was checked against the primary sources rather than
  convention-by-memory: the OCI image-spec only says keys **SHOULD** use reverse-DNS and
  is silent on both rationale and domain ownership, while **Docker's** documentation
  supplies both ("a domain **they own**"; "Don't use a domain … without the domain
  owner's permission"; the purpose being collision safety for automation). `io.cairn` /
  `dev.cairn` were **rejected as domains owned by others**; bare `cairn.*` was considered
  and rejected for forfeiting the collision protection cairn actually relies on, since it
  keys behavior off these labels. cairn deliberately does **not** set
  `org.opencontainers.image.vendor` — the distributing entity of a client's image is the
  client's to declare. Recorded in lessons §10 that a terse standard's operative guidance
  often lives in a dominant implementer's docs.
- **`BR-BUILD-008` clarified — a pin bump can change the tag with an unchanged manifest.**
  Affirmed by Brian as intended: the input hash covers *effective* build args
  (`BR-BUILD-010`), so a `frappe_docker` bump that moves a Containerfile default changes
  the image's inputs and therefore its tag. Stated explicitly because it will otherwise
  read as a defect to whoever meets it first; `BR-VEND-009` already makes pin bumps
  deliberate.
- **`BR-BUILD-007` revised — `CACHE_BUST` hashes *all* resolved commits, Frappe included.**
  As written it covered "the resolved app commits" only, which cannot satisfy its own goal
  ("a correct build MUST NOT require `--no-cache`"): `FRAPPE_BRANCH` enters the layer cache
  key by **name**, so a Frappe branch that *moves* keeps its name and would reuse a stale
  `bench init` layer. Brian approved including Frappe's commit, which also aligns the input
  set with `BR-BUILD-008`'s tag hash. Upstream's own recommended technique (an `apps.json`
  hash) has the same gap.
- **Two upstream corroborations recorded in `04-lessons-learned.md`.** The vendored
  `frappe_docker` docs turn out to state, in prose, two things this project had derived
  independently: **§1** — "BuildKit is the default builder starting with Docker Engine
  23.0" (`02-setup/02-build-setup.md:15`), confirming what was marked an inference about
  `BR-CLI-007`'s version floor; and **§2** — that `CACHE_BUST` exists precisely because
  secret contents are excluded from layer cache keys. **§4** gains a third: upstream
  documents `podman build` as a first-class equivalent with byte-identical flags,
  independent support for `ADR-027`. Reading the vendored docs earlier would have
  shortened that investigation.
- **`BR-CLI-007` revised — `git` added to the build-role preflight.** Implementing
  `resolve.py` surfaced that `git` is an unlisted build prerequisite: every manifest ref
  is resolved with `git ls-remote` (`BR-BUILD-005`), so a machine without git fails at
  resolution time rather than at preflight. Brian confirmed git is a prerequisite; the
  requirement now names it. No minimum version — `ls-remote` and its pattern matching
  predate every git a current distribution ships.
- **Lessons §9 — a pattern-filtered `git ls-remote` omits the peeled ref.** Found while
  implementing `resolve.py` (`BR-BUILD-005`): requesting `<ref>` alone returns an
  annotated tag's **tag object**, not the commit it peels to; `<ref>^{}` must be passed
  as a second pattern. Left uncorrected this would have recorded an object no clone ever
  checks out into provenance (`BR-BUILD-011`), the input hash (`BR-BUILD-008`), and
  `CACHE_BUST` (`BR-BUILD-007`) — well-formed and wrong. Unit tests passed throughout,
  because the stub returned what an *unfiltered* `ls-remote` returns; caught only by
  resolving against a real repository. No requirement changed.
- **`ADR-029` + `BR-CFG-012` — config discovery and precedence, finally documented.**
  `BR-CLI-014` promised "documented precedence" that was never written down; implementing
  `config.py` forced the gap. **Decided:** the manifest root and cairn's own project root
  are resolved by independent searches — `--manifest` if given, else the nearest
  `cairn.toml` walking up from the working directory, while the vendored tree stays
  anchored to cairn's root. They coincide in development and stop coinciding once cairn
  is `pip install`-ed, with no code change required. Build config layers
  `~/.config/cairn/config.toml` (machine-wide) under an optional `cairn.local.toml`
  **beside the manifest**, overriding key-by-key. `BR-CLI-014` now cites `BR-CFG-012`
  rather than promising documentation. `ADR-029` records one deferred gap: the wheel
  packages only `src/cairn`, so a pip-installed cairn has no vendored tree to build from
  — a `BUILD`-phase packaging concern.
- **Corrected `docs/plans/phase-1-build.md`**, whose illustrative manifest still showed
  the pre-approval `[cairn] name` and `[cairn.frappe] branch`. The approved
  `BR-BUILD-002` mandates `image_name` and `url`/`ref`; the plan is downstream of the
  requirements, so it was brought into line (and gained the `BR-BUILD-003` ordered-list
  comment that every shipped template must carry).
- **`ADR-027` — build engine is pluggable (`docker` | `podman`); deploy engine stays
  Docker.** Adopted after the measured buildah result. The unlock was recognizing that the
  build machine and the target are **different machines** whose only interchange is an OCI
  image in a registry, so `DEPLOY` needs no change at all — `BR-DEPLOY-005` already reads
  provenance over the (engine-independent) registry manifest API. Engine is auto-detected
  (prefer `docker`, else `podman`) and overridable via `engine =` in **local build config**,
  never in the portable `cairn.toml`. **Revised:** `BR-CLI-007` (role-aware preflight),
  `BR-BUILD-006` ("BuildKit secret" → "build secret"), `BR-BUILD-011` (engine's `--label`),
  `BR-BUILD-012` (exact build command), `BR-CFG-008` (engine is build config),
  `BR-CFG-010` (`docker login` / `podman login`); **amended** `ADR-003`. Engine floors:
  Docker v23+, podman v4+ (measured on 5.4.2). Carried risks: OCI-vs-v2s2 manifest format
  on push, and label readback across engines — both to confirm against a real registry.
  Rationale, evidence, and risks in `ADR-027`; motivation was avoiding a second engine
  managing nftables chains on a build-only laptop.
- **`ADR-028` — `cairn doctor` is role-aware, detected from context.** One package serves
  two roles (`ADR-018`), so a fixed preflight reports irrelevant failures. Build/control:
  build engine, vendored-tree integrity, config. Target: Docker + Compose, systemd,
  registry reachability. No flag in the common case (`BR-CLI-014`). The **target-role
  branch lands with `DEPLOY`**; doctor implements the build role today.
- **New document type — `docs/04-lessons-learned.md`.** Durable technical findings about
  the tools cairn builds on, kept separate from `BR` (what must be true), `ADR` (what we
  chose), and the discussion log (how we got there); each finding marked **measured** or
  **reasoned** and citing the IDs it illuminates. Added a row for it to `/CLAUDE.md`'s
  artifacts table. Seeded with seven findings from the Docker/podman investigation, the
  most consequential being **why `BR-BUILD-007` (`CACHE_BUST`) is a correctness
  requirement rather than an optimization**: a BuildKit secret's contents are excluded
  from the layer cache key by design, so editing `apps.json` alone will *not* invalidate
  the `bench init` layer. Also records that `Containerfile:144` strips app `.git`
  metadata — foreclosing image inspection as a provenance source and making
  `BR-BUILD-005`/`BR-BUILD-011` necessary rather than tidy.
- **Measured: buildah 1.39.3 / podman 5.4.2 satisfies the build side** (`BR-BUILD-006`,
  `BR-BUILD-007`) — secret mount honoured with `uid=`/`gid=`, no leak into layers or
  history, `CACHE_BUST` keying the cache in both directions. Retracts an earlier
  overstated claim that buildx has no podman equivalent. **No requirement changes**: the
  docs still name Docker (`BR-CLI-007`, `BR-BUILD-011`, `ADR-003`) and DEPLOY remains
  compose-shaped and untested against podman. Recorded so the question can be reopened
  cheaply if it ever is.
- **Phase 4 — second module (`cairn doctor`).** Implemented `src/cairn/doctor.py` (Docker
  Engine v23+ and buildx probes, plus the three vendored-tree preconditions) and
  `vendor.assert_build_inputs` — the first implementation of `BR-VEND-006`, deriving the
  required build inputs from the Containerfile's own context `COPY`s rather than a
  hardcoded list. Cites `BR-CLI-007/012/015`, `BR-VEND-005/006/007`. 20 unit tests
  (same `BR` IDs), ruff-clean; both the pass and fail paths verified end-to-end.
  **`BR-CLI-007` is landed partially by design:** its *"config valid"* leg awaits the
  config module and will be added when `config.py` lands (`BR-CLI-014`, `BR-CFG-008`,
  `BR-BUILD-002`). Decided then: a **missing** `cairn.toml` will WARN and keep exit 0
  (doctor is a machine preflight, legitimately run on a target host or before a manifest
  exists); a **malformed** one will FAIL. `--json` was deliberately not added — `BR-CLI-013`
  scopes it to `images`/status.
- **Phase 4 begins — first module (`VEND`).** Made the project a real Python package
  (hatchling, `src/` layout, `cairn` console script + `datahenge-cairn` alias, typer, ruff,
  pytest). Implemented `src/cairn/`: `project.py` (root discovery + vendor-source parsing),
  `vendor.py` (thin `ventwig` wrappers + drift/`.git` integrity checks), `cli.py` (Typer
  app with the `vendor status|sync` group). Cites `BR-VEND-003/005/007`, `BR-CLI-001/006/015`.
  9 unit tests (same `BR` IDs), ruff-clean; `cairn vendor status` verified end-to-end
  against the real vendored tree.

- **Non-requirement consistency sweep.** Aligned forward-looking docs with the approved
  requirements: project scope + overview reframed to **two pillars + a data-plane boundary**
  (was "three pillars"/"backup·restore·rollback"); `CLAUDE.md` `DATA` area updated; "DB
  snapshot" removed from the cairn metaphor. Added **supersession notes** to `ADR-012`
  (no pre-migrate snapshot) and `ADR-019` (cairn performs no restore), both pointing to
  `ADR-022`. Banner-marked the Phase-1 build plan as **superseded-in-part** (markers are
  labels not `.cairn/markers/`; no `cairn markers` command; `DATA` is a boundary). History
  docs (discussion log, this CHANGELOG) left as append-only record.
- **Requirements clarity audit.** Tightened all six requirement docs
  (`BR-VEND/BUILD/DEPLOY/DATA/CFG/CLI`) to crisp normative statements; migrated inline
  rationale/mechanism/verification into the cited ADRs and the discussion log. IDs and
  citations unchanged; approvals stand (clarity revision, not a design change).

- **`CLI` approved (`BR-CLI-001`…`015`). ALL SIX requirement areas now approved**
  (`VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`) — the Scribe Coding requirements phase
  is complete. Next: Phase 4 (modular code), one small module at a time.
- **`CLI` drafted (Pass 1)** — `docs/requirements/06-cli.md`, `BR-CLI-001`…`015`. Verb set:
  `build [--push]`, `push`, `new-tag`/`retag`/`retire` (create/move/decommission, with
  `--latest|--previous|--id|--from` selectors + typo-guards), `images`, `vendor`, `doctor`,
  `reconcile`. Conventions: `--dry-run`, prod-gate `--yes`, `--json` on reads,
  stdout/stderr logging + exit codes, config discovery. Sharpened `BR-DEPLOY-009` to a
  **declared environment list** (not bare convention).
- **Verified GHCR deletion is version-based** (no per-tag delete; deleting a version removes
  its image + all tags; public >5,000-download versions are undeletable). So `cairn retire`
  decommissions at cairn's layer only; the registry tag name lingers. Recorded in the
  deferred GHCR-cleanup note.
- **`DEPLOY` approved** (`BR-DEPLOY-001`…`020`) — all decisions resolved; only the deferred
  GHCR-side cleanup command remains (non-blocking). Five of six requirement areas approved.
- **Naming & packaging (`ADR-018` closed).** Single package/repo, name **`datahenge-cairn`**
  (`cairn` taken; `docker-cairn`/`frappe-cairn` falsely imply Docker/Frappe ownership;
  `datahenge-cairn` signals Datahenge + doubles the stone motif). Import package `cairn`;
  command **`cairn`** (+ `datahenge-cairn` alias). Split deferred behind an explicit
  trigger. Renamed the project **`docker-cairn` → `cairn`** throughout the docs (prose) and
  the local repo directory → `datahenge-cairn`; `pyproject` name → `datahenge-cairn`.
  Remote left untouched (new one to be created later). Also corrected the README pillars to
  match the current scope (two pillars + data-plane boundary; no DB backup/restore).
- **`DEPLOY` sequencing / health / failure / observability** (`BR-DEPLOY-016`…`020`).
  Single-flight reconcile; in-place recreate; `migrate` after every image enable (incl.
  rollback); health-gated success. **`ADR-025`**: deploy failure = **halt + report**, no
  auto-rollback (rollback stays manual). **`ADR-026`**: log to stdout/stderr only (host owns
  monitoring); optional best-effort **failure webhook** (transport-agnostic). Closed
  **`ADR-011`** (tagging settled by `BR-BUILD-008`).
- **`DEPLOY` secrets, single-site, prod gate** (`BR-DEPLOY-009`…`015`). Environment model:
  two halves joined by the tag; cairn **renders** the compose from the descriptor.
  **Closed `ADR-017`** (secret-agnostic: cairn references/wires but never handles secret
  values; registry pull via `docker login`; DB secrets via `compose.mariadb-secrets.yaml`
  recommended, `.env` supported). **Closed `ADR-016`** (single site per environment;
  multi-site deferred). Prod pointer moves require explicit confirmation; `install-app`
  to prod doubly explicit. Only sequencing/health remains open in DEPLOY.
- **`DEPLOY` opened, drafted (Pass 1, partial)** — `docs/requirements/03-deploy.md`,
  `BR-DEPLOY-001`…`008`: pull-based reconcile (target polls the env tag's digest);
  deploy/promote/rollback are one primitive (server-side retag, no rebuild); registry
  introspection reads provenance labels remotely; timer-driven GC keeps last N images and
  **never touches volumes**; cairn deploys to existing environments only.
- **Closed `ADR-010`** — desired-state pointer = the environment's moving registry tag
  (target polls; laptop advances by retag).
- **Added `ADR-024`** — reconcile is a thin orchestrator over docker/compose + registry
  API + systemd; Watchtower/Flux/ArgoCD evaluated and rejected (with reasons).
- **`DATA` approved** (`BR-DATA-001`…`008`) — the data-plane boundary area is settled.
- **Opt-in `bench install-app` (`ADR-023`).** A concrete case (deploying a 5-app image to
  a 2-app TEST site) showed `bench migrate` does *not* install newly-added apps. Decision:
  a default deploy is code-swap + `migrate` only (never changes a site's app set — least
  surprise); `bench install-app` is a second sanctioned Frappe command, **opt-in only**,
  delivered via the target's reconcile (no SSH). Added `BR-DATA-008`; amended `ADR-014`
  ("sole automatic" + install-app) and `ADR-022`.
- **Refined `BR-DATA-006` for accuracy:** cairn does not *itself* write to volumes, but the
  stack's own `configurator`/entrypoint reconcile the volume at every `compose up`
  (`ls -1 apps > sites/apps.txt`, `bench set-config -g …`, relink `sites/assets`) — Frappe's
  machinery, not cairn.
- **Established the data-plane boundary (`ADR-022`).** cairn ships code, not data: no SQL
  connection, no `bench execute`/`frappe` code, no DB movement; altering a target DB
  directly is impossible by construction. Sole exception: `bench migrate` after an image
  swap. Volumes/site-configs/`encryption_key` are aware-but-untouched.
- **Closed `ADR-014`** — `bench migrate` is the sole sanctioned (indirect) DB interaction;
  mandatory post-deploy, opaque, non-destructive. **Closed `ADR-013`** — backup / restore
  / DB-movement are out of scope.
- **Wrote `DATA` as a boundary area** (`docs/requirements/04-data.md`, `BR-DATA-001`…`007`,
  drafted). Reframed **Pillar 3** in the project scope; **revised approved `BR-CFG-005`/
  `006`** (no two-classes action; no volume seeding — `BR-DATA-006` supersedes); dropped
  "DB snapshot" from the cairn-marker concept.

## 2026-07-23

- **`CFG` fully approved** (build config signed off). `BR-CFG-010` refined: cairn may read
  a registry token from env / a local env file to perform a *transient* `docker login`,
  but still never stores credentials.
- **Closed `ADR-009`** — cairn is registry-agnostic; **GHCR is the recommended default**
  (ERPNext/GitHub ubiquity; fits the pull-only model). Follow-up: a GHCR setup runbook is
  needed (deferred to Phase-6 user docs).
- **`CFG` target config approved; build config drafted (Pass 1).** Added
  `docs/requirements/05-config.md`. Target (`BR-CFG-001`…`007`): env config lives on the
  sites volume and is never clobbered; opacity line (Frappe framework config understood,
  app config opaque); never overwrite Frappe-managed `site_config.json`; two config
  classes (data-bound `encryption_key` must travel vs env-authority must not);
  preserve-first + additive-seed provisioning. Build config (`BR-CFG-008`…`011`, drafted):
  build-time settings live in a local file separate from the portable `cairn.toml`;
  registry-agnostic; auth delegated to `docker login`; provenance labels ride with the
  pushed image (registry = image-and-metadata store).
- **Narrowed `ADR-009`** to "recommended default registry only" (cairn is now
  registry-agnostic via build config).

## 2026-07-21

- **`BUILD` requirements approved.** `BR-BUILD-008` tag composition settled as option (b)
  — human-legible slug + input-hash (`v16-a1b2c3d4`) + moving `latest`. Marked the
  `BUILD` row **approved**.
- **`BUILD` drafted (Pass 2).** `BR-BUILD-001`…`013` in `docs/requirements/02-build.md`.
  Verified bench pins by branch/tag only (no raw-SHA); adopted **Option A**
  (resolve-and-record commits, pin tags, warn on branch) — correcting the earlier
  "apps.json accepts commits" claim. Provenance is stamped as **OCI image labels**
  (not stored in the cairn tool repo); optional sidecar lives in the deployment dir.
  One item still open: `BR-BUILD-008` tag composition (pure hash vs. human-legible).
- **Closed `ADR-015`** (manifest `cairn.toml` schema + Option A app-pinning), moved to
  the closed register.
- **Added `ADR-021` (open)** — a deliberate fork of frappe_docker (MIT) as the sanctioned
  escape hatch for control unattainable while vendoring unmodified; deferred, not a
  default.
- **Manifest schema talk-through (pre-`BUILD`).** Settled: standalone `cairn.toml`
  (one file = one image, env-agnostic); `image_name`; special `[cairn.frappe]` section;
  **ordered** `[[cairn.apps]]` list = positional install order (no dependency solver);
  `[cairn.build]` knobs (`python_version`, `node_version`, `install_chromium`) +
  passthrough; no separate lockfile (marker is the record); input-deterministic (not
  hermetic) reproducibility bar. Redis/MariaDB versions are a DEPLOY concern (compose
  image tags), not image/manifest inputs. Documented the ordered-list rule prominently in
  `README.md` (required inline in every shipped template).
- **`VEND` requirements approved.** Brian signed off `BR-VEND-001`…`010` (hard-stop drift
  reasoning accepted; `ADR-020` parked open). Marked the `VEND` row **approved** in the
  requirements overview.
- **Began Phase 2 (requirements co-creation) with `VEND`.** Drafted `BR-VEND-001`…`010`
  in `docs/requirements/01-vendoring.md` (Pass 2): drift is a hard stop with no override;
  pin is immutable-intent and mechanism-agnostic; single vendored source.
- **Added `ADR-020` (open)** — strengthen upstream-pin immutability via a ventwig
  enhancement (SHA pinning and/or sync-time commit verification); non-blocking.
- **Adopted Scribe Coding** (Document-Driven AI Development) as the project methodology;
  added the ground-rules contract at `/CLAUDE.md`. Established the dual identifier
  system: `BR-<AREA>-NNN` (requirements) and `ADR-NNN` (decisions/ADRs).
- **Established the living-documentation infrastructure:** created
  `docs/requirements/` with `00-overview.md` (requirements root + ToC + conventions)
  and this `docs/CHANGELOG.md`.
- Requirements areas defined: `VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`.
  Per-area requirement documents are pending Phase-2 co-creation.
- **Renamed the decision-record prefix `D-NNN` → `ADR-NNN`** across all docs
  (`ADR-001`…`ADR-018`), for an explicit, self-describing identifier that matches
  `cofferdam-app`'s ADR convention. No IDs or numbering changed — prefix only.
- **Set the build PoC target to Frappe v16 + ERPNext + BTU** (`Datahenge/btu@version-16`),
  superseding the earlier ERPNext-only PoC now that a suitable, non-contradictory custom
  app exists. Updated the Phase-1 plan's verification target and illustrative
  `cairn.toml` manifest (the actual `cairn.toml.example` file is deferred to BUILD
  implementation, after Phase-2 `BUILD` requirements exist).
- **Added `ADR-019` — strict decoupling from cofferdam** (cairn and cofferdam are
  mutually unaware). Reframed the Phase-1 plan's Pillar-3 note around a *generic*
  restore-scoping rule (never overwrite local env config on the sites volume) instead of
  cofferdam-specific enforcement; retracted the earlier `cofferdam validate` deploy
  invariant. Genericized the `CFG` area description in `CLAUDE.md` and the requirements
  overview (cofferdam now only a non-normative example).

### Predating this changelog (context)

The following were created before the changelog existed and are its baseline:
`docs/00-project-scope.md`; the decision register `docs/01-decisions-closed.md`
(`ADR-001`…`ADR-008`, `ADR-012`) and `docs/02-decisions-open.md`
(`ADR-009`…`ADR-011`, `ADR-013`…`ADR-018`); `docs/03-discussion-log.md`; and the Phase-1
build plan `docs/plans/phase-1-build.md`. Vendored upstream `frappe_docker` pinned to
`v3.2.1` via ventwig.
