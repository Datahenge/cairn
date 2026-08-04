# Reference

Command surface and file-format reference material will land here.

Until it's written, run `cairn-build --help` / `cairn-adopt --help` (or `<command>
<subcommand> --help`) for the current command surface — it stays authoritative for the
CLI's exact flags and behavior.

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
