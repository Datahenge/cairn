# Next Steps

_Written 2026-07-25, at the end of the session that produced `ADR-031` and `ADR-032`.
Revised later the same day: `cairn prune` verified on the machine, and the CLI layer tested._

A resumption point for a fresh session. Read `/CLAUDE.md` first (the working agreement),
then this. Everything below is downstream of requirements that are already written; where a
decision is still open it says so explicitly, and **an open decision is not an invitation to
guess** — ask.

---

## Where things stand

Phase 4 (modular code) is under way. Implemented and tested (282 tests, ruff clean, 94%
statement coverage; `cli.py` at 100%):

| Command | Requirements | State |
| --- | --- | --- |
| `cairn build` | `BR-CLI-002`, `BR-BUILD-*` | Working end-to-end against a real registry |
| `cairn push` | `BR-CLI-003` | Working |
| `cairn images --local` | `BR-CLI-005` | Working; **registry mode not implemented** |
| `cairn prune` | `BR-CLI-018` | Working; verified on the real machine 2026-07-25 |
| `cairn doctor` | `BR-CLI-007` | Working |
| `cairn vendor status\|sync` | `BR-CLI-006` | Working |
| `new-tag` / `retag` / `retire` | `BR-CLI-004`, `BR-CLI-009/010` | Not started |
| `reconcile` | `BR-CLI-008` | Not started |

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

## 4. Remaining command surface

In dependency order:

1. **`cairn images` registry mode** (`BR-CLI-005`, `BR-DEPLOY-005`) — provenance labels read
   over the registry manifest API without pulling. Currently `cairn images` without
   `--local` fails with a message saying so, rather than pretending.
2. **`new-tag` / `retag` / `retire`** (`BR-CLI-004`, `BR-CLI-009`, `BR-CLI-010`) — the
   pointer verbs, with existence guards and the production confirmation gate.
3. **`reconcile`** (`BR-CLI-008`, `BR-DEPLOY-001/003/016`) — the target-side pull loop.

`DEPLOY` requirements are written and approved; these are implementation, not design.

---

## 5. Smaller carried items

- **Registry-backed cache** (`--cache-to` / `--cache-from`). No help for a warm local
  rebuild; large help for a cold CI runner. Weaker on podman, which `ADR-027` requires we
  keep supporting. Not yet a requirement.
- **A coverage floor.** `pytest-cov` is now a declared dev dependency and the package sits at
  94%. A `--cov-fail-under` floor was deliberately *not* added: putting `--cov` in
  `addopts` makes every plain `pytest` run fail without the plugin installed. Decide the
  trade before adding it.
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
