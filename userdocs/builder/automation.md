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

Nothing further is required before starting it, even for an environment you've never used
before — see below.

## What it actually runs

`setup-timer` writes a small script — `build-and-advance.sh`, next to the manifest — and a
systemd service + timer that runs it. The script does three things, in order:

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn.toml --push
cairn-build assign-tag production --latest --yes --manifest /srv/cairn/acmecorp/cairn.toml
cairn-build prune --keep 1 --yes
```

`build --push` is already an idempotent change detector: with no new commits, it resolves refs,
sees the input hash is already built, and exits without building or pushing again — so the timer
firing every 15 minutes costs almost nothing when there's nothing new. `assign-tag` only runs,
and only moves or creates the pointer, when a new image was actually built; on the very first
scheduled run against a brand-new environment, it creates the pointer instead of failing — there
is no separate manual step to run before starting the timer, even the first time. `prune` then
removes anything the build just superseded on this machine's own local disk, so the timer also
keeps disk use bounded without a second, separate job.

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
