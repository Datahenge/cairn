# `cairn-adopt` — command surface

Every `cairn-adopt` command. For what the target role does and why, see
[Target](../target/index.md); for the everyday verbs in context, see [Operating the
Stack](../target/operating.md). This page is just the command surface.

Every command here reads the host's own environment descriptor, `/etc/cairn/adopt.toml`, and
derives the compose project, compose files, and site from it. That is why almost none of them
takes an argument — there is only ever one host to describe, and it has already been
described. None of them touches your database or volumes.

## reconcile

```bash
cairn-adopt reconcile --dry-run
cairn-adopt reconcile
```

Converges this host to whatever image its environment's tag currently points at: pull, stop,
start, migrate. Idempotent, and **single-flight** — a second invocation while one is running
exits immediately rather than queueing. On failure it stops and reports; it never rolls back
on its own.

Honours a maintenance hold: while one is in place, this reports the environment as *held* and
changes nothing. See [The hold](../target/operating.md#the-hold).

Flags: `--dry-run` — show what would converge, change nothing.

## Everyday operation

```bash
cairn-adopt logs                      # every service
cairn-adopt logs -f --tail 200 backend
cairn-adopt shell                     # the bench container
cairn-adopt shell db                  # another service
cairn-adopt console                   # bench console, this environment's site
cairn-adopt mariadb                   # MariaDB console, this environment's site
```

- **`logs [service]`** — container logs; every service by default. `--follow` / `-f` keeps
  printing until interrupted; `--tail <n>` limits trailing lines per container.
- **`shell [service]`** — an interactive shell inside a container, defaulting to the bench
  container. This is cairn's answer to "show me `site_config.json`" — cairn will not print
  your secrets, but it will put you where you can read them yourself.
- **`console`** — `bench console` for this environment's site. No arguments.
- **`mariadb`** — a MariaDB console for this environment's site. No arguments. Refuses, naming
  the engine, on a stack that declares the Postgres override.

## stop / start / restart

```bash
cairn-adopt stop --reason "adding a port mapping"
cairn-adopt start
cairn-adopt restart
```

- **`stop`** — brings the environment down **and holds it there**. It will not converge again
  until `start`, including across a reboot. `--reason <text>` records a note in the hold for
  whoever finds it.
- **`start`** — releases the hold and brings the environment back up, converging it to its
  tag. No flags.
- **`restart`** — both in one step. Clears a hold if it finds one, says so, and never leaves
  the environment held even if it fails partway. No flags.

None of these removes a container or touches a volume.

## prune

```bash
cairn-adopt prune --dry-run
cairn-adopt prune --keep 2 --yes
```

Removes images this target previously ran, reclaiming disk. The image the stack is currently
running is protected unconditionally — read from the running container, not guessed from
recency — and volumes and containers are never touched. Full detail, including why `--keep`
is a grace window rather than a rollback guarantee, is in [Reclaiming
disk](../target/operating.md#reclaiming-disk).

Flags:

- `--keep <n>` — superseded images to keep for rollback headroom. Default `1`, minimum `1`.
- `--dry-run` — show what would be removed, remove nothing.
- `--yes` — don't ask for confirmation. The prompt otherwise defaults to *no*.

## examine

```bash
cairn-adopt examine
cairn-adopt examine --environment staging --manifest /srv/cairn/acmecorp/cairn_staging.toml
```

Reads the deployment already running on this host and prints an environment descriptor for
it. **Writes nothing** — review the output, then install it yourself, or let `setup` do it.

Flags:

- `--environment <name>` — name for this environment in the descriptor. Default `production`.
- `--project <name>` — which compose project to read. Defaults to the only one running.
- `--manifest <path>` — cross-check this manifest's apps against what the site actually has.

## doctor

```bash
cairn-adopt doctor
```

Checks that this machine can converge: Docker and Compose, the descriptor, the reconcile
timer, the registry tag — and reports a live maintenance hold on **every** run, since a
forgotten one silently suspends deployments. No flags; changes nothing.

## setup

```bash
sudo cairn-adopt setup --dry-run
sudo cairn-adopt setup
```

Provisions this machine to converge: shared config under `/etc/cairn`, a backup, and an
installed descriptor. Must be run with `sudo`. Idempotent.

Flags:

- `--dry-run` — print every action, change nothing.
- `--force` — replace existing files; the old ones are kept alongside.
- `--only <stage>` — run one stage: `preflight`, `admin-group`, `recon`, `backup`, or
  `descriptor`.
- `--environment <name>` — name for this environment in the descriptor. Default `production`.
- `--project <name>` — which compose project to adopt and back up.
- `--skip-backup` — do not back up before changing anything.
- `--workdir <path>`, `--skip-disk-free`, `--admin-group <name>` / `--no-admin-group` — as for
  [`cairn-build setup`](cairn-build.md#setup).

## setup-timer

```bash
sudo cairn-adopt setup-timer --interval 5min
```

Installs — but does **not** start — the reconcile-automation timer. Must be run with `sudo`.
Starting it is a deliberate second step; see [Reconcile
Automation](../target/automation.md).

Flags: `--interval <span>` (default `5min`), plus `--dry-run`, `--force`, and `--workdir`.

## systemd-units

```bash
cairn-adopt systemd-units --interval 5min --user root
```

Prints the systemd service and timer for `cairn-adopt reconcile` to stdout and **installs
nothing** — for review, or for a host where you'd rather place the units yourself.

Flags: `--interval <span>` (default `5min`), `--user <name>` (default `root`).
