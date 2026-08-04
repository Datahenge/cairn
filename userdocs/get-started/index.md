# Get Started

Installs cairn and gets it onto a machine — whether that machine will go on to **build**
images, **adopt and run** an existing deployment, or **host a local registry**. The three
roles diverge right after this page; see [Next steps](#next-steps) at the bottom.

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
a client's builder or target, not a laptop you alone operate — install system-wide rather than
into a personal account, so the install doesn't disappear if your individual login ever does:

```bash
# if you don't already have it
sudo apt install pipx

sudo pipx install --global datahenge-cairn
```

This single install gives you **three** commands, not one:

- **`cairn-build`** — the builder role: `build`, `push`, `images`, `prune`, `assign-tag`,
  `retire`, `vendor`, `doctor`, `setup`, `setup-timer`.
- **`cairn-adopt`** — the target role: `examine`, `reconcile`, `systemd-units`, `doctor`,
  `setup`, `setup-timer`.
- **`cairn-registry`** — the registry-host role, needed only if you choose to self-host:
  `status`, `start`, `stop`, `restart`, `images`, `prune`, `gc`, `doctor`, `setup`,
  `setup-timer`.

There is no unified `cairn` command. Which one(s) you need depends on what this machine does,
not what's installed — the same package carries all three.

## Next steps

- **[Builder](../builder/index.md)** — building and pushing images. Starts with
  `cairn-build doctor`.
- **Target** — adopting and running an existing deployment. Not yet written.
- **[Registry](../registry/index.md)** — provisioning and operating a self-hosted registry.
  Starts with `cairn-registry doctor`. Only needed if you chose that option — see
  [About container registries](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md).
