# Open Decisions

Unresolved questions, each with current lean/recommendation where one exists.
IDs continue the `ADR-00N` sequence; when closed, a decision moves to
`01-decisions-closed.md` keeping its ID.

_Last updated: 2026-07-21_

---

### ADR-010 — Desired-state pointer mechanism
How does CI tell the VPS "converge to ref X"? Options:
- a **moving registry tag** (e.g. `:env-prod` → digest), VPS resolves digest;
- a **git "state" ref/repo** the VPS pulls;
- a small **object in a bucket**;
- a one-line file served somewhere the VPS reads.
**Lean:** immutable per-commit tag **plus** a moving per-environment tag; the moving
tag *is* the pointer, and the cairn marker records the resolved digest. _Open._

---

### ADR-011 — Image tagging scheme (ref → tag mapping)
Exact tag convention. e.g. immutable `:git-<shortsha>` (and/or `:v<semver>` for tags)
+ moving `:branch-<name>` / `:env-<name>`. Needs to encode enough to reconstruct the
cairn marker. _Open — depends on ADR-009/ADR-010._

---

### ADR-013 — Backup storage, retention, and restic
Where do DB (and files?) backups live — local disk, S3-compatible bucket, both? Do we
adopt the `restic` path already present in the upstream image, or keep it simpler
first? Retention policy (keep-last-N, GFS)? Encryption? _Open._

---

### ADR-014 — Migration orchestration
Use upstream's `overrides/compose.migrator.yaml` service, or have `cairn deploy` run
`bench migrate` as an explicit, observable deploy phase (with pre-migrate snapshot)?
**Lean:** cairn orchestrates it as a phase — snapshot → migrate → healthcheck →
flip — so failures are catchable and rollback-able. _Open._

---

### ADR-016 — Multi-site scope
Single site per bench assumed for Phase 1, or must backup/restore/deploy handle
multiple sites on one bench from day one? Affects backup granularity and
`FRAPPE_SITE_NAME_HEADER` handling. _Open — need Brian's intended usage._

---

### ADR-017 — Secrets & env management on the VPS
How `.env`, DB passwords, and registry pull credentials are stored/rotated on the
host (plain `.env`, Docker secrets per `compose.mariadb-secrets.yaml`, or an external
store). _Open._

---

### ADR-018 — Package / distribution name & CLI command
Confirm the CLI command is `cairn`, the Python package name, and PyPI/distribution
name. Working directory is `docker-cairn`; the command may differ from the repo name.
_Lean: repo `docker-cairn`, CLI `cairn`. Open (minor)._

---

### ADR-020 — Strengthen upstream-pin immutability (ventwig enhancement)
The vendored pin currently uses a release **tag** (ventwig 0.2.0 clones via
`git clone --depth 1 --branch <ref>`, which cannot take a raw SHA). Tags are mutable
upstream — they can be force-moved or deleted. Our committed tree + `.ventwig.lock`
already makes *builds* immutable regardless (`ADR-007`), but a *re-sync* could silently
pull a moved tag. Options:
- **(a)** status quo — tag pin + committed-tree/lock anchor;
- **(b)** teach ventwig to pin by immutable commit **SHA**;
- **(c)** teach ventwig to verify, on `sync`, that `ref` still resolves to the commit
  recorded in `.ventwig.lock`, and refuse on mismatch;
- **(b)+(c)**.

**Lean:** at minimum (c) — cheap, high-value guard against ref movement whether pinning
by tag or SHA — ideally (b)+(c). This is a ventwig enhancement (Brian owns ventwig),
tracked here; **not a docker-cairn blocker**. `BR-VEND-002` is written pin-mechanism-
agnostic so nothing here changes when this lands. _Open._

---

### ADR-021 — Deliberate fork of frappe_docker as the sanctioned escape hatch
frappe_docker is **MIT-licensed** and adds *no capability* to Frappe/ERPNext — it merely
codifies the documented manual install into a repeatable recipe. So forking it into our
own spinoff is legally permitted (retain the notice) and defensible by transparency
(publish the Dockerfile + build commands).

**Stance:** a fork is the **sanctioned escape hatch** for control we cannot get while
vendoring unmodified (`ADR-001`) — e.g. hard commit-pinning (see `ADR-020`, and the
build immutability model in `docs/requirements/02-build.md`), which is impossible via
bench's `git clone --branch` without editing the vendored tree. If such a need becomes
essential, the honest move is a *deliberate, eyes-open fork recorded as its own decision*
— not silent local edits (which `BR-VEND-004` forbids) nor Option C's build-time git-
mirror machinery.

**Cost to weigh when the time comes:** a fork transfers frappe_docker's real value — the
*continuous maintenance* of a correct recipe as Python/Node/wkhtmltopdf/Debian/Frappe
churn — onto us, and forfeits the deliberate drift-checked sync we built with ventwig
(`ADR-007`). Therefore: **deferred, not a default.** Revisit only against a concrete,
essential need. _Open._
