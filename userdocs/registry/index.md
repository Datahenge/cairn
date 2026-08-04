# Registry

Provisioning and operating a self-hosted local registry with `cairn-registry`. New to
container registries? Read [What is this, exactly?](#what-is-this-exactly) below. Already
know the concept and just want the commands? Skip to [Provision it](#provision-it), or go
straight to the full **[Registry CLI](cli.md)** reference.

Only needed if you're self-hosting. If you're using a client-owned cloud registry or GHCR
instead, there's nothing to provision here:

- note the address in the manifest's [`[cairn.registry]`
  table](../reference/manifest.md#cairnregistry)
- see [Choosing a container registry](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md)
  for that decision, and why it isn't neutral for client work
- then go straight to [Builder](../builder/index.md)

Assumes cairn is already installed — see [Get Started](../get-started/index.md) if it isn't
yet.

## What is this, exactly?

A **container registry** is a server that stores container images and hands them out on
request — the same idea as Docker Hub, just running somewhere you control instead of a public
service.

A few things worth knowing before you provision one:

- **It's not cairn's own code.** The actual server is the official, open-source **Docker
  Distribution** registry (`docker.io/library/registry:2`) — the same engine that runs Docker
  Hub itself, written and maintained by Docker/the CNCF community. `cairn-registry` doesn't
  reimplement any of that; it only provisions and operates it:
    - generates a TLS certificate and trusts it
    - writes the container's configuration
    - starts and stops it
    - cleans up old images on a schedule
- **It runs on its own, all the time.** `setup` starts it once, as a standalone Docker
  container, and it stays up in the background from then on — it isn't launched per-build or
  per-deploy, and nothing else needs to be running for it to keep serving requests.
- **It's completely independent of Builder and Target.** It reads no manifest and no `[cairn]
  environment` — it has no idea any particular build, deployment, or client project exists.
  Every decision it makes comes from its own config (`/etc/cairn/registry.toml`) and its own
  API. All it knows is: here are some images, here are their tags, hand them out on request.

Day to day, it does three things:

- **Stores** every image `cairn-build push` sends it, identified by a content-hash tag.
- **Tags** — lets you point a moving name (an environment, like `production`) at one specific
  stored image, and move that pointer later without re-uploading anything.
- **Serves** images back out over HTTPS, whenever Builder pushes or a Target machine pulls.

## Provision it

```bash
sudo cairn-registry setup --dry-run   # review every action first
sudo cairn-registry setup
```

This:

- generates a self-signed TLS certificate and trusts it system-wide and with Docker
- creates a starter `/etc/cairn/registry.toml` the first time none exists, so every
  configurable setting is visible and editable without hunting for documentation — see
  [Registry CLI: configuration](cli.md#configuration)
- starts the registry as a `docker compose` project
- finishes by running `cairn-registry doctor` automatically, so a real run ends with a clear
  pass/fail, not just a log of steps taken

Expected once provisioned:

```
OK   reachable       127.0.0.1:5000 — 0 repositor(y/ies)
OK   certificate     /etc/cairn/registry.crt valid
OK   disk headroom   82 GB free at /opt/cairn-registry/data

All 3 checks passed.
```

### Changing the port, or anything else in registry.toml

1. Edit `/etc/cairn/registry.toml` — every key is documented inline, right in the file.
2. Re-apply with:
   ```bash
   sudo cairn-registry setup --force
   ```

Two things worth knowing:

- **`--force` is required, not optional.** The compose file `setup` already wrote no longer
  matches what your edit now produces, and cairn never silently overwrites a file it can't
  prove is unchanged. The previous compose file is kept alongside as a backup.
- **`registry.toml` itself is never touched by `setup`, `--force` included.** Once that file
  exists, it's yours to edit freely — cairn only ever writes it once, as a starting point.

## Keep disk use bounded

Every build's content-hash tag accumulates in the registry forever unless something prunes
it. This is safe to run unattended:

- cairn never deletes a digest that still carries a moving series tag (like `v16`)
- cairn never deletes a digest that still carries a declared environment tag (like
  `production`)

```bash
cairn-registry prune --dry-run   # report what retention would delete
cairn-registry gc --dry-run      # report what garbage collection would reclaim
```

Retention is opt-in — set `[registry.retention] enabled = true` in `/etc/cairn/registry.toml`
before `prune` will actually delete anything. Once you're comfortable with what it selects,
install the periodic maintenance timer:

```bash
sudo cairn-registry setup-timer --dry-run
sudo cairn-registry setup-timer
```

It installs enabled but not started, so the first pass is still one you run and watch by
hand. To confirm it's actually firing on schedule later, rather than trusting that it is:

```bash
systemctl list-timers --all | grep cairn
journalctl -u cairn-registry-maintenance.service --since -1d
```

See [Build Automation](../builder/automation.md#verify-its-actually-running) for the same
verification pattern applied to every cairn timer.

## Command reference

Every `cairn-registry` command, with its flags and examples, lives on its own page:
**[Registry CLI](cli.md)**.

## Next steps

- **[Builder](../builder/index.md)** — now that the registry decision is made, build and push
  images against it.

*This page is written ahead of a live run past `--dry-run` — check back, or see
[`docs/requirements/08-registry.md`](https://github.com/Datahenge/cairn/blob/main/docs/requirements/08-registry.md)
in the meantime for the full requirements reference.*
