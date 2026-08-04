# Builder

Building and pushing images with `cairn-build`. Assumes cairn is already installed — see
[Get Started](../get-started/index.md) if it isn't yet.

## Verify with `doctor`

```bash
cairn-build doctor
```

A machine with nothing configured yet is expected to show a couple of warnings, not failures —
for example:

```
WARN config          No manifest given. Pass --manifest <path>, or set $CAIRN_MANIFEST.
OK   build engine    docker v29.6.2
OK   docker buildx   github.com/docker/buildx v0.35.0 ...
OK   git             v2.47.3
OK   vendored tree   matches its recorded pin
OK   vendor .git     no nested .git
OK   build inputs    Containerfile complete
WARN shared config   /etc/cairn does not exist yet — run this CLI's `setup` subcommand, or create it by hand
OK   known manifests none found under /srv/cairn

All 9 checks passed (2 warning(s)).
```

Both warnings above are expected at this point: there's no manifest yet (next section), and
`/etc/cairn` is only created by `cairn-build setup`, which comes after you've confirmed a
manifest builds correctly by hand.

## Provision the manifest directory

Once `doctor` shows the two expected warnings above, run `setup` as root, naming your client:

```bash
sudo cairn-build setup --client acmecorp
```

This does two things in one privileged run:

- **`/etc/cairn`** — created and shared with the `cairn-admins` group (mode `2775`), the same
  group your own account joined in [Get Started](../get-started/index.md).
- **`/srv/cairn/acmecorp/`** — provisioned, with a starter `cairn.toml` scaffolded into it,
  since none existed yet.

Example output:

```
cairn-build setup
workdir /home/brian

[preflight]
  [ok] root                   running as root
  [ok] docker                 Docker version 29.6.2, build dfc4efb
  [ok] docker compose         Docker Compose version v5.3.1
  [ok] free disk              199 GB free on /var/lib/docker
  [ok] available memory       63.8 GB available
  [ok] docker buildx          github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782
  [ok] git                    git version 2.47.3

[admin-group]
    group 'cairn-admins' already exists (gid 1001)

[manifest]
    write /srv/cairn/acmecorp/cairn.toml (starter manifest)

--- summary ---
  did: /etc/cairn shared with group 'cairn-admins' (mode 2775)
  did: /srv/cairn/acmecorp provisioned
  did: scaffolded a starter manifest at /srv/cairn/acmecorp/cairn.toml
  skipped: group 'cairn-admins' (already exists)
```

`setup` is idempotent — re-running it later won't overwrite an edited `cairn.toml`, and steps
that already exist (like the group above) are reported as skipped, not redone.

## Next: edit the manifest, and run your first build

Edit the scaffolded `cairn.toml` for your deployment — see [the manifest
reference](../reference/manifest.md) for every field. Running the first build itself is
*coming once verified end-to-end.*
