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

All 8 checks passed (2 warning(s)).
```

Both warnings above are expected at this point: there's no manifest yet (next section), and
`/etc/cairn` is only created by `cairn-build setup`, which comes after you've confirmed a
manifest builds correctly by hand.

## Next: write a manifest, and run your first build

*Coming once verified end-to-end — check back, or see the
[README's configuration section](https://github.com/Datahenge/cairn/blob/main/README.md#configuration)
in the meantime for the manifest schema.*
