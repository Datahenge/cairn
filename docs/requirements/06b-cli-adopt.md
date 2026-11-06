---
status: authoritative
owner: requirements
purpose: BR-CLI requirements — the `cairn-adopt` command surface (target role).
---

# BR-CLI — `cairn-adopt` Command Surface

_Split out of `06-cli.md` on 2026-08-18; identifiers unchanged. Shared UX conventions, the
commands common to all three binaries, and the `cairn-registry` verbs remain in
[06-cli.md](06-cli.md), which is the entry point for this area._

---

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

**`BR-CLI-028`** *(prune — target machine, `ADR-072`)* — `cairn-adopt prune [--keep <n>]
[--dry-run] [--yes]` reclaims target disk:

1. Only images carrying `cairn-adopt-owned` (`BR-DEPLOY-023`) are candidates — never
   `cairn-build`'s own images.
2. The running `backend` container's own image (`BR-DEPLOY-003b`) is unconditionally
   protected regardless of `--keep`; beyond that, only images past the newest `<n>` (default
   1, a grace window not a rollback guarantee) are removed.

Removal mechanics match `BR-CLI-018`: no engine `--force`, tag-by-tag removal, a failed
removal MUST NOT abort the rest. cairn MUST NOT remove volumes or containers (`ADR-022`), MUST
report and confirm first (`BR-CLI-011`), and MUST state what it leaves alone.
*(BR-DEPLOY-003b, BR-DEPLOY-006, BR-DEPLOY-023, BR-BUILD-018, BR-CLI-018, ADR-022, ADR-072)*

**`BR-CLI-030`** *(inspection verbs — `console`, `mariadb`, `logs`)* — `cairn-adopt` MUST provide
these three, each deriving site, project, and compose files from the descriptor so that none
requires an argument (`ADR-075`). They close the gap `ADR-073` left: an operator forbidden to
run `docker compose` by hand still needs a console and logs.

- **`console`** — `bench console` for the descriptor's site.
- **`mariadb`** — `bench mariadb` for the descriptor's site. MUST refuse, with a message naming
  the engine, when the descriptor layers the `postgres` override. Best-effort: a hand-built
  stack may use Postgres without declaring it.
- **`shell [SERVICE]`** — an interactive shell inside a container, defaulting to the bench
  container. This is deliberately cairn's answer to "show me `site_config.json`": `BR-DATA-006`
  forbids cairn reading that file or `common_site_config.json` at all, and `BR-DEPLOY-011`
  forbids it handling secret values — `site_config.json` carries `db_password`. A shell lets the
  operator read their own config with no credential passing through cairn or its output. cairn
  MUST NOT gain a verb that prints either file.
- **`logs [--follow] [--tail N] [SERVICE]`** — compose logs, defaulting to the whole project.
  Bounded flags only; there MUST NOT be a passthrough for arbitrary arguments.

`console` and `mariadb` MUST allocate a TTY (never `-T`) and MUST replace the process rather
than run compose as a child, so the terminal and its signals belong to the client. All three
MUST NOT take the single-flight lock (`BR-DEPLOY-016`) — a session may last hours and would
otherwise block every deploy — and MUST work while a hold is set (`BR-DEPLOY-024`), since a
hold is when an operator most wants to look. *(BR-CLI-029, BR-DEPLOY-024, ADR-073, ADR-075)*

**`BR-CLI-031`** *(`container-info` — the stack's containers, plainly)* — `cairn-adopt
container-info` MUST list the containers of the descriptor's compose project, and only that
project: another project on the same host (a registry, an unrelated application) is not this
environment and MUST NOT appear. It derives project and compose files from the descriptor, so it
takes no argument (`ADR-075`). It MUST show, one line per container, sorted by service: the
**service**, the container **name**, the short (12-character) container **ID**, the **image**,
and the engine's **status** text (which carries health where the container defines a check). It
MUST NOT show the command or ports columns `docker container ls` does; their width is what makes
that listing hard to read. Stopped containers MUST be listed too, since `stop` keeps them
(`ADR-073`) and a held stack is exactly when an operator looks. An empty project MUST say so
rather than print a bare header. It is read-only: it MUST NOT take the single-flight lock
(`BR-DEPLOY-016`) and MUST work while a hold is set (`BR-DEPLOY-024`). *(BR-CLI-030, ADR-073,
ADR-075)*

**`BR-CLI-032`** *(`cp` — operator-directed file transfer, `ADR-080`)* — `cairn-adopt cp SOURCE
DEST` MUST copy a file or directory between the host and a container of the descriptor's compose
project, in either direction, by running `docker compose cp` scoped to that project. Exactly one
of `SOURCE` and `DEST` MUST name a container, as `SERVICE:PATH`; cairn MUST refuse, before
running anything, when neither or both do. A host-side path MUST be made absolute against the
operator's working directory before compose sees it, so its meaning cannot shift with compose's
project directory.

cairn MUST NOT choose, default, inspect, or rewrite what is copied or where: both paths are the
operator's, verbatim apart from the host side's absolutizing. That is what keeps `cp` on the
operator's side of `BR-DATA-003` and `BR-DATA-006` (`ADR-080`). It MUST NOT accept arbitrary
extra compose arguments (`ADR-075`). Like `BR-CLI-030`'s verbs it MUST NOT take the
single-flight lock and MUST work while a hold is set. *(BR-CLI-030, BR-DATA-003, BR-DATA-006,
ADR-075, ADR-080)*

