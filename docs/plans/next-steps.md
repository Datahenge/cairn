# Next Steps

_Written 2026-07-25, at the end of the session that produced `ADR-031` and `ADR-032`.
Revised later the same day: `cairn prune` verified on the machine, and the CLI layer tested._

A resumption point for a fresh session. Read `/CLAUDE.md` first (the working agreement),
then this. Everything below is downstream of requirements that are already written; where a
decision is still open it says so explicitly, and **an open decision is not an invitation to
guess** — ask.

---

## Where things stand

Phase 4 (modular code) is under way. Implemented and tested (444 tests, ruff clean, 92%
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

`ADR-021`'s **fork pressure register** (in `02-decisions-open.md`) names its own trigger, and
the measurement has not been taken:

> Time a rebuild after **a single custom-app commit**, against a first build.

This is the workflow that actually recurs — one Frappe/ERPNext version pinned for a client,
then weeks of custom-app iteration. Because `bench init` is one atomic `RUN` guarded by one
`CACHE_BUST`, changing one BTU commit re-clones Frappe and ERPNext and rebuilds every asset.
The number is unknown, and everything about per-app caching depends on it.

Method: commit something trivial to BTU, run `cairn build`, and record the per-phase timing
(`BR-CLI-017` now prints it, and the transcript keeps it). Compare against the first build.
Record the result in `04-lessons-learned.md` marked *measured*.

---

## 3. Settle the `<legible>` tag half — an open decision

**Do not implement without a decision from Brian.** Recorded in `ADR-032` as deliberately
open.

`tagging.legible_slug()` derives from the **declared** Frappe ref, so the tag is not a pure
function of resolved inputs:

```
same commit, declared as branch:  v16-1b019793dc20
same commit, declared as tag:     v16.0.1-1b019793dc20
```

Two consequences: one commit reached two ways yields two tag names for one image; and
following `BR-BUILD-005`'s own advice to pin to tags **renames every image** though nothing
about the content changed.

Options on the table, with the prior lean recorded as **(c)**:

- **(a)** status quo — declared ref; informative, but leaks a mutable symbol into identity;
- **(b)** read the version at the resolved commit (e.g. `frappe/__init__.py`) — truthful and
  spelling-independent, costs a network read or checkout during resolution;
- **(c)** a manifest-declared series, e.g. `[cairn] series = "v16"` — cheap, explicit, stable;
- **(d)** drop the half; the tag becomes `<inputhash>` alone — pure, unreadable.

---

## 4. The first live deployment — do this next

The whole deploy path is written. What remains is running it, in this order, and the order is
chosen so that each step is reversible until the last one.

**On the control machine:**

```
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

- **The registry read.** `ADR-036`'s client has never spoken to GHCR. The token flow and the
  media-type set are the parts most likely to need adjusting.
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
  systemd, registry reachability. Currently `doctor` only knows the build/control role, so on a
  target it checks for a vendored tree that is not there. This is the most obvious gap the
  first live run will expose.
- **`ADR-037`** — how an `install-app` opt-in reaches a target. Open, and blocking nothing:
  `reconcile` deliberately never installs. Decide it the first time an app must be added to a
  live environment, based on what was actually needed at that moment.
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
- **Phase 6** — `README.md` / `USAGE.md`. Note that the identifier rule binds from the first
  line of code, not from Phase 6, and `tests/test_conventions.py` enforces it.

---

## Things a fresh session should know before touching anything

These were learned expensively in this session; the full versions are in
`04-lessons-learned.md` §12 and `03-discussion-log.md` (2026-07-25 entries).

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
- **`frappe_docker/` is read-only** (`ADR-001`, `BR-VEND-004`). Manage it only via ventwig.
- **`BR`/`ADR` IDs must never reach user-visible output.** `tests/test_conventions.py` parses
  every non-docstring string in the package. If it fails, the *message* is wrong, not the
  test.
