---
status: authoritative
owner: requirements
purpose: BR-CLI requirements — the command surface and UX conventions across all CLI entry points.
---

# BR-CLI — Command Surface & UX Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-08-03_

The command surface across cairn's **three CLI entry points**, one file sectioned by role
(`05-config.md`'s `A`/`B` split, precedent) rather than separate area files — most of what
governs the CLI is shared UX convention (logging, `--json`, config discovery, help text)
applying identically across binaries. Mostly *cites* verbs defined in other areas; adds the
create/move/retire guards, global flags, and output/exit conventions. Conventions:
`/CLAUDE.md`. Decisions cited: `ADR-003`, `ADR-023`, `ADR-031`, `ADR-042`, `ADR-043`,
`ADR-046`, `ADR-048`, `ADR-052`.

---

## Substrate

**`BR-CLI-001`** — cairn is **one package** (`datahenge-cairn`, `ADR-046`, `ADR-048`) exposing
**three** console-script CLIs (Click/Typer, `ADR-003`), each its own Typer app: **`cairn-build`**
(build/control), **`cairn-adopt`** (target), **`cairn-registry`** (registry host). No unified
`cairn` command, no alias — the binary invoked is itself the role signal. *(ADR-003, ADR-046,
ADR-048)*

## A. `cairn-build` commands (build/control)

**`BR-CLI-002`** *(build)* — `cairn-build build [--push] [--manifest <path>] [--no-cache]
[--dry-run]` — build the image from `cairn.toml` (resolve refs → apps.json → tagged image +
provenance labels). **Default is build-only**; `--push` also uploads. *(BR-BUILD-*)*

**`BR-CLI-002a`** *(build's optional `--assign-tag`, `ADR-052`)* — `build` MAY be given
`--assign-tag` (boolean, no value): after a successful `--push` (or a no-op short-circuit,
`BR-BUILD-014`/`014a`), it performs the same retag step `assign-tag` (`BR-CLI-004`) does,
reusing the digest `build` already resolved rather than re-running `assign-tag`'s own
resolve-and-check from scratch. `--assign-tag` without `--push` MUST be refused as a
contradiction — nothing was pushed to retag. The `:production` gate (`BR-CLI-010`) applies the
same as it does to standalone `assign-tag`. *(BR-BUILD-014a, BR-CLI-004, BR-CLI-010, ADR-052)*

**`BR-CLI-003`** *(push)* — `cairn-build push [--id <tag>]` — upload a built image to the
registry (default: the current manifest's just-built image). *(BR-BUILD-*, BR-CFG-011)*

**`BR-CLI-004`** *(pointer verbs — assign / retire, `ADR-052`)* — Neither command takes an
environment name as an argument; both take `--manifest <path>` and read the environment from
the file (`BR-DEPLOY-009a`).

- `cairn-build assign-tag --manifest <path> [--yes] [--dry-run]` — resolves the manifest's refs
  to their **current** commits, computes the deterministic primary tag (`BR-BUILD-008`), and
  checks the registry. **Found:** retags the manifest's declared environment onto that digest
  (server-side, no rebuild) and reports it. **Not found:** reports that and does **nothing** —
  `assign-tag` MUST NOT trigger a build. There is no selector menu (`--latest`/`--previous`/
  `--id`/`--from`, `ADR-050`, retired) — there is only ever one well-defined answer: what the
  manifest's own refs currently, factually resolve to.
- `cairn-build retire --manifest <path>` — **decommission** the manifest's declared environment
  from cairn (see `BR-CLI-009`).

An earlier draft added an opt-in `--install-app <apps>` here. It was **struck** 2026-07-25
(`ADR-037`, `BR-DEPLOY-003a`): installing a Frappe App is the operator's act, not a pointer
move's. *(BR-DEPLOY-004, BR-DEPLOY-003a, ADR-023, ADR-052)*

**`BR-CLI-005`** *(introspection)* — `cairn-build images [--tags] [--local] [--json]`.

- **Registry** (default) — tags, digests, and provenance labels read **remotely**, no pull.
  *(BR-DEPLOY-005)*
- **`--local`** — the same question asked of the build machine: which images does *this*
  machine hold, why does each exist, and which are superseded. cairn MUST identify its own
  images by their provenance labels (`BR-BUILD-011`), MUST group them by **input hash**, and
  MUST show, per image, its tags — or that it has **none** — along with age, size, and the
  resolved Frappe/app commits read from labels.

An engine's own image listing answers only repository, tag, id, age and size, so an untagged
former build is indistinguishable from anything else untagged. Every fact needed to explain
it is already stamped on the image; this is the command that reads them back. Images cairn
did not build MUST be excluded, but their count MUST be reported, so the command is never
mistaken for a complete inventory. *(BR-DEPLOY-005, BR-BUILD-011, BR-BUILD-014, ADR-032)*

**`BR-CLI-006`** *(vendor)* — `cairn-build vendor status | sync` — thin ventwig wrappers.
*(BR-VEND-*)*

**`BR-CLI-009`** *(no declared environment, no auto-vivification, `ADR-052`)* — `assign-tag
--manifest <path>` and `retire --manifest <path>` MUST **error if that manifest declares no
environment** (`<path> declares no environment`) — there is nothing to point or decommission.
Since a manifest declares at most one environment (`BR-DEPLOY-009a`), there is no "wrong name"
to guard against — only "no name at all."

Whether the environment's registry pointer already exists is a separate, later question
`assign-tag` answers by resolving and checking the registry (`BR-CLI-004`), never by refusing
up front.

`retire --manifest <path>` removes the declaration from that manifest (the operator's edit,
not cairn's — cairn only validates and warns), touches **no images**, and MUST warn that the
**registry tag name persists** (GHCR has no per-tag delete — see `03-deploy.md`).
*(BR-DEPLOY-009, BR-DEPLOY-009a, ADR-052)*

**`BR-CLI-010`** *(prod gate)* — Any command that creates, moves, or retires a
**`:production`** pointer MUST require **explicit confirmation** — interactive prompt by
default, `--yes` to skip for automation. *(BR-DEPLOY-015)*

**`BR-CLI-016`** *(build transcript — attended CLI only)* — cairn recognises **three
execution contexts** (`ADR-031`), and writes a transcript in exactly one of them:

| Context | Behavior |
| --- | --- |
| Target daemon (systemd) | stdout/stderr only (`BR-DEPLOY-019`) |
| Unattended CLI (CI) | stdout/stderr only |
| **Attended CLI** (human at a terminal) | terminal **and** transcript file |

- Attendedness MUST be detected from **stderr being a TTY**, and MUST be overridable in
  both directions by `--transcript <path>` and `--no-transcript`.
- In attended mode cairn MUST write the full build output to a transcript **and** keep it
  streaming live to the terminal — the transcript replaces neither the live output nor
  the operator's ability to `tee`.
- Attended builds MUST request **plain, append-only** engine progress, so both scrollback
  and the transcript stay readable. Unattended contexts are unaffected.
- The default location MUST be `/tmp/cairn-<uid>/`, created mode `0700`; cairn MUST refuse
  to use it if it exists and is not owned by the invoking user, or is not a real directory.
  Files are named `<timestamp>--<image_name>.log` — from the **manifest's** image name, not
  the built tag, because the file must be open before ref resolution can compute a tag and
  the resolution is itself part of what the transcript records. The primary tag is written
  into the transcript instead. A `last-build.log` symlink points at the newest, and a
  `last-failure.log` symlink is updated on failure so a later success cannot bury it.
- The transcript path MUST be printed **when the build starts and when it ends**, so the
  path survives an interrupted run or a lost terminal.
- A failed build MUST retain its transcript.
- The location MUST be overridable by `transcript_dir` in build config (`BR-CFG-008`).

*(ADR-031, BR-CFG-008, BR-DEPLOY-019)*

**`BR-CLI-018`** *(prune — build machine)* — `cairn-build prune [--keep <n>] [--dry-run] [--yes]`
reclaims space on the **build** machine, under three concentric restrictions:

1. Only images carrying cairn's own provenance labels (`BR-BUILD-011`) are candidates.
2. Of those, only images holding **no tag** may be removed. A tag is a name something else
   may rely on, and removing a tagged image would require the engine's `--force`, which
   cairn MUST NOT pass — a removal needing force is one to report, not perform.
3. Of those, only images beyond the newest `<n>` of their **input hash** (default 1).
   `<n>` counts a group's newest members whether tagged or not, so `--keep 2` leaves the
   current image plus one predecessor as rollback headroom — `BR-DEPLOY-006`'s keep-last-N,
   applied per input hash because images under different hashes are different images, not
   each other's history.

cairn MUST NOT remove volumes or containers under any option (`ADR-022`), MUST report what
it will remove and confirm first (`BR-CLI-011`), and MUST state what it is leaving alone so
the omission is never a surprise. A removal that fails MUST NOT abort the rest.

**Label-scoping is a cache-safety mechanism, not merely tidiness.** On podman, an untagged
image may be a **build-cache stage** rather than a former build — the `builder` stage of the
vendored Containerfile is untagged, larger than the final image, and is what lets a rebuild
skip `bench init`. A prune written against "dangling" would delete it and silently convert
every later build into a cold one. cairn's labels are applied only at the **final** commit,
so a stage image never carries them, and a label-scoped prune cannot reach the cache. cairn
MUST therefore never prune by danglingness. *(BR-DEPLOY-006 is the target-side counterpart;
this is its build-machine analogue. ADR-032, lessons §12)*

## B. `cairn-adopt` commands (target)

**`BR-CLI-008`** *(reconcile)* — `cairn-adopt reconcile` — the target-side, single-flight
pull-loop verb, run under systemd. *(BR-DEPLOY-001/003/016)*

**`BR-CLI-019`** *(systemd units — emitted by default, installable via `setup`)* —
`cairn-adopt systemd-units` MUST print a ready-to-install systemd **service** and **timer**
for `cairn-adopt reconcile` to stdout, and, invoked on its own, MUST NOT write them to the
host or reload the daemon (`ADR-035`). The emitted unit MUST reflect what cairn knows and
the operator would otherwise guess: `Type=oneshot`, no custom log file (journald owns the
record, `BR-DEPLOY-019`), and a cadence consistent with `reconcile` being idempotent and
single-flight (`BR-DEPLOY-016`) so an overrunning pass cannot stack. Because a unit is
host-specific, the command MUST report the values it assumed (binary path, user, cadence)
rather than silently choosing them. Installing the unit for real is `cairn-adopt setup`'s
job (`BR-CLI-021`), not this command's. *(BR-DEPLOY-001, BR-DEPLOY-008, BR-DEPLOY-016,
BR-DEPLOY-019, ADR-035, ADR-046)*

**`BR-CLI-020`** *(examine — derive a descriptor from a running deployment)* —
`cairn-adopt examine` MUST read an **existing** frappe_docker deployment on this host and
**print** a draft environment descriptor (`BR-DEPLOY-010a`). It MUST NOT write any file,
install anything, or alter the running stack — it is a read-and-print command, exactly as
`BR-CLI-019` is. (Named `examine`, not `adopt` — the CLI itself is `cairn-adopt`; a
subcommand repeating the program's own name read as a stutter and, worse, wrongly implied
this command changes something, when it is a strict survey. See `ADR-046`.)

Together with `systemd-units`, this fixes cairn's rule for host configuration:

> **cairn prints host configuration for review; only the explicit, privilege-gated `setup`
> subcommand (`BR-CLI-021`) — never an ordinary command — installs it.**

It MUST derive, from the live stack rather than from anything the operator states:

- the compose **project** and the compose **files in use**, and from those the frappe_docker
  directory and which `overrides/compose.*.yaml` are layered;
- the **site name(s)** and each site's **installed apps**;
- the **image and tag currently running**;
- the `.env` in use.

Site names MUST be read from the filesystem (`sites/<name>/site_config.json`), never parsed out
of `bench --site all list-apps`'s own formatting: that command's site-header convention has
varied across Frappe versions — measured on 16.26.1, a single-site host omits the header
entirely and prints a flat app list — and treating it as the source of site names turns a version
difference into a false multi-site stop, or worse, zero apps found on an ordinary host. Installed
apps MAY still come from `list-apps`, filtered against the already-known site names rather than
by indentation.

It MUST **report gaps rather than guess**: anything it cannot determine is named, with the reason,
and left absent from the output. A plausible default silently inserted here becomes a wrong deploy
later.

When auto-detecting the project (no `--project` given) and more than one compose project is
running, `examine` MUST exclude any project containing a container cairn itself stood up as
supporting infrastructure (e.g. a local registry stood up by `cairn-registry setup`, `ADR-048`),
so that infrastructure never forces a `--project` disambiguation the site did not cause.
Exclusion MUST be by an explicit label cairn writes into its own compose files, never by a
project's **name** — a name is only ever the default compose derives from a directory, something
an operator's own project could coincidentally share. An explicit `--project` naming a
cairn-managed project anyway MUST still be honored — exclusion applies only to guessing, never to
a stated choice.

Given a manifest it MUST **cross-check** the manifest's ordered app list (`BR-BUILD-003`) against the
site's installed apps and report disagreement — a mismatch means `bench migrate` would run against
code the site does not expect, which is the likeliest way a first deploy fails.

It MUST report when the deployment serves **more than one site**, because `reconcile` sets `SITES`
from a descriptor naming exactly one (`BR-DEPLOY-014`), and converging such a host would drop the
others. That condition is a **stop**, not a warning to be worked around.

The emitted descriptor MUST be **loadable**: whatever `examine` prints, `BR-DEPLOY-010a`'s reader
must accept. *(BR-DEPLOY-010a, BR-DEPLOY-014, BR-BUILD-003, BR-CLI-019, ADR-034, ADR-046)*

## C. `cairn-registry` commands (registry host)

Surface only — substance is `BR-REG` policy, cited not restated.

**`BR-CLI-024`** — `status|start|stop|restart` (`BR-REG-004`); `images [--json]` (`BR-REG-005`).

**`BR-CLI-025`** *(prune)* — `[--dry-run] [--yes]`; `BR-REG-006`/`007`'s retention algorithm;
no-op unless `[registry.retention] enabled = true` (`BR-CLI-011`).

**`BR-CLI-026`** *(gc)* — `[--dry-run] [--yes]`; reclaims blobs `prune` freed (`BR-REG-009`);
MUST report its read-only window first, require `--yes`/`--dry-run` (`BR-CLI-010`).

**`BR-CLI-027`** *(setup-timer)* — emits, never installs (`ADR-035`), a `prune`+`gc` timer on
`[registry.gc] schedule` (`BR-REG-010`, `BR-CLI-019`/`023`).

## D. Commands on all three CLIs

**`BR-CLI-007`** *(doctor)* — Each CLI runs exactly **one** fixed check set — no role
detection, no context-sniffing (`ADR-028` superseded, `ADR-046`): the binary invoked already
answers which checks apply. Each accepts `--manifest` where relevant (`BR-CLI-014`); a missing
manifest warns rather than fails, since doctor legitimately runs before one exists.

- **`cairn-build doctor`** — the selected build engine present and capable of secret-mount
  builds (Docker Engine v23+, or podman v4+ — `ADR-027`); free disk under its data root and
  available memory, `setup`'s own preflight floors (`BR-DEPLOY-021`), reported here too;
  **`git`**, which cairn resolves every manifest ref with (`BR-BUILD-005`); `ventwig status`
  clean; config valid; `/etc/cairn`'s current group, permissions, and the invoking user's
  membership, reported only, never mutated (`BR-CFG-015`, `ADR-043`); and, extending the
  existing known-manifests listing (`BR-CLI-022`), a **duplicate-declaration check**
  (`ADR-052`): every `.toml` found under a client's directory is read for its `image_name` +
  `environment`, and any (`image_name`, `environment`) pair repeating within that client MUST
  be reported — case-insensitively, so `staging` and `Staging` collide. This is validation
  only; no command resolves an environment name to a manifest this way, per `BR-DEPLOY-009a`.
- **`cairn-adopt doctor`** — Docker Engine + Compose, systemd, registry reachability;
  `/etc/cairn`'s current group, permissions, and membership, reported only, as above.
- **`cairn-registry doctor`** — reachable over HTTPS, cert validity, disk headroom under
  `data_dir` (`BR-REG-011`).

*(BR-VEND-005/006, BR-BUILD-005, BR-CFG-015, BR-CLI-014, BR-REG-011, ADR-027, ADR-043, ADR-046,
ADR-048)*

**`BR-CLI-021`** *(setup — the privileged installer, nested per role)* — Each CLI carries its own
`setup` (`cairn-build setup`, `cairn-adopt setup`, `cairn-registry setup`), replacing the
retired `cairn-provision` (`ADR-046`) — `cairn-registry setup` is `BR-REG-003`, migrated from
`cairn-build setup`'s former `"registry"` stage (`ADR-048`). No `--role` flag: each `setup`
provisions only its own role. Excludes build/reconcile/registry-maintenance automation — see
`BR-CLI-023`/`027`.

`setup` MUST check that it is running with the privilege its actions require (root, or the
configured equivalent) and MUST exit, reporting the shortfall, rather than attempt a partial run
without it. Beyond that gate, it MUST satisfy the same seven-point installer contract as before
(`BR-DEPLOY-021`) — idempotent; offers `--dry-run`; never silently overwrites; handles no secrets;
gates all prerequisite checks before any change; verifies its own postconditions; and is never the
only path, since every action it takes MUST remain documented for an operator to perform by hand.
`ADR-043`'s `/etc/cairn` group-sharing stage runs as part of it unchanged. *(BR-DEPLOY-021,
BR-DEPLOY-022, ADR-040, ADR-043, ADR-046)*

**`BR-CLI-022`** *(canonical manifest home + scaffolding, `ADR-047`, `ADR-052`)* — `cairn-build
setup` requires `--client <name>` (no default; omitting it fails) and provisions
`/srv/cairn/<name>/` — creating `/srv/cairn/` first if absent — group-shared like `/etc/cairn`
(`BR-CLI-021`, `ADR-043`). Cairn MUST NOT read, list, or assume anything about sibling paths
under `/srv` — only `/srv/cairn/` is its namespace.

`setup` also requires `--environment <name>` and scaffolds a **distinctly-named** manifest,
`/srv/cairn/<client>/cairn_<environment>.toml`, if absent — from the canonical illustrative
manifest (`README.md`/`userdocs/reference/manifest.md`, `BR-BUILD-003`'s ordered-list comment
included, `[cairn] environment` pre-filled), so a client directory holding several environments
holds several distinctly-named files, per `BR-DEPLOY-009`'s 1:1 model. An existing file MUST
NOT be modified (`BR-DEPLOY-021`). `doctor` MAY report manifests found under
`/srv/cairn/*/*.toml`, informationally and for the duplicate-declaration check (`BR-CLI-007`),
never for selection — `BR-CLI-014` is unchanged. *(BR-BUILD-003, BR-CLI-014, BR-DEPLOY-009,
BR-DEPLOY-021, ADR-043, ADR-047, ADR-052)*

**`BR-CLI-023`** *(setup-timer, `ADR-047`, `ADR-052`)* — Both CLIs carry a `setup-timer`
subcommand, separate from `setup`, installing only the build/reconcile systemd timer —
enabled, not started, unchanged in substance from `ADR-046`'s `setup --only timers`. Split out
for discoverability in `--help`, where a first-time reader would otherwise miss the flag
before their first manual build or reconcile. Takes `--manifest <path>` only — no
`--environment` flag; the unit names are parameterized from the manifest's own declared
environment (`cairn-build-<environment>.service`/`.timer`), so `setup-timer` for two different
manifests coexists on one host. `cairn-build`'s script runs `build --push --assign-tag --yes`,
then `prune --keep 1 --yes` — disk cleanup rides the same script rather than a separate timer
(`ADR-051`), and the retag step rides `build`'s own `--assign-tag` flag (`BR-CLI-002a`) rather
than a second command. *(ADR-046, ADR-047, ADR-051, ADR-052)*

## E. Shared conventions (all three CLIs)

**`BR-CLI-011`** *(least surprise)* — Nothing consequential is silent: no auto-rollback
(`ADR-025`), no auto-install (`ADR-023`), no data/volume/DB writes of cairn's own
(`ADR-022`). Consequential/destructive actions confirm; `--dry-run` is available on
`cairn-build build`/`push`/`assign-tag` and on `cairn-adopt reconcile`.

**Silence cuts both ways.** A command MUST NOT appear to do nothing: any operation that
takes more than a moment (ref resolution, image build, push) MUST report what it is doing
and what it is doing it to, and MUST verify its own post-condition rather than trusting an
exit code — an engine that exits 0 without producing the image MUST be reported as a
failure, not as success. *(ADR-022, ADR-023, ADR-025)*

**`BR-CLI-012`** *(logging & exit codes)* — cairn logs **only to stdout/stderr**
(`BR-DEPLOY-019`) and MUST return **meaningful exit codes** (0 success, non-zero failure)
so systemd and CI detect outcomes. *(BR-DEPLOY-019)*

**`BR-CLI-013`** *(output)* — Human-readable by default; **`--json`** on read/introspection
commands (`images`, `vendor status`, `doctor`) for CI/scripting. *(—)*

**`BR-CLI-014`** *(config discovery)* — cairn resolves the manifest (`cairn.toml`) only from
`--manifest` or `$CAIRN_MANIFEST` — never by searching a directory (`ADR-042`) — resolves
build config from `/etc/cairn/builder.toml` plus `CAIRN_*` environment-variable overrides, and
(on targets) reads the environment descriptor from its fixed path. Every command that accepts a
manifest exposes `--manifest`, so the flag is always available even where `$CAIRN_MANIFEST` is
not set. Precedence is specified by `BR-CFG-012`. *(BR-CFG-008, BR-CFG-012, ADR-029, ADR-042)*

**`BR-CLI-015`** *(help & errors)* — Every command has `--help`; errors are actionable and
name the fix; convention over configuration. *(—)*

**`BR-CLI-017`** *(timing)* — Any command that can take more than a moment MUST report
**start time, end time, and elapsed duration**, plus **per-phase** elapsed times, to the
terminal and the transcript. Timing MUST NOT be recorded in provenance labels: duration is
a property of a build *run* (cache state, machine, network), not of the image's inputs,
and `BR-BUILD-013`'s guarantee is about inputs. *(ADR-031, BR-CLI-011)*
