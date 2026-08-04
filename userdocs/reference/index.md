# Reference

Command surface and file-format reference material will land here.

Until it's written, run `cairn-build --help` / `cairn-adopt --help` / `cairn-registry --help`
(or `<command> <subcommand> --help`) for the current command surface — it stays authoritative
for the CLI's exact flags and behavior.

## Contributing

### For development

Contributing to cairn itself, or re-syncing the vendored upstream, needs a checkout:

```
git clone https://github.com/Datahenge/cairn.git
cd cairn
python3 -m venv .venv
.venv/bin/pip install --editable '.[dev]'
```

The `dev` extra adds `ventwig` (vendoring), `ruff`, and `pytest` — none of which a normal
install needs.

### Vendored upstream

`src/cairn/vendored/frappe_docker/` is a pinned, read-only copy of upstream, vendored as
plain committed files via [`ventwig`](https://github.com/brian-pond/ventwig) and never
edited by hand. It lives inside the `cairn` package itself, so it's part of every install
— pip or checkout alike. It's pinned to upstream release tag **`v3.2.1`**.

```
cairn-build vendor status   # verify the vendored tree is clean / unmodified
cairn-build vendor sync      # re-materialize from the pinned ref (a checkout only)
```

To upgrade upstream: bump `ref` in `pyproject.toml`, `cairn-build vendor sync`, review the diff,
test-build, then commit — including the regenerated `frappe_docker.pin.toml` alongside it.
