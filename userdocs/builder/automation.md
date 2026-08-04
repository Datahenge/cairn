# Build Automation

Repeats the manual build → push → point-an-environment sequence from [Builder](index.md) on a
schedule, unattended. Do this only after that sequence has worked by hand at least once — a
timer that fires before a manifest is confirmed working turns one wrong configuration into a
wrong deploy every few minutes.

## Install the timer

```bash
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn.toml --environment production
```

`--build-interval` controls the cadence (default `15min`). This installs and **enables** the
timer but does not **start** it — cairn prints exactly this after it runs:

```
cairn-build.timer is enabled but NOT started — run the first build by hand first,
then `systemctl start cairn-build.timer`
```

## What it actually runs

`setup-timer` writes a small script — `build-and-advance.sh`, next to the manifest — and a
systemd service + timer that runs it. The script does two things, in order:

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn.toml --push
cairn-build retag production --latest --yes --manifest /srv/cairn/acmecorp/cairn.toml
```

`build --push` is already an idempotent change detector: with no new commits, it resolves refs,
sees the input hash is already built, and exits without building or pushing again — so the timer
firing every 15 minutes costs almost nothing when there's nothing new. `retag` only runs, and
only moves the pointer, when a new image was actually built.

## Before you start the timer: point the environment once by hand

`retag` refuses to run against an environment whose registry pointer has never been created —
that's deliberate (see the [manifest reference](../reference/manifest.md#cairnenvironments)).
Which means: the *first* time this timer fires against a brand-new environment, `retag` fails,
because nothing has pointed at it yet. Before running `systemctl start cairn-build.timer` for an
environment you haven't used before, create its pointer once by hand:

```bash
cairn-build new-tag production --latest
```

After that, every scheduled run is an ordinary `retag`, and there's nothing further to do by
hand.

## It doesn't clean up local disk yet

`setup-timer` only wires the build/retag pair above — it does not run `cairn-build prune`.
Superseded local images accumulate on the build machine until you remove them yourself:

```bash
cairn-build prune --dry-run   # see what would go
cairn-build prune
```

Run this by hand periodically, or as your own cron/timer, until build automation covers it.

## Verify it's actually running

Each of cairn's three timers has its own systemd unit name, so you don't need to wade through
all of journald — filtering to one unit already scopes the output to just that timer:

| Role | Unit |
| --- | --- |
| Build machine | `cairn-build.service` / `cairn-build.timer` |
| Target (`cairn-adopt reconcile`) | `cairn-reconcile.service` / `cairn-reconcile.timer` |
| Registry host | `cairn-registry-maintenance.service` / `cairn-registry-maintenance.timer` |

```bash
# Next/last trigger for every cairn timer on this host, at a glance:
systemctl list-timers --all | grep cairn

# That unit's own output, scoped — not all of journald:
journalctl -u cairn-build.service --since -1d
```
