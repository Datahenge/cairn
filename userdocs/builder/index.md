# Builder

Building and pushing images with `cairn-build`.

- Assumes cairn is already installed — see [Get Started](../get-started/index.md) if it
  isn't yet.
- Assumes the registry decision is already made. `cairn-build push`, `assign-tag`, and every
  build automation timer all assume it — and the target role has nothing to poll without it.
    - **Self-hosting?** Provision it first — see [Registry](../registry/index.md).
    - **Using a client- or cloud-hosted registry instead?** There's nothing to provision.
      Just note its address in the manifest's [`[cairn.registry]`
      table](../reference/manifest.md#cairnregistry) and continue below.

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
OK   free disk       199 GB free on /var/lib/docker
OK   available memory 63.8 GB available
OK   git             v2.47.3
OK   build inputs    Containerfile complete
WARN shared config   /etc/cairn does not exist yet — run this CLI's `setup` subcommand, or create it by hand
OK   known manifests none found under /srv/cairn

All 9 checks passed (2 warning(s)).
```

Both warnings above are expected at this point: there's no manifest yet (next section), and
`/etc/cairn` is only created by `cairn-build setup`, which comes after you've confirmed a
manifest builds correctly by hand.

## Provision the manifest directory

Once `doctor` shows the two expected warnings above, run `setup` as root, naming your client
and the environment this manifest is for:

```bash
sudo cairn-build setup --client acmecorp --environment production
```

A manifest declares **at most one** environment (see [the manifest
reference](../reference/manifest.md#environments)) — for `test`/`staging`/`production`, run
`setup` again with each `--environment`, once per environment, and you'll get one
distinctly-named manifest per environment in the same client directory.

This does two things in one privileged run:

- **`/etc/cairn`** — created and shared with the `cairn-admins` group (mode `2775`), the same
  group your own account joined in [Get Started](../get-started/index.md).
- **`/srv/cairn/acmecorp/`** — provisioned, with a starter `cairn_production.toml` scaffolded
  into it, since none existed yet.

Example output:

```
cairn-build setup
workdir /home/brian

[preflight]
  [ok] root                   running as root
  [ok] build engine           docker v29.6.2
  [ok] docker buildx          github.com/docker/buildx v0.35.0 a319e5b15052cf6557ceb666eb8ff6e32380b782
  [ok] free disk              199 GB free on /var/lib/docker
  [ok] available memory       63.8 GB available
  [ok] git                    git version 2.47.3

[admin-group]
    group 'cairn-admins' already exists (gid 1001)

[manifest]
    write /srv/cairn/acmecorp/cairn_production.toml (starter manifest)

--- summary ---
  did: /etc/cairn shared with group 'cairn-admins' (mode 2775)
  did: /srv/cairn/acmecorp provisioned
  did: scaffolded a starter manifest at /srv/cairn/acmecorp/cairn_production.toml
  skipped: group 'cairn-admins' (already exists)
```

`setup` is idempotent — re-running it later won't overwrite an edited manifest, and steps
that already exist (like the group above) are reported as skipped, not redone.

## Edit the manifest

Edit the scaffolded `cairn_production.toml` for your deployment — see [the manifest
reference](../reference/manifest.md) for every field.

## Run the build

Preview first — nothing is built, pushed, or touched:

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn_production.toml --dry-run
```

This resolves every ref (contacting each app's remote), computes the tags, and prints the
exact command a real build would run. Once it looks right, drop `--dry-run`:

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn_production.toml
```

Progress prints as it works — resolving refs, building, verifying the image landed,
naming the reusable build-cache layer — and, at a terminal, the whole run is also saved to
a transcript file, since nothing else is keeping it. It finishes with a per-phase timing
report, worth a glance every time: it's the fastest way to notice a build that's started
thrashing the layer cache instead of reusing it.

```
Timing
  checks + ref resolution  4.2s
  image build              4m 52s
  verify image              0.6s
  name build cache          0.3s
  started  2026-08-04 15:03:09 -0700
  finished 2026-08-04 15:08:24 -0700
  total    5m 15s
```

As a real-world data point: a clean build of `erpnext-v16` (Frappe + ERPNext only, no
custom apps) took **5 minutes 15 seconds** end-to-end against a typical VPS. Expect
something in that range for a similar image; a much longer first run is usually the layer
cache warming up rather than anything wrong.

## Where the image goes

By default a build stays **local** — tagged `cairn/<image_name>` in the build machine's own
Docker/Podman image store, nowhere else. It only leaves the machine once you configure a
registry (the manifest's `[cairn.registry]`, or `/etc/cairn/builder.toml`) and explicitly
push — building never pushes on its own unless you pass `--push`. See [Machine-local build
config](../reference/builder-config.md#resolution-order) for how the image base is chosen.

That local image store lives on disk somewhere cairn deliberately doesn't assume —
`cairn-build doctor`/`setup` already name it, as part of their disk-space check:

```
OK   free disk    199 GB free on /var/lib/docker
```

The path after "free on" is the engine's own data root, read with `docker info --format
'{{.DockerRootDir}}'` (or `podman info --format '{{.Store.GraphRoot}}'`) rather than
assumed — a separate mount for it is common on a build machine, and that's exactly the
case a hardcoded `/var/lib/docker` would get wrong. Whatever a system admin needs to
monitor for disk headroom, this is the path.

To know for certain what a build machine is actually holding, ask cairn rather than reading
a raw `docker images` — cairn groups by what was actually built, distinguishing a current
build from one it has since superseded:

```bash
cairn-build images --local
```

```
cairn/erpnext-v16:v16-d47f139c6ffe  (input hash d47f139c6ffe)
  frappe       v16.25.0         9a8daf34
  erpnext      v16.26.1         fd00cebb
  built from recipe a1c2e3f4
    a1b2c3d4e5f6    1.79 GB       2m  cairn/erpnext-v16:v16-d47f139c6ffe, cairn/erpnext-v16:latest

1 image(s) built by cairn across 1 input hash(es); 0 superseded, holding 0 B.
```

Leads with the tag you'd actually recognize, not the input hash — the hash is still there,
parenthetically, and is usually visible again in the tag's own suffix
(`<series>-<hash>`). `src/cairn/recipe/` is cairn's own owned Docker build
recipe — its git commit is part of what produced this image, since it supplies the
Containerfile itself, so two images from an identical `cairn.toml` can still differ if the
recipe changed between builds. Every image cairn builds carries its full provenance as OCI
labels — resolved commits, the effective build args, that same recipe commit — so `docker
inspect` (or the listing above) can always answer "what exactly is this" later, long after
the terminal output has scrolled away.

## Next steps

- **Push it**, if this deployment uses a registry: `cairn-build push`. With no registry
  configured there's nothing to push to yet — see [the manifest's
  `[cairn.registry]`](../reference/manifest.md#cairnregistry) or [`builder.toml`'s
  registry keys](../reference/builder-config.md).
- **Point an environment at it.** An *environment* (`production`, `staging`, …) is just a
  named, moving registry tag that a target machine watches — this manifest's own declared
  `environment` (see [Environments](../reference/manifest.md#environments), which has a
  full worked example of what this buys you: build once, let each environment's own
  manifest prove a match, roll back by repointing). `cairn-build assign-tag --manifest
  /srv/cairn/acmecorp/cairn_production.toml` resolves this manifest's refs, checks the
  registry, and — only if it finds a match — points `production` at it, creating the
  pointer the first time and moving it every time after. Nothing is rebuilt or pulled
  either way; moving `production` asks for confirmation first, whether that's the first
  time it's pointed at anything or the fiftieth. No `--latest`/`--previous`/`--from` — there
  is only ever one correct answer: what this manifest's own refs currently resolve to.
- **Adopt it.** `cairn-adopt` is the target-side binary — it polls the environment's tag
  and converges on its own next poll once the pointer moves; nothing pushes into the
  target. See **[Target](../target/index.md)** for the target-side walkthrough.
- **Automate it.** Once a manual build, push, and pointer move all work, `cairn-build
  setup-timer` installs a systemd timer that repeats the same sequence on a schedule
  unattended — see [Build Automation](automation.md).
