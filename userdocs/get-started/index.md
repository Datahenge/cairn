# Get Started

Installs cairn and gets it onto a machine — whether that machine will go on to **build**
images or **adopt and run** an existing deployment. The two roles diverge right after this
page; see [Next steps](#next-steps) at the bottom.

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

This single install gives you **two** commands, not one:

- **`cairn-build`** — the builder role: `build`, `push`, `images`, `prune`, `new-tag`,
  `retag`, `retire`, `vendor`, `doctor`, `setup`.
- **`cairn-adopt`** — the target role: `examine`, `reconcile`, `systemd-units`, `doctor`,
  `setup`.

There is no unified `cairn` command. Which one you need depends on what this machine does, not
what's installed — the same package carries both.

## Next steps

- **[Builder](../builder/index.md)** — building and pushing images. Starts with
  `cairn-build doctor`.
- **Target** — adopting and running an existing deployment. Not yet written.
