# Reconcile Automation

Repeats `cairn-adopt reconcile` from [Target](index.md) on a schedule, unattended — a target
never listens for anything and never receives a push; it only polls outbound. Do this only
after a manual `reconcile` has worked at least once on this host — a timer that fires before
that's confirmed turns one wrong descriptor into a wrong deploy every few minutes.

## Install the timer

```bash
sudo cairn-adopt setup-timer --dry-run
sudo cairn-adopt setup-timer
```

`--interval` controls the poll cadence (default `5min`). This installs and **enables** the
timer but does not **start** it — cairn prints exactly this after it runs:

```
cairn-reconcile.timer is enabled but NOT started — run `cairn-adopt reconcile` by hand first,
then `systemctl start cairn-reconcile.timer`
```

Watch the first manual `reconcile` succeed (see [Target](index.md#run-reconcile)), then:

```bash
sudo systemctl start cairn-reconcile.timer
```

Unlike the build side, there's only ever one reconcile timer per host — a target watches
exactly one environment, so there's no `--manifest` and no per-environment unit name to
choose.

## What it actually runs

`setup-timer` doesn't write a script the way `cairn-build`'s does — `reconcile` is already the
whole of what needs to run, so the timer calls it directly:

```
ExecStart=cairn-adopt reconcile
```

Each pass reads the environment's tag, and does nothing at all unless the digest it resolves
to has changed since the last pass — the common case under a 5-minute poll, since most passes
land between deploys. `Type=oneshot` with no `Restart=` means a failed pass is left failed and
visible in `systemctl status`/journald rather than retried in a loop against a migration that's
already failed once.

## If you'd rather install it by hand

`systemd-units` prints the same two units without installing anything — useful for a host
where you want to review or customize them before they exist on disk at all:

```bash
cairn-adopt systemd-units --interval 5min
```

```
Assumed for this host:
  executable   /usr/local/bin/cairn-adopt
  user         root
  interval     5min (plus up to 30s of jitter)
  unit names   cairn-reconcile.service, cairn-reconcile.timer

# --- /etc/systemd/system/cairn-reconcile.service ---
[Unit]
Description=cairn — converge this host to its environment's desired state
...

# --- /etc/systemd/system/cairn-reconcile.timer ---
[Unit]
Description=cairn — poll for a moved deploy pointer
...

To install, review the units above, then:
  sudo tee /etc/systemd/system/cairn-reconcile.service < the service section
  sudo tee /etc/systemd/system/cairn-reconcile.timer   < the timer section
  sudo systemctl daemon-reload
  sudo systemctl enable --now cairn-reconcile.timer
Then watch it with: journalctl -u cairn-reconcile.service -f
```

`setup-timer` is still the recommended path for an ordinary host — it does the same install,
enabled but not started, without the copy-paste.

## Verify it's actually running

```bash
# Next/last trigger for every cairn timer on this host, at a glance:
systemctl list-timers --all | grep cairn

# Just this timer's own output, not all of journald:
journalctl -u cairn-reconcile.service --since -1d
```

See [Build Automation: verify it's actually
running](../builder/automation.md#verify-its-actually-running) for the same pattern across all
three roles, including the unit-name table.
