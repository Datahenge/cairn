# Open Decisions

Unresolved questions, each with current lean/recommendation where one exists.
IDs continue the `D-00N` sequence; when closed, a decision moves to
`01-decisions-closed.md` keeping its ID.

_Last updated: 2026-07-21_

---

### D-009 — Container registry for built images
Where do immutable images live so the VPS can pull them? Candidates: GHCR
(GitHub Container Registry), Docker Hub, or self-hosted registry on/near the VPS.
**Lean:** GHCR — co-located with source, good auth story, read-only pull token for
the VPS fits the pull-only model (D-005/D-006). _Open._

---

### D-010 — Desired-state pointer mechanism
How does CI tell the VPS "converge to ref X"? Options:
- a **moving registry tag** (e.g. `:env-prod` → digest), VPS resolves digest;
- a **git "state" ref/repo** the VPS pulls;
- a small **object in a bucket**;
- a one-line file served somewhere the VPS reads.
**Lean:** immutable per-commit tag **plus** a moving per-environment tag; the moving
tag *is* the pointer, and the cairn marker records the resolved digest. _Open._

---

### D-011 — Image tagging scheme (ref → tag mapping)
Exact tag convention. e.g. immutable `:git-<shortsha>` (and/or `:v<semver>` for tags)
+ moving `:branch-<name>` / `:env-<name>`. Needs to encode enough to reconstruct the
cairn marker. _Open — depends on D-009/D-010._

---

### D-013 — Backup storage, retention, and restic
Where do DB (and files?) backups live — local disk, S3-compatible bucket, both? Do we
adopt the `restic` path already present in the upstream image, or keep it simpler
first? Retention policy (keep-last-N, GFS)? Encryption? _Open._

---

### D-014 — Migration orchestration
Use upstream's `overrides/compose.migrator.yaml` service, or have `cairn deploy` run
`bench migrate` as an explicit, observable deploy phase (with pre-migrate snapshot)?
**Lean:** cairn orchestrates it as a phase — snapshot → migrate → healthcheck →
flip — so failures are catchable and rollback-able. _Open._

---

### D-015 — Custom-apps specification (our manifest → apps.json)
cairn should own a human-friendly apps manifest (name, repo, ref/pin per app) that it
compiles into the `apps.json` BuildKit secret. Pinning apps by **commit** (not branch)
is required for true immutability. Format/location TBD (likely a `[tool.cairn]` /
`cairn.toml` block). _Open._

---

### D-016 — Multi-site scope
Single site per bench assumed for Phase 1, or must backup/restore/deploy handle
multiple sites on one bench from day one? Affects backup granularity and
`FRAPPE_SITE_NAME_HEADER` handling. _Open — need Brian's intended usage._

---

### D-017 — Secrets & env management on the VPS
How `.env`, DB passwords, and registry pull credentials are stored/rotated on the
host (plain `.env`, Docker secrets per `compose.mariadb-secrets.yaml`, or an external
store). _Open._

---

### D-018 — Package / distribution name & CLI command
Confirm the CLI command is `cairn`, the Python package name, and PyPI/distribution
name. Working directory is `docker-cairn`; the command may differ from the repo name.
_Lean: repo `docker-cairn`, CLI `cairn`. Open (minor)._
