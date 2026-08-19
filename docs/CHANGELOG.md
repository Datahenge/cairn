# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-08-18 (`06-cli.md` split into three)

Brian asked whether the requirements docs could be split. Measurement said yes, and said which:
`06-cli.md` had reached 4585 words against a ceiling raised twice in one session, and its
role-specific sections (A `cairn-build`, B `cairn-adopt`, C `cairn-registry`) were **57%** of
the file against 42% shared convention.

That mattered because the file's own header justified keeping it whole — "most of what governs
the CLI is shared UX convention applying identically across binaries." True when written,
false by now. Rather than split around a stale justification, the header was rewritten to say
what the structure is and why it changed.

Sections **A** and **B** moved to new `06a-cli-build.md` (1738 words) and `06b-cli-adopt.md`
(831), leaving `06-cli.md` as the area's entry point — substrate, the `cairn-registry` verbs,
the all-three commands, and shared conventions — at 2198 words, **under the 2200 default**, so
its allowlist override was retired outright rather than bumped a third time. Section C stayed
put: at 91 words it would have been a stub.

Worth recording because it validates the mechanism: the retired override carried a note saying
~4500 words was where "an actual split becomes the right call — this ceiling is set to trip a
fresh review before that point, not at it." It did exactly that. It guessed section E (shared
conventions) would be the one to move; measurement pointed at A and B instead.

All 30 `BR-CLI` identifiers verified preserved across the three files, none lost and none
defined twice — the IDs are cited in docstrings and test names, so only their file moved.
`00-overview.md`'s index gained `06a`/`06b` rows and
`docs/technical/25-documentation-authority.md` gained explicit per-file rows, so the routing
rule in `AGENTS.md` still resolves. Documentation process, so no new identifier.

## 2026-08-18 (`BR-DEPLOY-024` + `BR-CLI-029`: the hold and the lifecycle verbs)

`ADR-073`'s decision written into requirements. **`BR-DEPLOY-024`** defines the maintenance
hold — the file `/etc/cairn/hold`, whose presence is the whole signal — and makes *held* a
third `reconcile` outcome, distinct from converged and failed, which is precisely what
`cairn-adopt` could not previously express. Durable rather than in `/run`, with `doctor`
reporting a live hold on every run as a stated condition of that durability.

**`BR-CLI-029`** covers `stop`, `start`, and `restart` in one requirement rather than three,
because their correctness is a property of their interaction: all three run under the
single-flight lock, held once per command. Brian added `restart` with two rules — it clears any
hold it finds, and sets none of its own between the down and the up. The lock, not a hold, is
what protects that interval; a hold would outlive a crashed `restart` and freeze the host,
inverting the command's meaning.

Brian accepted that `restart` is `stop` then `start` rather than `docker compose restart`, and
asked for the divergence from `cairn-registry restart` (`BR-REG-004`) to be documented clearly.
It now appears on **both** sides — `BR-CLI-029` and `BR-REG-004` each state it and its reason —
so neither reads as an oversight. The reason is asymmetric ownership: `compose restart` does not
recreate containers and so cannot pick up an edited compose file; the target's file is
operator-editable by design (`ADR-074`) and picking up such an edit is the motivating case,
while the registry's is cairn-written, leaving the thin wrapper correct there.

An implementation hazard is recorded in `ADR-073` rather than left to be rediscovered:
`reconcile.run()` already acquires the single-flight lock, so a verb that takes the lock and
then delegates to `run()` would block against its own lock.

Three ceilings bumped in `ai/tools/.docs_check_allowlist` to admit this work — `03-deploy.md`
(2700 → 2900), `06-cli.md` (4250 → 4600, which had ten words of headroom), and `ADR-073` itself
(2200 → 2600). Unlike the grandfathered pre-migration entries, these are growth from new
content, and each carries a dated note saying so. Three bumps in one session is the signal that
a split is due rather than another bump; `06-cli.md` is the candidate, and Brian asked for it as
a separate change.

This file itself then tripped its own ceiling by three words. Rather than a fourth bump, `ai/tools/changelog_rotate.py` was run — and **did not crash**, contrary to `W-034`, archiving 2026-08-05 and 2026-08-06 cleanly and leaving 4624 words live. `W-034` is left `open` with the non-reproduction recorded, since nobody has identified what changed.

## 2026-08-18 (`ADR-073` decided: cairn owns the stack's lifecycle verbs)

Brian settled both halves. A human should **not** run `docker compose` directly against a
cairn-managed stack — so `W-037` (an `.env` cairn maintains, or a `compose --` passthrough) is
rejected outright, and `BR-VEND-006`'s `${VAR:?...}` guard stands as the entire answer for an
unsupported attempt: it fails loudly instead of silently starting another vendor's image.
Instead, cairn offers its own verbs so an operator can bring the stack up and down.

That makes the hold state load-bearing rather than optional. `State.is_converged` requires
`stack_up`, so without a hold the timer resurrects a deliberately-stopped stack — `bench
migrate` included — within the poll interval, which would make a `down` verb actively
misleading. Sketch recorded in `ADR-073`: `down` sets the hold and brings the stack down; `up`
clears it and delegates to the existing reconcile path, which already does the right thing for
a stack that is down, so no new convergence logic is needed; `reconcile` reports *held* and
converges nothing while set; `doctor` surfaces it so a forgotten hold cannot hide.

Both remaining details settled the same day. The hold is **durable**, at `/etc/cairn/hold`:
a host rebooting mid-maintenance must stay down, so "down" honestly means down — which makes
`doctor` reporting a live hold on *every* run a requirement of the decision rather than a
nicety, since the cost of durability is that a forgotten hold freezes deploys indefinitely. The
verbs are **`start`/`stop`**, matching `cairn-registry`. A concern raised while deciding — that
compose-`stop` semantics would leave an edited `compose.yaml` ineffective — proved unfounded:
`cairn-registry start` already runs `compose up -d` rather than `compose start`
(`registry_provision.py:294`), and Compose recreates any container whose config hash changed.
Also verified that `stack_is_up` requires `State == "running"` and a stopped container reports
`exited`, so a released hold registers as not-converged with no change to that function.

`ADR-073` is `approved` and fully specified; `W-035` is ready to implement.

## 2026-08-18 (`ADR-074`: cairn seeds the compose file, the operator owns it)

Brian resolved the ownership question `ADR-073` surfaced, framing it across two horizons — this
particular VPS today, and cairn used by dozens of operators tomorrow with `frappe_docker` never
in the picture. His statement of it: **"Help them. But don't take away their control."**

Four commitments: cairn writes the *first* compose file on a fresh install from its owned
recipe; it **never regenerates** it (seed-once, the same pattern `registry_provision.py`
already uses for the fully-commented starter `/etc/cairn/registry.toml`, and what makes
operator edits safe from clobbering); `${CUSTOM_IMAGE}`/`${CUSTOM_TAG}` stay, so cairn keeps
control of *which image* while the operator keeps everything else; and the file is readable and
editable by the operator. Location `/etc/cairn/`, matching `registry.toml` — an earlier draft
argued for `/opt/cairn-target/` by analogy with `ADR-063`, which was the wrong analogy: that
tier is for files cairn *rewrites*, and this one is seeded once. The recipe's `compose.yaml`
uses named volumes exclusively, so no path resolution constrains the choice.

A first draft of `ADR-074` also claimed the decision settled `ADR-073`'s fork, by making an
on-disk `.env` permanent architecture. Brian rejected the premise — the live VPS has no `.env`
at all and works fine — and he was right: cairn injects `CUSTOM_IMAGE`/`CUSTOM_TAG` per
invocation and needs nothing on disk. The claim came from the AI silently widening "the
operator may see and edit the file" into "…and run it by hand", then deriving a requirement
from its own addition. Withdrawn the same day; `ADR-074` and `ADR-073` both carry the
correction in place rather than a quiet deletion, and `W-037` was rewritten from a work item
into the open question it actually is — *is hand-running wanted at all?* — with a
`cairn-adopt compose --` passthrough noted as an alternative that avoids the group-shared
directory entirely. `W-032`/`W-033` updated with the decided shape. `ADR-073` stays open for
factor 3 alone: file ownership gives cairn no way to express "intentionally down", so `W-035`
is unaffected.

## 2026-08-18 (`BR-VEND-006`: the owned recipe no longer substitutes another vendor's image)

Brian's call on `W-036`: drop the default so it fails loudly. New **`BR-VEND-006`** forbids a
fallback on the image reference in the owned recipe, and requires Compose's error-on-unset
form. `src/cairn/recipe/compose.yaml` and `overrides/compose.migrator.yaml` now read
`${CUSTOM_IMAGE:?...}:${CUSTOM_TAG:?...}`, halting before any container starts and naming the
remedy. Plain `${CUSTOM_IMAGE}` was considered and rejected: Compose substitutes an empty
string and emits only a `WARN`, so the failure still arrives late and quietly. `example.env`'s
`ERPNEXT_VERSION` — read by nothing once the fallback was gone — is replaced by explicit
`CUSTOM_IMAGE`/`CUSTOM_TAG` placeholders. The requirement is deliberately scoped to image
*identity*: `PULL_POLICY` and `RESTART_POLICY` keep their defaults, since substituting one of
those cannot silently run somebody else's software.

Guarded by a parametrized test over every compose file in the recipe tree, not just the two
that carried the line, since it gets copied whenever an override is added; mutation-checked by
reinstating the old line and confirming the test fails. Full suite 929 passed. The `${VAR:?...}`
form was then confirmed live the same day on Life Scientific's test VPS (same Compose
syntax, applied by hand to that host's own file): `docker compose config` fails on an unset
variable and renders the correct image when both are supplied.

## 2026-08-18 (`ADR-073` opened: the target stack has no usable lifecycle)

Brian asked how to stop and restart the containers on a client VPS after changing the Compose
YAML. cairn has no answer — `start`/`stop`/`restart` exist only for `cairn-registry`
(`BR-REG-003`/`004`). The working procedure is five steps around a hand-assembled `docker
compose` invocation transcribed out of `/etc/cairn/adopt.toml`; Brian's assessment was
"extremely awkward and impractical."

Tracing why separated inherited awkwardness from self-inflicted. The multi-file override
layering is upstream `frappe_docker`'s, though `BR-DEPLOY-010`'s render-never-store choice
does forgo upstream's usual render-once workaround. The other two factors are cairn's: the
compose variables (`CUSTOM_IMAGE`/`CUSTOM_TAG`/`PULL_POLICY`/`SITES`) are injected per
invocation and never written to disk, so a manual `docker compose up -d` succeeds against a
stale `.env` and silently starts the previous image — a drift cairn's own `_survey_image` and
`stage_reconnoitre` already treat as known; and `State.is_converged` requires `stack_up`, so
an intentionally-stopped stack is indistinguishable from a dead one and the timer resurrects
it, `bench migrate` included. That last one is the real blocker: cairn has no way to express
"intentionally down."

Verified against Life Scientific's test VPS the same day, which **refuted** the guess that it
used the rendered single-file `gitops` pattern its directory name suggests. `erpnext.yaml`
still interpolates; `CUSTOM_IMAGE`/`CUSTOM_TAG` are its only two variables, both carrying
upstream defaults (`${CUSTOM_IMAGE:-frappe/erpnext}`); and no `.env` exists beside it. So a
hand-run `docker compose up -d` on that host silently starts stock `frappe/erpnext:v16.26.1`
— another vendor's image, never carrying the client's apps — with no warning, because a `:-`
default suppresses Compose's unset-variable message. Factor 2 is more severe than first
written, and `ADR-073` was amended accordingly: candidate (a) (write-through `.env`) is
re-rated from "heavier, defer it" to worth doing close behind (b), since on this host the
`.env` cairn would write carries no secret and its creation removes the hazard outright.
`reconcile` was confirmed *not* looping there (zero converge passes in 24h).

Brian then supplied the host's history, which reframed the finding twice over. The client
built the VPS themselves from `frappe_docker`, which reached for **`pwd.yml`** — the
disposable, explicitly non-production demo file — and cairn adopted it later; `/opt/vps-setup/`
is surviving client tooling cairn superseded without displacing. The `.env` that does exist
there sits one directory *above* the Compose project directory, so Compose never reads it, and
carries neither `CUSTOM_IMAGE` nor `CUSTOM_TAG` regardless. That makes the VPS the first
concrete instance of **`W-033`** (`ADR-068`'s take-ownership path), now cross-referenced.

More consequentially, the same fallback turned out to live in **cairn's own recipe**:
`src/cairn/recipe/compose.yaml:5` and `overrides/compose.migrator.yaml:9` both carry
`${CUSTOM_IMAGE:-frappe/erpnext}`, inherited byte-for-byte from `frappe_docker` but owned by
cairn since `ADR-059` — and `W-032` would ship it to every newly-provisioned host. Queued as
`W-036`, with the choice between "drop the default so it fails loudly" and "keep it but detect
the substitution" left to Brian.

**Brian ruled the fix in scope** (an operator has no practical alternative route); the design
is open. `ADR-073` records both candidates — write-through `.env`, and owned lifecycle
commands plus a hold state — with two sub-questions still needing his answer: whether a hold
survives reboot, and whether cairn writing `.env` collides with `BR-DEPLOY-011`'s
secret-agnostic boundary. Queued as `ADR-073` (`needs_user`) in `docs/open/OPEN_DECISIONS.md`
and `W-035` (`blocked`) in `docs/open/OPEN_WORK.md`. No requirement changed yet.

## 2026-08-08 (`ADR-072`: `cairn-adopt-owned` marker; `cairn-adopt prune` fully specified)

Brian asked why `cairn-build images` still held six images on a client VPS after most had
been pushed. Tracing the code against `ADR-061`/`BR-BUILD-008`/`014`/`018` found no bug — six
genuinely distinct input hashes, none superseded, marker correctly stripped on the five
already pushed. The real gap: `ADR-061`'s `cairn-build prune` protects *every* pushed image
unconditionally, forever, because it has no signal for "still in use by a colocated target
role." `ADR-072` closes it: `cairn-adopt` gains a symmetric `cairn-adopt-owned` marker
(`BR-DEPLOY-023`), applied to the image its `backend` container is currently running and
refreshed on **every** `reconcile` pass (including a converged no-op, closing the rollout gap
for hosts that pulled images before this feature existed). `cairn-build prune`'s Restriction 2
(`BR-CLI-018`) is rewritten to protect the `cairn-build-owned` or `cairn-adopt-owned` markers
specifically, rather than any tag at all — a pushed image nothing local is running is now
eligible. `cairn-build images` (`BR-CLI-005`) excludes `cairn-adopt-owned` images entirely
rather than showing them with an absent build marker.

This also fully specifies `BR-DEPLOY-006`/`W-003` (target-side GC), open since 2026-07-24
with no concrete selection rule: a new `BR-CLI-028`, `cairn-adopt prune [--keep <n>]
[--dry-run] [--yes]`, keeps the currently-running image (unconditionally, via the same
running-container digest read `BR-DEPLOY-003b` already uses) plus the newest `--keep`
`cairn-adopt-owned` images, mirroring `cairn-build prune`'s removal mechanics exactly.
`ADR-061` gets a short inline amendment note; its own core decision is unchanged.
`docs/adr/README.md`, `docs/open/OPEN_WORK.md` (`W-003`), and both requirement files' headers
updated to match.

## 2026-08-06 (new lessons-learned topic: Docker & host storage)

Closing out the same client-VPS disk-space incident as the two entries below: six durable
findings recorded in new **`docs/technical/04d-lessons-docker-and-host-storage.md`** —
Docker's `data-root` vs. containerd's independent `root`; disproving a plausible-looking
double-counting theory with `stat -f` rather than trusting matching sizes/timestamps; not
nesting one service's data inside another's managed tree; `sudo`'s glob-expansion-happens-
first gotcha; verifying a device explicitly rather than trusting an implicit `mount
<path>` → `/etc/fstab` lookup on a live migration; and when collapsing to one shared
volume beats textbook per-service isolation. `docs/technical/04-lessons-learned.md`'s
topic index updated to route to it.

## 2026-08-06 (`changelog_rotate.py` could not parse its own generated footer)

Found immediately after writing the entry below: `docs/CHANGELOG.md` tripped `DOC002`'s word
budget, and running the prescribed fix (`ai/tools/changelog_rotate.py --dry-run`) crashed
instead of archiving anything. `render_footer` writes the footer heading as `## Archived
entries`; `parse_changelog`'s block loop only skips a trailing block that does *not* start with
`## ` — so the tool's own output, fed back in on a later run, hit the "not a dated entry"
branch and raised. Bug found and fixed, no requirement redesign: both sites now reference one
`FOOTER_HEADING` constant, and `parse_changelog` explicitly recognizes and discards that exact
block rather than only the no-heading case. Rotation re-run after the fix; archived the five
oldest entries (2026-08-04 through 2026-08-05) to `docs/archive/CHANGELOG-2026-08-04-to-
2026-08-05.md`, confirmed against `docs_check.py` and the full test suite.

## 2026-08-06 (new userdocs guide: Docker storage on a multi-volume host)

Same VPS relocation session that surfaced the `disk-headroom` doctor bug (below): after fixing
`cairn-registry`'s `data_dir`, Brian tried to solve the client VPS's small-root-disk problem
generally by pointing containerd at the big Docker volume too — nesting a directory inside
`/var/lib/docker` and moving files there. That doesn't work: containerd's `root` setting
(`/etc/containerd/config.toml`) is completely independent of Docker's own `data-root`
(`/etc/docker/daemon.json`), and on a host with Docker's containerd image store enabled
(`driver-type: io.containerd.snapshotter.v1`), containerd — not Docker's own graphdriver — is
what actually holds the growing image/container layer bytes. Redirecting only `data-root`
leaves containerd silently defaulting to `/var/lib/containerd`, on whatever volume holds
ordinary `/var/lib` — the small one. Brian: "a huge footgun for anyone running multiple volumes
on a VPS," and asked for it in published docs before it bites someone else.

Not a cairn requirement — this is host-level Docker/containerd configuration, nothing cairn's
own code touches (confirmed: no reference to `containerd` anywhere in `src/` or `docs/`) — so no
`BR`/`ADR` ID, just a new userdocs page: **`userdocs/guides/docker-storage-layout.md`**,
covering how to tell which daemon actually holds the space (`ncdu`, `docker info`, the `moby`
namespace check on containerd's shims) and how to relocate containerd's `root` onto its own
volume rather than nesting it inside `/var/lib/docker` (the same data-root-blast-radius caution
`ADR-060` already applied to `cairn-registry`'s own `data_dir`, here generalized to any
Docker host). Linked from `userdocs/guides/index.md` and, since this needs deciding *before*
first use, from `userdocs/get-started/index.md`'s Prerequisites section. `mkdocs.yml` nav gained
a `Guides` submenu (previously a single flat page) to hold it.

## 2026-08-06 (`cairn-registry doctor`: a `PermissionError` on `data_dir` no longer crashes the disk-headroom check)

Found live while helping Brian relocate a client VPS's `data_dir` off a disk-space-constrained
root filesystem: he'd pointed `[registry] data_dir` at a path under `/var/lib/docker`, which
Docker keeps locked down against non-root traversal by design. `cairn-registry doctor` crashed
with an unhandled `PermissionError` instead of reporting a normal `FAIL` row.

Bug found and fixed, no requirement redesign — `BR-REG-011` already requires `doctor` to report
three checks, not throw: `_check_disk_headroom` (`cli_registry.py`) called `config.data_dir.
exists()` *outside* the function's own `try`/`except OSError` block, so an `EACCES` on an
unreadable parent directory (raised by `exists()` itself, not just the `shutil.disk_usage()`
call two lines below that was already guarded) propagated as an internal-error crash. Fixed by
moving the `.exists()` call inside the existing `try` block — one-line fix, same error-message
shape the `disk_usage()` path already used. New test
(`test_check_disk_headroom_reports_permission_error_as_fail`, `test_cli_registry.py`) exercises
the exact failure mode by monkeypatching `Path.exists` to raise `PermissionError`. Full suite
passes.

## 2026-08-06 (`cairn-build doctor` reports build-timer status; `--all` walks every manifest)

Brian suggested `doctor` mention whether `setup-timer`'s systemd units exist and are
enabled/started — currently only checkable by hand, one `systemctl` call at a time.
`cairn-adopt doctor` already had this for the reconcile timer (`check_reconcile_timer`); the
build side had no equivalent.

Design settled through a short back-and-forth: single-manifest scope (mirroring `github
reachability`) was the obvious first cut, but Brian rejected it — `/srv/cairn/` is a static,
known directory (`BR-CLI-022`), and a build host commonly serves more than one client, so
scoping to one manifest at a time would force an operator to script their own enumeration to
be sure every timer on the host is actually running. Settled on two mutually exclusive scope
flags: `--manifest <path>` (one manifest) and `--all` (every manifest under
`/srv/cairn/*/*.toml`, one result per manifest) — recorded as `ADR-070`. A further question —
whether `--all` should also broaden `config`/`github reachability` into a full per-manifest
host audit — was deliberately deferred rather than folded in; tracked as `ADR-071`
(`docs/open/OPEN_DECISIONS.md`). Bare `cairn-build doctor` (neither flag) is unchanged and
still runs every host-level check, but now reports the build-timer check as skipped, with the
fix, rather than omitting it silently the way `github reachability` does.

**`BR-CLI-007`** (`docs/requirements/06-cli.md`) amended in place: the `cairn-build doctor`
bullet documents the new check and its two scope flags.

**Code:** `provision.build_unit_name`'s naming logic extracted into a pure
`unit_name_for(client, image_name, environment)` so `doctor.py` can compute the same unit name
`setup-timer` would install for any manifest it walks, without duplicating the f-string.
`doctor.py` gains `check_build_timers`/`_check_one_build_timer`/`_known_manifest_paths`; wired
into `run_build_checks`. `cli_build.py`'s `doctor_command` gains `--all`, checked against
`--manifest` via `typer.BadParameter` before either check family runs. Tests added to
`tests/test_doctor.py` and `tests/test_cli_build.py`.

**Same-day follow-up.** Brian, re-reviewing, suspected the *service* also needed to be active,
not just the timer. Checking the actual unit definitions showed both cairn-build's build
service and cairn-adopt's reconcile service are `Type=oneshot` — they run, exit, and return to
`inactive` between firings, so "active" is the unusual state, not the healthy one; his
suggested check would have false-WARNed on every healthy install. The real gap underneath the
hunch was genuine, though: neither check asked whether the *last* run had actually succeeded.
Added `systemctl is-failed` on the service to both `check_build_timers` and — since
`cairn-adopt doctor`'s pre-existing `check_reconcile_timer` had the identical blind spot —
`check_reconcile_timer` too, taking priority over each check's existing enabled/active read. A
failed last run now FAILs the check outright rather than reporting the more benign "not yet
started." `ADR-070` and `BR-CLI-007` amended in place; no new ID minted.

---

## 2026-08-06 (`images` splits by role: `cairn-build` local-only, `cairn-registry` gains `--host`/`--namespace`/`--image`)

Brian flagged `cairn-build images`'s help text as inaccurate — "reads the registry by default"
said nothing about needing a manifest first, and a bare invocation errored outright. First fix
considered was a `--local` fallback; Brian pushed back on the premise instead: examining a
*registry* shouldn't be reached indirectly through a manifest's `image_name`. Settled into a
clean split, restated by Brian as "the builder talks about things the builder owns; the
registry talks about things registries own (a local one, or a remote one)."

**`cairn-build images` (`BR-CLI-005`) becomes `[--json]`, nothing else, unconditionally local.**
No `--manifest`, no `--local` — there is no other mode to flag. `_registry_repository` and the
old registry branch are deleted outright.

**`cairn-registry images` (`BR-REG-005`) gains `--host`/`--namespace`/`--image` and the
provenance detail (frappe/app versions, `cairn-build-owned` marker) the old `cairn-build`
registry mode used to show**, so that capability relocates rather than disappears. Re-reading
the userdocs mid-design surfaced a real constraint: `ghcr-setup.md`/`ghcr-tags-and-
troubleshooting.md` already use the old registry mode against **GHCR**, a real authenticated
third-party registry, which only works because the single-repository read
(`registry.tags`/`inspect`) does the full anonymous-then-bearer-token exchange (`BR-CFG-010`).
`registry.catalog()` — needed to *enumerate* a registry — is anonymous-only by design, scoped
to cairn's own self-hosted registry. Resolved by splitting the lookup: an **exact**
`--namespace` + `--image` (no glob) reads that one repository directly, bypassing the catalog
entirely — this is what keeps GHCR reachable via `docker login`/`podman login`. Any other
combination (no `--image`, or a glob) enumerates via the catalog, which stays limited to
registries that allow anonymous catalog access.

Also fixed incidentally: `cairn-registry images`' "Repository" line printed the bare catalog
name; `userdocs/registry/cli.md` already (incorrectly) documented it as the full reference
with registry host. The rewrite makes the doc's existing claim true.

Recorded as `ADR-069` (`docs/decisions/069-images-splits-by-role-builder-local-registry-remote.md`)
— amends a requirement with a rejected alternative (the `--local`-fallback draft) worth
remembering. `BR-CLI-005`/`BR-REG-005` (`docs/requirements/06-cli.md`,
`docs/requirements/08-registry.md`) rewritten. Code: `cli_build.py`'s `images_command`
simplified; `images.py`'s `registry_as_json` renamed `registry_payload`, now returning a
`dict` so `cli_registry.py` can assemble one multi-repository JSON payload; `cli_registry.py`'s
`images_command` extended, its old `_grouped_tags`/`_repository_json` helpers replaced by
`images.py`'s provenance-aware equivalents. Tests updated in `test_cli_build.py` and
`test_cli_registry.py`. Userdocs updated: `userdocs/builder/index.md` drops its `--local`
example; `userdocs/registry/cli.md`, `ghcr-setup.md`, and `ghcr-tags-and-troubleshooting.md`
now point at `cairn-registry images`.

## 2026-08-06 (`05-implementation-index.md` trimmed — Completion Judgment cells are verdicts, not incident narratives)

Brian flagged the file as wordy/busy right after the `setup-timer` entry below added yet another
paragraph to an already-long cell. Looking at it directly: the "Completion Judgment" column had
drifted from its own stated purpose (a judgment) into full incident retelling — which functions
were renamed, exactly how each bug happened, ADR-by-ADR blow-by-blow — duplicating
`docs/CHANGELOG.md`, which already owns that narrative. The file had grown to 2,271 words,
repeatedly bumping into `docs_check.py`'s word ceiling.

Trimmed every bloated cell to a terse verdict plus a `docs/CHANGELOG.md` pointer for the story
(2,271 → ~1,450 words); table structure, code locations, and test/owner-doc columns untouched.
Process/documentation-hygiene work, not a product decision — no new Decision/ADR file
(`01-documentation-conventions.md`'s own rule). Two guardrails added so this doesn't recur
unnoticed: a short note directly in `05-implementation-index.md`'s intro ("a cell is a verdict,
not a narrative"), and a new "Completion Judgment Cells Stay Terse" section in
`01-documentation-conventions.md` recording this as a cautionary tale, with a checkable rule of
thumb (>~3 sentences in a cell means narrative crept back in) for future documentation review
sessions to catch.

## 2026-08-06 (`setup-timer` output: quieter empty-stop summary, one non-contradictory error message)

Brian's first live `cairn-build setup-timer` run on the Life Scientific test VPS (`W-013`)
refused correctly — a private `erp-lifescientific` repo with no `github-token.env` populated
yet — but the output had two rough edges he flagged as worth polishing while true, not a design
mistake needing a redesign: a `--- summary ---`/`nothing to do` block printed under `Stopped:
...` even though the run had done nothing at all, and the error text gave two remedies that
disagreed — `resolve.py`'s generic hint ("No `$CAIRN_GITHUB_TOKEN` is set — set it and retry")
assumes an interactive build reading the invoking shell, while `setup-timer`'s own check
(`ADR-067`) deliberately reads only the client's token file, never the shell. "Set it and
retry" is actively wrong advice on that path.

Two in-place fixes, no requirement redesign — bugs found and fixed, not a rejected alternative
worth a Decision/ADR file (`01-documentation-conventions.md`'s own rule):

- **`setup_runner.py`**: `execute()`'s `Aborted`/`KeyboardInterrupt` handlers now skip the
  `--- summary ---` block entirely when `Report.is_empty()` — new method, also now the single
  source of truth `_summarize()`'s own "nothing to do" fallback reuses (previously that check
  omitted `report.revert`, a latent inconsistency fixed as a side effect). A stage header
  (`[timers]`, `[preflight]`, …) stays as-is: three existing tests
  (`test_cli_build.py`/`test_cli_adopt.py`/`test_cli_registry.py`) assert on it as proof that
  `setup-timer` runs only its own stage, not `setup`'s — genuinely informative, not noise.
- **`github_auth.py`** gained `missing_token_hint()`, the single source of truth for the
  generic "set it and retry" sentence `resolve.py`'s `_run()` now calls instead of inlining.
  `provision.py`'s `_check_timer_github_reachability` strips that exact sentence
  (`str.removesuffix`) before appending its own file-based remedy, so the operator sees one
  fix, not two. `resolve.py`'s own message is unchanged for every other caller (a plain build
  failure still correctly points at the operator's own shell, per `BR-BUILD-016` point 5).

`docs/requirements/06-cli.md`'s `BR-CLI-023` paragraph amended in place to describe the
stripped hint. `docs/open/OPEN_WORK.md`'s `W-013` row updated; still open (`setup-timer`'s
happy path — a working token file — remains unexercised against a real host).

## 2026-08-06 (recipe tree flattened — no more nested `frappe_docker/`, `images/custom/`, or `resources/core/`)

Follow-on to the same-day trim below: Brian asked to flatten what remained. The nested
`frappe_docker/` subdirectory is gone — `compose.yaml`, `overrides/`, `example.env`,
`images/`, and `resources/` now sit directly under `src/cairn/recipe/`. `images/custom/`
collapsed to `images/` and `resources/core/` to `resources/`, since neither had a sibling
left to be distinguished from (the alternate `bench`/`layered`/`production` Containerfiles and
frappe_docker's own `docs/`-nested `core`/other resource groupings were already dropped in the
trim). `frappe_docker/LICENSE` folded into `ATTRIBUTIONS_FRAPPE_DOCKER.md` verbatim rather than
kept as a separate file. Pure scaffolding reorganization — no new ADR (`01-documentation-
conventions.md`'s own rule for this), `BR-VEND-005` and `BR-VEND-001`/`003` in
`docs/requirements/01-vendoring.md` updated in place instead. Code: `vendor.py`'s
`FRAPPE_DOCKER_DIR`/`FRAPPE_DOCKER_SOURCE` collapsed into one `RECIPE_DIR`;
`CUSTOM_CONTAINERFILE` now `images/Containerfile`; the Containerfile's own `COPY` lines
repointed at `resources/`. `pyproject.toml`'s ruff `extend-exclude` and `ai/tools/
docs_check.py`'s `EXCLUDED_PATHS` both updated to the flattened root. Docs swept for the old
paths: `02-build.md`, `00-coding-standards.md`, lessons-learned `04b`/`04c`, `AGENTS.md`,
`userdocs/builder/index.md`, `userdocs/reference/index.md`. `tests/test_vendor.py` updated to
match; full suite passes.

## 2026-08-06 (recipe tree trimmed to load-bearing files; `ADR-068` grows cairn's scope to initial provisioning)

Two related changes, same session, both prompted by Brian: make `src/cairn/recipe/frappe_docker/`
actually cairn's own rather than the untouched byte-for-byte bootstrap copy `ADR-059` left
behind.

- **Recipe trim + attribution (`BR-VEND-005`).** Deleted everything under
  `src/cairn/recipe/frappe_docker/` that no cairn code path reads and that isn't part of the
  compose scaffolding cairn now commits to owning (see next item): upstream's own docs site,
  test suite, CI workflows, contributor/devcontainer tooling, community-health files, `pwd.yml`
  (the unparameterized quick-start compose shape `ADR-021`'s fork-pressure incident already
  flagged as the wrong one), `docker-bake.hcl` (redundant with cairn's own `build.py` build
  orchestration), and the three alternate Containerfiles (`images/bench`, `images/layered`,
  `images/production`) `BR-BUILD-009` never builds. Kept: the build inputs
  `assert_build_inputs()` already required, plus `compose.yaml`/`overrides/*.yaml`/`example.env`
  (see below), and `LICENSE`. New `src/cairn/recipe/ATTRIBUTIONS_FRAPPE_DOCKER.md` credits
  `frappe/frappe_docker` and links to the preserved `LICENSE`; `BR-VEND-005` added to
  `docs/requirements/01-vendoring.md` requiring both be kept current.
- **`ADR-068`: cairn's scope grows to initial provisioning, not just reconcile.** Trimming the
  compose scaffolding raised the question of whether `compose.yaml`/`overrides/*.yaml` were dead
  weight too, since `cairn-adopt` never reads cairn's own copy — it inspects whatever's already
  on the target host. Brian's answer: no, because cairn replacing `frappe_docker` means owning
  the whole lifecycle, not just build+reconcile-against-whatever-exists. Cairn's owned Compose
  stack is now the intended way to provision a *new* environment, and `cairn-adopt` should
  eventually be able to take over ownership of a pre-existing hand-built deployment rather than
  reading around it forever. Neither is built yet — both queued as `W-032`/`W-033` in
  `docs/open/OPEN_WORK.md`, design work only. The `DATA` boundary (`ADR-022`) and
  `BR-DEPLOY-007`'s `bench new-site`/database-creation clause are explicitly unchanged; only the
  "existing environments only" framing around them was amended.

## 2026-08-06 (`.docs_check_allowlist` relocated into `ai/tools/`)

Brian pointed out the allowlist lived at the repo root while everything that reads or writes
it — `docs_check.py`, `changelog_rotate.py` — lives in `ai/tools/`. Moved the file to
`ai/tools/.docs_check_allowlist` (`git mv`, preserving history) and added `docs_check.py`'s
`ALLOWLIST_REL = Path("ai/tools") / ALLOWLIST_FILENAME`, resolved as `root / ALLOWLIST_REL` so
`--root` still targets the checked project's own copy rather than the script's location.
`changelog_rotate.py` already imported `load_word_count_allowlist` from `docs_check`, so its one
hardcoded write path (`_append_allowlist_entry`) just switched to the same constant. `AGENTS.md`'s
artifact table updated to note `ai/tools/` now also holds the data file, not just the two
scripts. Process/tooling-only per the rule above — this entry, no new ID.

---

## Archived entries

Older entries are moved out once this file grows past its word-count budget
(`.docs_check_allowlist`), by `tools/changelog_rotate.py` — each archive covers a
contiguous range, newest-first within it same as here.

- [CHANGELOG-2026-07.md](archive/CHANGELOG-2026-07.md)
- [CHANGELOG-2026-08-03.md](archive/CHANGELOG-2026-08-03.md)
- [CHANGELOG-2026-08-04-early.md](archive/CHANGELOG-2026-08-04-early.md)
- [CHANGELOG-2026-08-04.md](archive/CHANGELOG-2026-08-04.md)
- [CHANGELOG-2026-08-04-to-2026-08-05.md](archive/CHANGELOG-2026-08-04-to-2026-08-05.md)
- [CHANGELOG-2026-08-05-to-2026-08-06.md](archive/CHANGELOG-2026-08-05-to-2026-08-06.md)
