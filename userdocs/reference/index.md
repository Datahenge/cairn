# Reference

## Command surface

One page per binary — every command, every flag:

- **[`cairn-build`](cairn-build.md)** — building images and moving environment pointers.
- **[`cairn-adopt`](cairn-adopt.md)** — converging and operating a target host.
- **[`cairn-registry`](../registry/cli.md)** — provisioning and operating a self-hosted
  registry. (Filed under Registry, alongside the narrative that explains it.)

These describe the same surface as `--help`, with the context a help string has no room for.
Where the two ever disagree, **`--help` is authoritative** — it ships with the version you
actually have installed, and these pages do not.

## File formats

- **[cairn.toml (manifest)](manifest.md)** — the image declaration: Frappe source, apps,
  build knobs, environments, registry.
- **[builder.toml (build config)](builder-config.md)** — machine-local build settings,
  the private-`github.com`-app token, and shared `/etc/cairn` provisioning.
- **[Target descriptor](target-descriptor.md)** — `/etc/cairn/adopt.toml`, what a target
  host runs.

## Contributing

### For development

Contributing to cairn itself needs a checkout:

```
git clone https://github.com/Datahenge/cairn.git
cd cairn
python3 -m venv .venv
.venv/bin/pip install --editable '.[dev]'
```

The `dev` extra adds `ruff` and `pytest` — neither of which a normal install needs.

### Docker build recipe

`src/cairn/recipe/` is cairn's own Docker build recipe (the `Containerfile`
and compose YAML) — ordinary source, owned and freely edited directly, not vendored or
pinned from upstream. It lives inside the `cairn` package itself, so it's part of every
install — pip or checkout alike. There's no sync command or pin file: consulting
[`frappe/frappe_docker`](https://github.com/frappe/frappe_docker) for ideas is an
informal, manual `git clone`/diff, done by hand whenever it's convenient.
