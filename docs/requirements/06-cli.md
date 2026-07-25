# BR-CLI — Command Surface & UX Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-07-25_

The `cairn` command surface. Mostly *cites* verbs defined in other areas; adds the
create/move/retire guards, global flags, and output/exit conventions. Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-003`, `ADR-018`, `ADR-023`, `ADR-031`.

---

## Substrate

**`BR-CLI-001`** — cairn is a **single Python CLI** (Click/Typer, `ADR-003`), invoked as
`cairn` (distribution `datahenge-cairn` + `datahenge-cairn` alias), with subcommands. One
package. *(ADR-003, ADR-018)*

## Command surface

**`BR-CLI-002`** *(build)* — `cairn build [--push] [--manifest <path>] [--no-cache]
[--dry-run]` — build the image from `cairn.toml` (resolve refs → apps.json → tagged image +
provenance labels). **Default is build-only**; `--push` also uploads. *(BR-BUILD-*)*

**`BR-CLI-003`** *(push)* — `cairn push [--id <tag>]` — upload a built image to the registry
(default: the current manifest's just-built image). *(BR-BUILD-*, BR-CFG-011)*

**`BR-CLI-004`** *(pointer verbs — create / move / retire)* —
- `cairn new-tag <env> <selector>` — **create** a new environment pointer.
- `cairn retag <env> <selector>` — **move** an existing pointer (server-side retag, no
  rebuild).
- `cairn retire <env>` — **decommission** an environment from cairn (see `BR-CLI-009`).

Selectors for `new-tag`/`retag`: `--latest | --previous | --id <ident> | --from <env>`
(`--from` points at whatever another env currently runs → cross-env promotion). Both accept
opt-in **`--install-app <apps>`** (`ADR-023`). *(BR-DEPLOY-004, ADR-023)*

**`BR-CLI-005`** *(introspection)* — `cairn images [--tags] [--local] [--json]`.

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

**`BR-CLI-006`** *(vendor)* — `cairn vendor status | sync` — thin ventwig wrappers. *(BR-VEND-*)*

**`BR-CLI-007`** *(doctor)* — `cairn doctor` — **role-aware** preflight, role detected from
context (`ADR-028`). On a **build/control** machine: the selected build engine present and
capable of secret-mount builds (Docker Engine v23+, or podman v4+ — `ADR-027`); **`git`**,
which cairn resolves every manifest ref with (`BR-BUILD-005`); `ventwig status` clean;
config valid. On a **target**: Docker Engine + Compose, systemd, and registry
reachability. *(BR-VEND-005/006, BR-BUILD-005, BR-CLI-014, ADR-027, ADR-028)*

**`BR-CLI-008`** *(reconcile)* — `cairn reconcile` — the target-side, single-flight
pull-loop verb, run under systemd. *(BR-DEPLOY-001/003/016)*

## Guards & safety

**`BR-CLI-009`** *(existence guards; no auto-vivification)* — Environment existence is
determined by cairn's **declared environment list** (control-side, `BR-DEPLOY-009`).
- `new-tag <env>` MUST **error if `<env>` already exists**.
- `retag <env>` / `retire <env>` MUST **error if `<env>` does not exist**
  (`No such environment '<env>'`).

`retire <env>` removes `<env>` from the declared list, touches **no images**, and MUST warn
that the **registry tag name persists** (GHCR has no per-tag delete — see `03-deploy.md`).
*(BR-DEPLOY-009)*

**`BR-CLI-010`** *(prod gate)* — Any command that moves or retires a **`:production`**
pointer MUST require **explicit confirmation** — interactive prompt by default, `--yes` to
skip for automation. `--install-app` against Production is **doubly** explicit. *(BR-DEPLOY-015)*

**`BR-CLI-011`** *(least surprise)* — Nothing consequential is silent: no auto-rollback
(`ADR-025`), no auto-install (`ADR-023`), no data/volume/DB writes of cairn's own
(`ADR-022`). Consequential/destructive actions confirm; `--dry-run` is available on
`build`/`push`/`new-tag`/`retag`/`reconcile`.

**Silence cuts both ways.** A command MUST NOT appear to do nothing: any operation that
takes more than a moment (ref resolution, image build, push) MUST report what it is doing
and what it is doing it to, and MUST verify its own post-condition rather than trusting an
exit code — an engine that exits 0 without producing the image MUST be reported as a
failure, not as success. *(ADR-022, ADR-023, ADR-025)*

## Conventions

**`BR-CLI-012`** *(logging & exit codes)* — cairn logs **only to stdout/stderr**
(`BR-DEPLOY-019`) and MUST return **meaningful exit codes** (0 success, non-zero failure)
so systemd and CI detect outcomes. *(BR-DEPLOY-019)*

**`BR-CLI-013`** *(output)* — Human-readable by default; **`--json`** on read/introspection
commands (`images`, status) for CI/scripting. *(—)*

**`BR-CLI-014`** *(config discovery)* — cairn discovers the manifest (`cairn.toml`), build
config (`~/.config/cairn/config.toml` + optional `cairn.local.toml`), and (on targets) the
environment descriptor; the common case needs **no flags** (minimal typing). Precedence is
specified by `BR-CFG-012`. *(BR-CFG-008, BR-CFG-012, ADR-029)*

**`BR-CLI-015`** *(help & errors)* — Every command has `--help`; errors are actionable and
name the fix; convention over configuration. *(—)*

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

**`BR-CLI-017`** *(timing)* — Any command that can take more than a moment MUST report
**start time, end time, and elapsed duration**, plus **per-phase** elapsed times, to the
terminal and the transcript. Timing MUST NOT be recorded in provenance labels: duration is
a property of a build *run* (cache state, machine, network), not of the image's inputs,
and `BR-BUILD-013`'s guarantee is about inputs. *(ADR-031, BR-CLI-011)*

**`BR-CLI-018`** *(prune — build machine)* — `cairn prune [--keep <n>] [--dry-run] [--yes]`
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

**`BR-CLI-019`** *(systemd units — emitted, never installed)* — `cairn systemd-units` MUST
print a ready-to-install systemd **service** and **timer** for `cairn reconcile` to stdout,
and MUST NOT write them to the host or reload the daemon (`ADR-035`). The emitted unit MUST
reflect what cairn knows and the operator would otherwise guess: `Type=oneshot`, no custom
log file (journald owns the record, `BR-DEPLOY-019`), and a cadence consistent with
`reconcile` being idempotent and single-flight (`BR-DEPLOY-016`) so an overrunning pass cannot
stack. Because a unit is host-specific, the command MUST report the values it assumed
(binary path, user, cadence) rather than silently choosing them. *(BR-DEPLOY-001,
BR-DEPLOY-008, BR-DEPLOY-016, BR-DEPLOY-019, ADR-035)*
