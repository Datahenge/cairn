# GitHub Container Registry: Ownership & Cost

Who ends up owning a pushed image, who can see it, and what it actually costs at ERPNext image
sizes.

*GitHub Container Registry (GHCR) guide: [Setup](ghcr-setup.md) · **Ownership & Cost** ·
[Tags & Troubleshooting](ghcr-tags-and-troubleshooting.md)*

## Who owns the images after deployment

The GitHub account that pushed them — in your case the `datahenge` organization. Pulling an
image to a VPS does not transfer anything; the VPS holds a *copy*, and the registry keeps the
original.

The practical consequences are worth stating because they are the kind of thing discovered at
a bad moment:

- **If the package is deleted, targets can no longer pull it.** Already-running containers
  keep running — they use the local copy — but a fresh host, or one whose local image has been
  pruned, cannot deploy. cairn's rollback model depends on old images still being in the
  registry.
- **If the organization is deleted or renamed, every image path changes.** The registry path
  contains the owner name.
- **If you pushed to your own namespace, your client does not own their image.** An image
  sitting in *your* organization is a dependency they have on you: end the relationship badly
  and they cannot deploy or roll back software they own. This is a rule, not a caveat — see
  [Choosing a container
  registry](choosing-a-registry.md#1-the-image-belongs-in-the-account-that-owns-the-source).
  Push to an account **they** own: set `[cairn.registry]` in their deployment's `cairn.toml`
  and nothing else about cairn changes.
- **Anyone with `read:packages` on a private package can pull the whole image**, which
  contains your application code. Treat pull tokens as code access, because that is what they
  are.

## Visibility: private by default

A newly pushed package is **private**. Nobody but you (and accounts you grant) can pull it.

You can change a package to **public** in its settings, and then *anyone on the internet* can
pull it anonymously, with no token. For a proprietary ERPNext build that is almost certainly
wrong — the image contains your custom app source.

Two facts about public that are easy to miss:

- Public packages are **free**, in both storage and bandwidth. Private ones are not. See
  [below](#what-it-costs-read-this-before-you-push-several-images).
- A public image version that has been downloaded more than a few thousand times **cannot be
  deleted at all.** See [Tags & Troubleshooting: deleting
  images](ghcr-tags-and-troubleshooting.md#deleting-images-the-genuinely-sharp-edge).

## What it costs — read this before you push several images

GHCR is free for public packages. For **private** packages, storage and outbound data transfer
count against your plan's GitHub Packages allowance, and you are billed per gigabyte beyond
it.

**This matters more for ERPNext than for most projects, because the images are large.** A
custom Frappe + ERPNext image is roughly **2.75 GB**. The allowances included with the
personal and small-team plans are on the order of a couple of gigabytes of storage and ten
gigabytes of monthly transfer — meaning **one single image can exceed your entire included
storage**, and one deployment pull can consume a meaningful share of the monthly transfer.

Do the arithmetic for your own situation, with current prices from GitHub's billing docs, on
these three numbers:

1. **Image size** × **how many versions you keep** = storage. Rollback headroom is not free;
   keeping five versions of a 2.75 GB image is about 14 GB.
2. **Image size** × **deploys per month** = outbound transfer. Every reconcile pass that
   actually converges pulls an image.
3. Transfer *into* GitHub Actions is free. Transfer to your VPS is not.

Two things that make this better or worse than it looks:

- **Better:** layers are shared. Two images differing only in an upper layer store the common
  layers once, and a pull only fetches what the host lacks.
- **Worse, and specific to this stack:** the upstream build recipe installs Frappe and every
  app in a *single* step, so changing one line in one custom app rebuilds that entire step. The
  result is a new multi-gigabyte layer rather than a small one — so in practice a custom-app
  change costs close to a full image in both storage and transfer.

If the bill turns out to be the deciding factor, the alternatives are a registry with cheaper
egress, or one you host yourself. See [Choosing a container registry: the
options](choosing-a-registry.md#the-options) — cairn does not care which you choose.

## Next

- **[Setup](ghcr-setup.md)** — tokens, scopes, and getting a first push and pull working.
- **[Tags & Troubleshooting](ghcr-tags-and-troubleshooting.md)** — what cairn writes to the
  registry, the deletion rule that is genuinely surprising, and the errors you'll actually hit.
