# cairn

**Frappe + ERPNext + your custom apps, on one VPS, running the commit you last pushed.**

cairn builds a Docker image from your app repositories, publishes it to a container
registry, and lets your server notice the new image and switch to it on its own.

There is no CI service to configure, no webhook to receive, and no build minutes to pay
for. Two small systemd timers do the polling, one on the machine that builds and one on
the machine that serves. Both dial outward: your VPS never opens a port, never holds a
webhook listener, and never hands a deploy key to GitHub.

> *A cairn is a trail marker of stacked stones. Every deploy leaves one behind: the git
> ref, the commits it resolved to, the image tag, the digest. You can always walk back.*

## How it works

You push a commit. The builder's timer resolves your app refs to commits, notices the
combination is new, builds an image, pushes it, and moves the environment's tag. The
target's timer notices the tag moved, pulls the image, restarts the stack, runs
`bench migrate`, and checks that the site came back. Neither machine accepts a connection
to do any of it.

Every image records the commits it was built from, the build arguments used, and the
version of the build recipe that produced it. The tag is derived from those resolved
inputs rather than typed by hand, so the same inputs produce the same tag and different
inputs cannot collide. Rolling back is moving the tag to an earlier image and letting the
server converge.

cairn's build recipe and compose configuration were bootstrapped from
[`frappe/frappe_docker`](https://github.com/frappe/frappe_docker) and stay close to it.
frappe_docker gives you the parts to build a custom image; cairn adds the lifecycle around
them. If cairn went away, you would be left holding a normal compose deployment and a
registry full of normal images.

## What it does not touch

cairn moves code, not data. The only database write it ever makes is the `bench migrate`
that follows a deploy. It does not create sites, it is not a backup tool, and it is not
multi-server orchestration. One VPS, one site.

## Three roles, one package

| | Command | Does |
| --- | --- | --- |
| **Builder** | `cairn-build` | Builds the image, pushes it, moves the environment tag |
| **Target** | `cairn-adopt` | Polls for the tag, pulls, converges the running stack |
| **Registry** | `cairn-registry` | Hosts images, if you self-host. Optional: bring your own registry instead |

```bash
pipx install datahenge-cairn
```

installs all three. Each machine uses whichever role applies to it.

## Documentation

**[datahenge.github.io/cairn](https://datahenge.github.io/cairn/)**

Start with [Why cairn](https://datahenge.github.io/cairn/why-cairn/) to decide whether you
want it, then [Get Started](https://datahenge.github.io/cairn/get-started/) to install.
