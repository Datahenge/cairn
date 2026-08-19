---
status: authoritative
owner: requirements
purpose: BR-CLI requirements — the command surface and UX conventions across all CLI entry points.
---

# BR-CLI — Command Surface & UX Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-08-08_

The command surface across cairn's **three CLI entry points**. This file is the area's entry
point: substrate, the `cairn-registry` verbs, the commands common to all three binaries, and
shared UX conventions. The two largest role sections live beside it —
[06a-cli-build.md](06a-cli-build.md) and [06b-cli-adopt.md](06b-cli-adopt.md).

Until 2026-08-18 this was one file, on the reasoning that most of what governs the CLI is
shared convention. Growth overtook that — role-specific content had reached 57% — so the two
largest role sections moved out. `cairn-registry`'s stayed: at 91 words it would be a stub.
Identifiers did not change; only their file did.

Mostly *cites* verbs defined in other areas; adds the create/move/retire guards, global flags,
and output/exit conventions. Conventions:
`/CLAUDE.md`. Decisions cited: `ADR-003`, `ADR-023`, `ADR-031`, `ADR-042`, `ADR-043`,
`ADR-046`, `ADR-048`, `ADR-052`, `ADR-061`, `ADR-069`, `ADR-072`.

---

## Substrate

**`BR-CLI-001`** — cairn is **one package** (`datahenge-cairn`, `ADR-046`, `ADR-048`) exposing
**three** console-script CLIs (Click/Typer, `ADR-003`), each its own Typer app: **`cairn-build`**
(build/control), **`cairn-adopt`** (target), **`cairn-registry`** (registry host). No unified
`cairn` command, no alias — the binary invoked is itself the role signal. *(ADR-003, ADR-046,
ADR-048)*

## A. `cairn-build` commands (build/control)

Moved to **[06a-cli-build.md](06a-cli-build.md)**.

## B. `cairn-adopt` commands (target)

Moved to **[06b-cli-adopt.md](06b-cli-adopt.md)**.

## C. `cairn-registry` commands (registry host)

Surface only — substance is `BR-REG` policy, cited not restated.

**`BR-CLI-024`** — `status|start|stop|restart` (`BR-REG-004`); `images [--host] [--namespace]
[--image] [--json]` (`BR-REG-005`).

**`BR-CLI-025`** *(prune)* — `[--dry-run] [--yes]`; `BR-REG-006`/`007`'s retention algorithm;
no-op unless `[registry.retention] enabled = true` (`BR-CLI-011`).

**`BR-CLI-026`** *(gc)* — `[--dry-run] [--yes]`; reclaims blobs `prune` freed (`BR-REG-009`);
MUST report its read-only window first, require `--yes`/`--dry-run` (`BR-CLI-010`).

**`BR-CLI-027`** *(setup-timer)* — emits, never installs (`ADR-035`), a `prune`+`gc` timer on
`[registry.gc] schedule` (`BR-REG-010`, `BR-CLI-019`/`023`). The generated script is written
to `PROJECT_DIR` (`/opt/cairn-registry`), not the invoking shell's working directory
(`ADR-062`, `ADR-063`).

## D. Commands on all three CLIs

**`BR-CLI-007`** *(doctor)* — Each CLI runs exactly **one** fixed check set — no role
detection, no context-sniffing (`ADR-028` superseded, `ADR-046`): the binary invoked already
answers which checks apply. Each accepts `--manifest` where relevant (`BR-CLI-014`); a missing
manifest warns rather than fails, since doctor legitimately runs before one exists.

- **`cairn-build doctor`** — the selected build engine present and capable of secret-mount
  builds (Docker Engine v23+, or podman v4+ — `ADR-027`); free disk under its data root and
  available memory, `setup`'s own preflight floors (`BR-DEPLOY-021`), reported here too;
  **`git`**, which cairn resolves every manifest ref with (`BR-BUILD-005`); config valid;
  `/etc/cairn`'s current group, permissions, and the invoking user's
  membership, reported only, never mutated (`BR-CFG-015`, `ADR-043`); and, extending the
  existing known-manifests listing (`BR-CLI-022`), a **duplicate-declaration check**
  (`ADR-052`): every `.toml` found under a client's directory is read for its `image_name` +
  `environment`, and any (`image_name`, `environment`) pair repeating within that client MUST
  be reported — case-insensitively, so `staging` and `Staging` collide. This is validation
  only; no command resolves an environment name to a manifest this way, per `BR-DEPLOY-009a`.
  When a manifest was found, doctor also **resolves every one of its refs live**
  (`resolve.resolve_manifest`, `ADR-067`) — the same call `build` itself makes — reporting
  FAIL with the `RefResolutionError` message (already actionable per `BR-BUILD-016` point 5)
  on any failure, including an unauthenticated `github.com` app. Uses whichever
  `$CAIRN_GITHUB_TOKEN` the invoking shell has exported, mirroring `build`'s own interactive
  path. Skipped, not failed, when no manifest was found.

  Also reports **build-timer status** (`setup-timer`'s units, `BR-CLI-023`), scoped by
  mutually exclusive `--manifest` (one) or `--all` (every manifest under `/srv/cairn/`,
  `BR-CLI-022`) — neither given reports the check as skipped, not omitted (`ADR-070`). The
  service is `Type=oneshot` — inactive between runs by design — so "active" alone can't say
  the last run succeeded; `systemctl is-failed` on the service is checked too and FAILs
  ahead of the timer's own enabled/active state (`ADR-070`).
- **`cairn-adopt doctor`** — Docker Engine + Compose, systemd, registry reachability;
  `/etc/cairn`'s current group, permissions, and membership, reported only, as above. Its
  reconcile-timer check applies the same `is-failed`-takes-priority reasoning (`ADR-070`).
- **`cairn-registry doctor`** — reachable over HTTPS, cert validity, disk headroom under
  `data_dir` (`BR-REG-011`).

*(BR-VEND-003, BR-BUILD-005, BR-BUILD-016, BR-CFG-015, BR-CLI-014, BR-CLI-022, BR-CLI-023,
BR-REG-011, ADR-027, ADR-043, ADR-046, ADR-048, ADR-067, ADR-070)*

**`BR-CLI-029`** *(target lifecycle — `stop`, `start`, `restart`)* — `cairn-adopt` MUST provide
these three verbs, so an operator never invokes `docker compose` directly against a
cairn-managed deployment (`ADR-073`; a direct invocation is not merely unsupported but unsafe,
which `BR-VEND-006` makes fail loudly rather than silently).

All three MUST run under the single-flight lock (`BR-DEPLOY-016`), held once for the whole
command, so a timer firing mid-command exits on the lock rather than interleaving. Because
`reconcile` already takes that lock, a verb delegating to it MUST NOT acquire it a second time.

- **`stop`** — set the hold (`BR-DEPLOY-024`), then `docker compose stop`. Containers are kept;
  volumes are never touched (`BR-DATA-005`).
- **`start`** — clear the hold, then perform an ordinary reconcile pass (`BR-DEPLOY-003`). It
  MUST NOT carry its own convergence logic: a stopped stack is already not converged, so the
  existing path pulls, recreates, migrates, and health-checks correctly.
- **`restart`** — clear the hold if one is present, and **MUST NOT** set a hold of its own for
  the interval between down and up; the single-flight lock is what protects that interval, and
  a hold would outlive a crashed `restart`, leaving the host frozen — the opposite of what the
  command means. It MUST report having cleared a hold, since silently resuming a host somebody
  deliberately took down is a surprise worth one line of output.

**`restart` is `stop` then `start`, NOT `docker compose restart`** — a deliberate divergence
from `cairn-registry restart` (`BR-REG-004`), which is a thin `compose restart` wrapper.
`compose restart` does not recreate containers, so it cannot pick up an edited compose file;
the target's compose file is operator-editable by design (`ADR-074`), and picking up such an
edit is the motivating case for these verbs existing. The registry's is not operator-editable,
so the thin wrapper remains correct there. Same verb, different mechanics, for a stated reason.

All three MUST be idempotent — `stop` on a stopped stack, `start` on a running one — succeeding
and reporting the existing state rather than erroring, and MUST refuse to run without a
descriptor (`BR-DEPLOY-010a`). *(BR-DEPLOY-016, BR-DEPLOY-024, ADR-073, ADR-074)*

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

**`BR-CLI-023`** *(setup-timer, `ADR-047`, `ADR-051`, `ADR-052`, `ADR-062`, `ADR-064`, `ADR-065`)* — Both CLIs carry
a `setup-timer` subcommand, separate from `setup`, installing only the build/reconcile
systemd timer — enabled, not started, unchanged in substance from `ADR-046`'s
`setup --only timers`. Split out for discoverability in `--help`, where a first-time reader
would otherwise miss the flag before their first manual build or reconcile. Takes
`--manifest <path>` only — no `--environment` flag; the environment `cairn-build`'s script
advances is read from the manifest itself, per `ADR-052`.

**`cairn-build setup-timer`'s unit name is `cairn-build-<client>-<image_name>-<environment>`**
(`.service`/`.timer`) — every part of `ADR-052`'s uniqueness key
`(client, image_name, environment)`, not `environment` alone. `environment` and `image_name`
alone would collide across two different clients that happen to share either name — the exact
situation a build host serving more than one client (`BR-CLI-022`) can produce. `client` and
`image_name` are derived from the manifest's own location and content, never a second flag
that could disagree with it. The manifest given to `setup-timer` MUST resolve to
`/srv/cairn/<client>/<file>.toml` — the layout `cairn-build setup --client <name>` provisions
(`BR-CLI-022`) — or the command MUST stop, reporting why, rather than fall back to a weaker,
collision-prone name. The generated build script is written to that same client directory,
`/srv/cairn/<client>/<unit>.sh`, never to the invoking shell's working directory: the
directory is already the group-shared, non-user-specific home `ADR-047` established, and a
script build automation depends on MUST NOT live somewhere a retired operator account or a
cleaned-up home directory can take it down. **Every host-specific value the generated `.service`
carries follows the same rule** (`ADR-064`): `WorkingDirectory=` is the script's own directory,
not the operator's `cwd` at the moment `setup-timer` ran — `cairn-build setup-timer` takes no
`--workdir` at all, since nothing in the stage reads one. `cairn-build`'s script runs
`build --push --assign-tag --yes`, then `prune --keep 1 --yes` — disk cleanup rides the same
script rather than a separate timer (`ADR-051`), and the retag step rides `build`'s own
`--assign-tag` flag (`BR-CLI-002a`) rather than a second command.

**The generated `.service` carries `EnvironmentFile=-/etc/cairn/<client>/github-token.env`**
(`ADR-065`) — optional (the leading `-`; a client with no private apps needs no file there at
all), never written by cairn (`BR-BUILD-016`: cairn stores no secrets), and scoped to this
one client: a build host serving several clients (`BR-CLI-022`) gets one such file per client,
each referenced only by that client's own generated unit, never a single shared token
assumed to work for every client. Populating it (`CAIRN_GITHUB_TOKEN=<token>`, mode `0600`,
root-owned) is the operator's job, same as installing the unit itself.

**`setup-timer` gates on that file actually working, before writing or enabling anything**
(`ADR-067`, `BR-DEPLOY-021` point 5). It resolves every ref in the manifest
(`resolve.resolve_manifest`) using only what the eventual unit's `EnvironmentFile=` would
supply — the token parsed from `github_token_env_file(client)` if that file exists,
otherwise none — deliberately **not** the invoking operator's own exported
`$CAIRN_GITHUB_TOKEN`, since the unit never inherits that either. A failure refuses the
whole run (script, service, and timer all unwritten) and reports the same actionable
message `BR-BUILD-016` point 5 gives a failed build, naming the expected file — minus its
generic "set it and retry" hint (assumes a shell), replaced by the file-based remedy so the
operator sees one fix, not two. A pass means the manifest already resolves under the
credentials the timer will have, so no separate warning is printed.
*(ADR-046, ADR-047, ADR-051, ADR-052, ADR-062, ADR-064, ADR-065, ADR-067)*

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
commands (`images`, `doctor`) for CI/scripting. *(—)*

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
