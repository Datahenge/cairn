# Registry CLI

Every `cairn-registry` command. For what the tool actually does and why you'd want it, see
[Registry](index.md) — this page is just the command surface.

## setup

```bash
sudo cairn-registry setup --dry-run
sudo cairn-registry setup
```

Provisions this machine as a registry host: certificate, config file, compose project,
running container. Idempotent — safe to re-run.

Flags:

- `--dry-run` — print every action, change nothing.
- `--force` — replace files cairn itself generates (the certificate, the compose file) when
  they no longer match what the current config would produce. The old file is kept alongside
  as a backup. Never applies to `registry.toml` itself — see [Registry: changing the
  port](index.md#changing-the-port-or-anything-else-in-registrytoml).
- `--only <stage>` — run one stage only: `preflight`, `admin-group`, or `registry`.
- `--private-ip <ip>` — also cover this address in the certificate, for when the registry and
  its clients later split onto separate machines.
- `--skip-disk-free` — proceed even if free disk space is under the minimum.
- `--admin-group <name>` — which group `/etc/cairn` is shared with (default `cairn-admins`).
- `--no-admin-group` — skip sharing `/etc/cairn` with a group; leave it exactly as found.

A real (non-`--dry-run`) run that actually brings the registry container up — the full run,
or `--only registry` on its own — finishes by running the same checks as `doctor` and exits
with its code. `--dry-run` and `--only preflight`/`--only admin-group` skip this, since
neither leaves anything running to check yet.

### Storage
Images served by the registry are stored in `/var/lib/cairn-registry` by default.

### Configuration

`setup` scaffolds `/etc/cairn/registry.toml` the first time none exists, fully commented:

```toml
[registry]
port = 5000
bind_address = "127.0.0.1"
data_dir = "/var/lib/cairn-registry"

[registry.retention]
enabled = false
keep_last = 10
max_age_days = 90

[registry.gc]
schedule = "weekly"
```

- `port` / `bind_address` — where the registry listens.
- `data_dir` — where image blobs are stored on disk. An operator-chosen path, not an
  anonymous Docker volume, so you can point it at a specific disk.
- `[registry.retention]` — see [prune](#prune) below.
- `[registry.gc] schedule` — the cadence `setup-timer` installs (a systemd `OnCalendar=`
  value; `"weekly"`/`"daily"` are valid as-is).

The file is absent-safe: with no file at all, `cairn-registry setup` still runs against these
same defaults. Once the file exists, it's entirely yours — edit any value, then re-apply with
`sudo cairn-registry setup --force`.

## setup-timer

```bash
sudo cairn-registry setup-timer --dry-run
sudo cairn-registry setup-timer
```

Installs a systemd timer that runs `prune` then `gc` on the schedule set by `[registry.gc]
schedule`. Installed **enabled but not started** — run the first pass by hand and watch it,
then:

```bash
sudo systemctl start cairn-registry-maintenance.timer
```

## status / start / stop / restart

Thin wrappers over `docker compose`, addressing the exact project `setup` created:

```bash
cairn-registry status    # docker compose ps
cairn-registry start     # docker compose up -d
cairn-registry stop      # docker compose stop — data is untouched
cairn-registry restart   # docker compose restart
```

## images

```bash
cairn-registry images
cairn-registry images --host ghcr.io --namespace acmecorp --image erpnext-v16
cairn-registry images --namespace acmecorp --image 'erpnext-*'
cairn-registry images --json
```

Reports what cairn built, read from a registry's own API — never pulls an image to find out.
This is the registry-side counterpart to `cairn-build images`, which only ever answers for
the build machine itself; a registry (this machine's own, or a client's remote one) is always
this command's job, not that one's.

Flags:

- `--host <host[:port]>` — which registry to query. Default: this machine's own (from
  `registry.toml`). Any other value queries that registry instead, local or remote.
- `--namespace <name>` — only repositories directly under this namespace (typically one
  client).
- `--image <name>` — only this image name; accepts a glob, e.g. `'erpnext-*'`.
- `--json` — machine-readable output.

**An exact `--namespace` and `--image` together (no glob) read that one repository directly**,
the same authenticated way `cairn-build push`/`assign-tag` do — this is what reaches a
registry that requires a login, GHCR included, after `docker login`/`podman login`. Any other
combination — no `--image`, or `--image` is a glob — enumerates the registry's whole catalog
first, then filters. Catalog enumeration only works unauthenticated, which cairn's own
self-hosted registry is by design; most third-party registries refuse it, so a whole-registry
or glob query against one of those will fail plainly rather than pretend to a partial answer.

Output is grouped by input hash and digest, not one row per tag — a deterministic content-hash
tag, `latest`, and any moving tag you assigned (an environment pointer, or anything else) can
all name the same build, so every name for it shows up together rather than scattered across
rows you'd otherwise have to cross-reference by eye. The repository line prints the **full
reference** — registry host included — not just the bare name: `image = "..."` in a target
descriptor needs the host too, since cairn refuses to assume one, and this is meant to be
copy-pasted straight in:

```
Registry ghcr.io

Repository ghcr.io/acmecorp/erpnext-v16
v16-a1b2c3d4e5f6  (input hash a1b2c3d4e5f6)
  frappe       v16.25.0         9a8daf34
  erpnext      v16.26.1         fd00cebb
    a1b2c3d4e5f6  1.79 GB       2d  latest, production, v16-a1b2c3d4e5f6

1 image(s) built by cairn in ghcr.io/acmecorp/erpnext-v16 across 1 input hash(es).
Sizes are the download size from the registry, not unpacked size on disk.
```

This is usually the fastest way to find the exact tag to put into a target's
[descriptor](../reference/target-descriptor.md#fields) — whatever's listed alongside the build
you want *is* the tag to watch.

## doctor

```bash
cairn-registry doctor
```

```
OK   reachable       127.0.0.1:5000 — 0 repositor(y/ies)
OK   certificate     /etc/cairn/registry.crt valid
OK   disk headroom   82 GB free at /var/lib/cairn-registry

All 3 checks passed.
```

Three checks, each read-only:

- **reachable** — the registry answers over HTTPS.
- **certificate** — present and not expired.
- **disk headroom** — free space under `data_dir`.

`setup` runs this automatically at the end of a real run — see [setup](#setup) above.

## prune

```bash
cairn-registry prune --dry-run   # report only
cairn-registry prune --yes       # delete without prompting
```

For every repository, reports every digest's disposition — kept or deleted, and why — before
deleting anything. Deletes nothing unless `[registry.retention] enabled = true`; with it
`false` (the default), `prune` still runs and still reports, just never deletes.

Rules, in order:

1. Only digests whose every tag matches cairn's own content-hash shape are even eligible. A
   digest still carrying a moving series tag (`v16`) or a declared environment tag
   (`production`) is categorically protected — never a candidate for deletion.
2. The newest `keep_last` eligible digests are kept regardless of age — the rollback floor.
3. Of what's left, only digests older than `max_age_days` are deleted.

## gc

```bash
cairn-registry gc --dry-run   # report the read-only window, then stop
cairn-registry gc --yes       # actually reclaim storage
```

Reclaims disk space for digests `prune` already deleted — `prune` marks things eligible, `gc`
is the step that actually frees the bytes.

- Briefly puts the registry into **read-only** maintenance mode. Pulls (including a Target
  machine's own polling) continue throughout; pushes are refused until it finishes.
- Requires `--yes` or `--dry-run` — it never runs with neither.
