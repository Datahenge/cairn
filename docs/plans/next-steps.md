---
status: archived
owner: project
purpose: Narrative record of the session that produced ADR-031/032; the live backlog now lives in open/OPEN_WORK.md.
---

# Next Steps

> **Superseded as a live backlog by `open/OPEN_WORK.md`** (seeded from this file 2026-08-03).
> Kept here as the narrative record of how that session's work was approached — read
> `open/OPEN_WORK.md` for current outstanding work, not this file. Command names below predate
> the `cairn-build`/`cairn-adopt` split (`ADR-046`) and are historical, not current usage.

_Written 2026-07-25, at the end of the session that produced `ADR-031` and `ADR-032`.
Revised later the same day: `cairn prune` verified on the machine, and the CLI layer tested.
Revised again 2026-07-25: the PyPI-install blockers closed, `README.md` written, and the
installer moved into the package as `cairn-provision` — see `docs/CHANGELOG.md` for the full
account. The table and §4 below are updated accordingly; §1–3 and the lessons-learned section
are untouched and still current._

A resumption point for a fresh session. Read `/CLAUDE.md` first (the working agreement),
then this. Everything below is downstream of requirements that are already written; where a
decision is still open it says so explicitly, and **an open decision is not an invitation to
guess** — ask.

---

## Where things stand

Phase 4 (modular code) is under way. Implemented and tested (568 tests, ruff clean, 92%
statement coverage; `cli.py` at 99%):

| Command | Requirements | State |
| --- | --- | --- |
| `cairn build` | `BR-CLI-002`, `BR-BUILD-*` | Working end-to-end against a real registry |
| `cairn push` | `BR-CLI-003` | Working |
| `cairn images --local` | `BR-CLI-005` | Working; verified on the real machine |
| `cairn images` (registry) | `BR-CLI-005`, `BR-DEPLOY-005` | Written; **never run against a real registry** |
| `cairn prune` | `BR-CLI-018` | Working; verified on the real machine 2026-07-25 |
| `cairn doctor` | `BR-CLI-007` | Working; **target-role branch not written** (`ADR-028`) |
| `cairn vendor status\|sync` | `BR-CLI-006` | Working |
| `new-tag` / `retag` | `BR-CLI-004`, `BR-CLI-009/010` | Written; **never run against a real registry** |
| `retire` | `BR-CLI-009` | Written; reports only — edits no manifest, deletes no tag |
| `reconcile` | `BR-CLI-008`, `BR-DEPLOY-003` | Written; **never run on a real target** |
| `systemd-units` | `BR-CLI-019` | Written; prints units, installs nothing |
| `adopt` | `BR-CLI-020` | Written; prints a descriptor read off a running stack |
| `cairn-provision` | `BR-DEPLOY-021` | Written; **never run on a real host** |

**Everything in the deploy path is unexercised against real infrastructure.** It is heavily
tested and mutation-checked, which establishes that it does what it was written to do — not
that what it was written to do is right. The first live run is the test that matters.

`build` gained a lot in this session: attended-mode transcripts (`BR-CLI-016`), per-phase
timing (`BR-CLI-017`), the input-hash short-circuit (`BR-BUILD-014`), and cache-stage naming
(`BR-BUILD-015`).

---

## 1. ~~Verify `cairn prune` on the real machine~~ — done 2026-07-25

Brian ran it and confirmed it behaved as intended. This was the only new code never executed
against real images, and `cairn prune` remains cairn's only destructive verb — so if its
scoping is ever changed, re-verify on the machine rather than trusting the suite. The
instrument is:

```
cairn images --local     # what cairn thinks is there
podman image list        # what is actually there
cairn prune --dry-run    # what would be removed
```

The selection logic is covered by `tests/test_prune.py`, and the CLI's plumbing of `--keep`,
`--dry-run`, `--yes`, the confirmation gate, and the non-zero exit on a failed removal by
`tests/test_cli.py`. What no test can settle is whether the engine's real listing looks the
way cairn assumes, which is what the machine run answered.

---

## 2. Measure the case that decides the fork question

`ADR-021`'s **fork pressure register** (in `docs/adr/021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md`) names its own trigger, and
the measurement has not been taken:

> Time a rebuild after **a single custom-app commit**, against a first build.

This is the workflow that actually recurs — one Frappe/ERPNext version pinned for a client,
then weeks of custom-app iteration. Because `bench init` is one atomic `RUN` guarded by one
`CACHE_BUST`, changing one BTU commit re-clones Frappe and ERPNext and rebuilds every asset.
The number is unknown, and everything about per-app caching depends on it.

Method: commit something trivial to BTU, run `cairn build`, and record the per-phase timing
(`BR-CLI-017` now prints it, and the transcript keeps it). Compare against the first build.
Record the result in `docs/technical/04b-lessons-caching-and-provenance.md` marked
*measured*.

---

## 3. ~~Settle the `<legible>` tag half~~ — decided 2026-07-25

Resolved: `[cairn] series = "v16"` in the manifest. The readable half of the tag is now
declared once rather than derived from the Frappe ref, so re-pinning the ref from a branch to
a tag no longer renames every image. The series never enters the input hash — it is a label,
not an input — so renaming a line of images cannot orphan the ones already built.

Reading the true version at the resolved commit was the more truthful option and was rejected:
`git ls-remote` returns hashes, not file contents, so it needs either a clone on every build or
a provider-specific API call. Full reasoning in `ADR-032`.

Accepted cost: nothing validates the declaration. A manifest may claim `series = "v16"` while
building Frappe 15. Validating it at build time against the resolved version is possible later
and is not currently a requirement.

---

## 4. The first live deployment — do this next

The whole deploy path is written. What remains is running it, in this order, and the order is
chosen so that each step is reversible until the last one.

**Decide the registry first** (`docs/technical/ABOUT_REGISTRIES.md`). For Brian's own projects `ghcr.io/datahenge`
is fine and already declared in the scratch manifest. For a client, the registry must be an account
they own, with a push credential scoped to that one repository (`BR-CFG-013`).

**Provision the machine with the installer** rather than by hand (`ADR-040`, amended 2026-07-25).
There is no checkout to rsync anymore — `cairn-provision` installs alongside `cairn` from PyPI:

```
sudo pipx install --global datahenge-cairn   # shared system install, not tied to one account
cd /opt/deployments/<client>                 # or wherever cairn.toml will live
sudo cairn-provision --role both --dry-run   # review every action
sudo cairn-provision --role both --private-ip <ip>
```

`--role both` is today's case, one box building and serving. When they split it becomes
`--role builder` on one and `--role target` on the other; the stage lists differ accordingly and
each stage refuses the wrong role. This is also the first real (non-dry-run) execution of
`cairn-provision` against live infrastructure — everything about it so far is unit-tested and
dry-run-verified against a wheel install, never against real docker/systemd/openssl.

**On the control machine:**

```
podman login <registry>            # only if using a remote registry
cairn images                       # does the registry read work at all?
cairn build --push                 # if no image is in the registry yet
cairn new-tag production --latest --dry-run
cairn new-tag production --latest  # prompts, because it is production
```

**On the VPS**, write `/etc/cairn/environment.toml` (`ADR-034`), then:

```
cairn reconcile --dry-run          # says what it would do, takes no lock, changes nothing
cairn reconcile                    # pull -> compose up -> bench migrate -> health
cairn systemd-units | less         # only once a manual pass has succeeded
```

Do **not** install the timer before a manual `reconcile` has worked. A timer turns a wrong
descriptor into a wrong deploy every five minutes.

**Known-unknowns to watch for on that first run**, each recorded because no test can settle it:

- **The registry read.** `ADR-036`'s client has spoken to GHCR only as far as its 401 challenge and
  token endpoint — verified working, and correctly reporting that no credential is stored. The
  authenticated path, the manifest fetch, and the config-blob read are all still unexercised. If the
  chosen registry is *not* GHCR, its token flow may differ in detail; the challenge parsing is
  generic but has been tested against one registry's wording only.
- **`compose.directory`.** `reconcile` renders the stack from the frappe_docker tree *on the
  target*; if the descriptor's directory is wrong, compose is invoked with no `--file` at all
  and will use whatever is in the working directory.
- **`stack_is_up` reads `docker compose ps --format json`,** whose shape has changed across
  Compose versions. Both known shapes are handled; a third would read as "not up" and time
  out at the health check.
- **The health check probes from inside the stack** with `curl`, which the backend image may
  not carry. Absent a `[health] url` it checks containers only, which is the safer default.

## 4a. After the first deployment

- **`cairn doctor`'s target-role branch** (`ADR-028`, `BR-CLI-007`) — Docker + Compose,
  systemd, registry reachability. Currently `doctor` only runs the build/control checks
  regardless of role; since the vendored tree now ships inside every install (2026-07-25), those
  checks no longer fail outright on a target, they just ask the wrong questions of it (git,
  build engine) instead of the right ones (systemd, registry reachability). Still the most
  obvious gap the first live run will expose, just a quieter one now than a crash.
- **~~`ADR-037`~~ — closed 2026-07-25: cairn never installs a Frappe App.** The clause was struck
  rather than implemented. If a Frappe App must be added to a live environment, that is
  `bench install-app`, run by hand, exactly as site creation already is.
- **`BR-DEPLOY-006`** — the target-side GC pass (keep last N images, **never** touch volumes).
  `cairn prune` is its build-machine analogue and the same label-scoping applies.
- **`BR-DEPLOY-020`** — the optional failure webhook. Opt-in, best-effort, must never crash
  cairn or alter deploy behaviour.

---

## 5. Smaller carried items

- **Registry-backed cache** (`--cache-to` / `--cache-from`). No help for a warm local
  rebuild; large help for a cold CI runner. Weaker on podman, which `ADR-027` requires we
  keep supporting. Not yet a requirement.
- **A coverage floor.** `pytest-cov` is a declared dev dependency and the package sits at
  92%. A `--cov-fail-under` floor was deliberately *not* added: putting `--cov` in
  `addopts` makes every plain `pytest` run fail without the plugin installed. Decide the
  trade before adding it.
- **`ADR-036` is mine, not Brian's.** cairn speaking the registry API directly was decided
  during implementation, on the evidence that no tool present on the control machine can read a
  remote image's labels. It is the one decision in the deploy path he did not choose, and the
  module boundary is drawn so that swapping in `skopeo` later would touch nothing else.
- **`ADR-020`** — ventwig pin immutability. Brian owns ventwig; not a cairn blocker.
- **Phase 6** — `README.md` done 2026-07-25 (Installation, Configuration, How-To-Use, grounded
  in the real CLI surface). `USAGE.md` not started; unclear whether it's still needed
  separately from the README or was superseded by it — decide before writing one.
- **A dedicated service account for `reconcile`**, instead of the default `root`. Raised
  2026-07-25 while deciding the recommended install method; deliberately not built — it
  addresses least-privilege/audit-trail, not the account-independence risk that motivated
  `sudo pipx install --global` (root already has that property). Needs `docker` group
  membership either way, which is itself close to root-equivalent, so the security delta is
  smaller than it looks. Worth a documented "hardening" option, not a default.

---

## Things a fresh session should know before touching anything

These were learned expensively in this session; the full versions are in
`docs/technical/04b-lessons-caching-and-provenance.md` §5 and
`docs/discussions/discussion-log.md` (2026-07-25 entries).

- **Declared vs resolved inputs is the distinction that makes the rest coherent.** Image
  content is a function of *resolved* inputs. Same declared/different resolved = a branch
  moved; different declared/same resolved = a branch and a tag naming one commit.
- **cairn's primary tag is deterministic, not immutable.** It is a re-pointable name, not a
  content address. The digest is the address. Calling it "immutable" caused a real
  misdiagnosis.
- **On podman, an untagged image may be the build cache.** `<none>` spans superseded builds,
  multi-stage stage images, and true orphans, and the engine's listing cannot tell them
  apart. Never scope destructive work by danglingness; scope it by cairn's own labels, which
  are applied at the final commit and so never appear on a stage.
- **`src/cairn/vendored/frappe_docker/` is read-only** (`ADR-001`, `BR-VEND-004`). Manage it only
  via `cairn vendor sync` — never touch `ventwig` directly, and never at build time (2026-07-25:
  it moved inside the package specifically so nothing outside `vendor sync`/`status` needs it).
- **`BR`/`ADR` IDs must never reach user-visible output.** `tests/test_conventions.py` parses
  every non-docstring string in the package. If it fails, the *message* is wrong, not the
  test.
