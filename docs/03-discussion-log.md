# Discussion Log

Chronological summaries of the design conversation — the reasoning behind the
decisions, so future readers (and future sessions) don't have to re-derive it.

_Last updated: 2026-07-21_

---

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

Brian ruled that docker-cairn must **not** rely on, leverage, or be aware of cofferdam /
cofferdam-app — and cofferdam should stay unaware of Docker. His intent: cofferdam stands
on its own and quietly does its job; if installed + configured it works, otherwise it
doesn't. Agreed, with a strengthening: the one scenario that appeared to need
cofferdam-awareness (restoring a Production DB into non-prod) is met correct-by-
construction via a **generic** rule — *restore replaces the DB (+ optional attachments)
and never overwrites local environment config on the sites volume* — which protects
`site_config.json`, local secrets, and any local policy file (e.g. cofferdam's) as a side
effect, naming no app. This also **retracted** an earlier proposal that docker-cairn
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

Made `docker-cairn` a Python project (`pyproject.toml`) and configured ventwig to
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
