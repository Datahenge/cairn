# Reference

File-format reference material:

- **[cairn.toml (manifest)](manifest.md)** — the image declaration: Frappe source, apps,
  build knobs, environments, registry.
- **[builder.toml (build config)](builder-config.md)** — machine-local build settings,
  the private-`github.com`-app token, and shared `/etc/cairn` provisioning.
- **[Target descriptor](target-descriptor.md)** — `/etc/cairn/adopt.toml`, what a target
  host runs.

Command surface reference will land here later. Until it's written, run
`cairn-build --help` / `cairn-adopt --help` / `cairn-registry --help` (or `<command>
<subcommand> --help`) for the current command surface — it stays authoritative for the
CLI's exact flags and behavior.

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
