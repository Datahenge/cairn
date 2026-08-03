# Get Started

This walks through installing cairn's **builder** role on a fresh machine — a client VPS, or
any box that will build and push images. The **target** role (the machine that actually runs
ERPNext) has its own, separate Get Started guide, not yet written.

## Prerequisites

cairn needs:

- **Docker Engine v23+** with `buildx`, or **podman v4+** — auto-detected, Docker preferred
  when both are present.
- **`git`** — every manifest ref is resolved to a commit at build time.

Confirm both are present before installing:

```bash
docker --version
git --version
```

## Install

cairn is distributed as **`datahenge-cairn`** on PyPI. On a machine anything else depends on —
a client's builder, not a laptop you alone operate — install system-wide rather than into a
personal account, so the install doesn't disappear if your individual login ever does:

```bash
# if you don't already have it
sudo apt install pipx

sudo pipx install --global datahenge-cairn
```

This single install gives you **two** commands, not one:

- **`cairn-build`** — the builder role: `build`, `push`, `images`, `prune`, `new-tag`,
  `retag`, `retire`, `vendor`, `doctor`, `setup`.
- **`cairn-adopt`** — the target role: `examine`, `reconcile`, `systemd-units`, `doctor`,
  `setup`.

There is no unified `cairn` command. Which one you need depends on what this machine does, not
what's installed — the same package carries both.

## Verify with `doctor`

Each CLI has its own `doctor`, checking only what its own role needs:

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
