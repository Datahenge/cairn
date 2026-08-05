# Get Started

Installs cairn and gets it onto a machine — whether that machine will go on to **host a
local registry**, **build** images, or **adopt and run** an existing deployment. The three
roles diverge right after this page; see [Next steps](#next-steps) at the bottom, and read
it in order — Registry first. `cairn-build push`, `assign-tag`, and every build automation
timer assume the registry decision is already made, and the target role has nothing to poll
without it. Deciding it upfront, even if the answer is "a client already runs one," avoids
stopping mid-Builder-walkthrough to go make that decision.

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

- **`cairn-registry`** — the registry-host role, needed only if you choose to self-host:
  `status`, `start`, `stop`, `restart`, `images`, `prune`, `gc`, `doctor`, `setup`,
  `setup-timer`.
- **`cairn-build`** — the builder role: `build`, `push`, `images`, `prune`, `assign-tag`,
  `retire`, `vendor`, `doctor`, `setup`, `setup-timer`.
- **`cairn-adopt`** — the target role: `examine`, `reconcile`, `systemd-units`, `doctor`,
  `setup`, `setup-timer`.

There is no unified `cairn` command. Which one(s) you need depends on what this machine does,
not what's installed — the same package carries all three.

## Next steps

1. **[Choosing a container registry](../registry/choosing-a-registry.md)** — decide where
   images will live before going further; see the tradeoffs there. If that's a self-hosted
   registry, provision it with **[Self-Hosted Registry](../registry/index.md)**, starting with
   `cairn-registry doctor`. If a client or cloud provider already operates the registry you'll
   push to, there's nothing to provision — just note its address for the [manifest's
   `[cairn.registry]` table](../reference/manifest.md#cairnregistry) — but make that call now
   rather than after a build is already sitting local-only.
2. **[Builder](../builder/index.md)** — building and pushing images. Starts with
   `cairn-build doctor`.
3. **[Target](../target/index.md)** — adopting and running an existing deployment. Starts
   with `cairn-adopt doctor`.
