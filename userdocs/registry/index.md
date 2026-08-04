# Registry

Provisioning and operating a self-hosted local registry with `cairn-registry`. Only needed if
you chose the self-hosted option — see [About container
registries](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md)
for the tradeoffs against a client-owned cloud registry or GHCR. Assumes cairn is already
installed — see [Get Started](../get-started/index.md) if it isn't yet.

`cairn-registry` is independent of the builder and target roles: it reads no manifest and no
`[cairn] environment` — every decision comes from `/etc/cairn/registry.toml`
(optional; sane defaults apply if it's absent) and the registry's own API.

## Provision it

```bash
sudo cairn-registry setup --dry-run   # review every action first
sudo cairn-registry setup
```

This generates a self-signed TLS certificate, trusts it system-wide and with Docker, and
starts the registry as a `docker compose` project. Verify with `doctor`:

```bash
cairn-registry doctor
```

Expected once provisioned:

```
OK   reachable       127.0.0.1:5000 — 0 repositor(y/ies)
OK   certificate     /etc/cairn/registry.crt valid
OK   disk headroom   82 GB free at /opt/cairn-registry/data

All 3 checks passed.
```

## Keep disk use bounded

Every build's content-hash tag accumulates in the registry forever unless something prunes
it — cairn never deletes a digest that still carries a moving series tag (like `v16`) or a
declared environment tag (like `production`), so this is safe to run unattended:

```bash
cairn-registry prune --dry-run   # report what retention would delete
cairn-registry gc --dry-run      # report what garbage collection would reclaim
```

Retention is opt-in — set `[registry.retention] enabled = true` in `/etc/cairn/registry.toml`
before `prune` will actually delete anything. Once you're comfortable with what it selects,
install the periodic maintenance timer (enabled but not started, so the first pass is still
run and watched by hand):

```bash
sudo cairn-registry setup-timer --dry-run
sudo cairn-registry setup-timer
```

To confirm it's actually firing on schedule, rather than trusting that it is: `systemctl
list-timers --all | grep cairn` and `journalctl -u cairn-registry-maintenance.service --since
-1d` — see [Build Automation](../builder/automation.md#verify-its-actually-running) for the
same pattern applied to every cairn timer.

## Next: verified against a real deployment

*This page is written ahead of a live run — check back, or see
[`docs/requirements/08-registry.md`](https://github.com/Datahenge/cairn/blob/main/docs/requirements/08-registry.md)
in the meantime for the full command and configuration reference.*
