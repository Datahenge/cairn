# GitHub Container Registry: Tags & Troubleshooting

What cairn actually writes to GHCR, the deletion rule that catches people off guard, and the
errors you're most likely to hit.

*GitHub Container Registry (GHCR) guide: [Setup](ghcr-setup.md) ·
[Ownership & Cost](ghcr-ownership-and-cost.md) · **Tags & Troubleshooting***

## What cairn puts in the registry

Per build, cairn writes **two** tags pointing at the same image:

- a **deterministic** tag like `v16-1b019793dc20`, where the trailing hash is derived from
  every resolved input — the Frappe commit, each app's commit, and the build settings. The
  same inputs always produce the same name.
- a **moving** tag like `v16`, which is repointed to the newest build.

Then, per environment, you point an **environment tag** at a chosen image:

```bash
cairn-build assign-tag --manifest cairn_production.toml
```

`production` is now a third name for the same underlying image, and it is the name your VPS
watches. Moving that tag is what deploying, promoting, and rolling back all are — no rebuild,
no upload, just a new name written server-side.

So a single image commonly carries three or more tags at once, and `cairn-build images` folds
them together and reports them as one image, because that is what they are.

One thing to be clear about, because the word invites the wrong inference: cairn's
deterministic tag is **deterministic, not immutable.** Same inputs → same name. The name is
still a pointer, and a registry will happily move it. The thing that never changes is the
**digest** — the `sha256:…` value. That is the real identity of an image, and it is what
cairn's deploy machinery actually compares.

## Deleting images — the genuinely sharp edge

GHCR's deletion model does not work the way you would guess, and cairn is shaped around it.

**There is no way to delete a single tag.** Deletion operates on a *version* — one underlying
image — and deleting a version removes **every tag pointing at it, and the image itself.**

Read that against the section above. If `v16-1b019793dc20`, `v16`, and `production` all point
at one image, then "deleting the `v16` tag" is not an operation GHCR offers. Attempting to
clean up a tag name destroys the image your production environment is running.

Also: **a public version with more than a few thousand downloads cannot be deleted at all**, by
anyone, including you.

This is why `cairn-build retire <env>` deletes nothing. It tells you what to remove from your
manifest, and warns you that the registry tag will still exist and still resolve. And it is why
`cairn-build prune` operates only on your **build machine's** local images and never on the
registry. Registry-side cleanup is deliberately left as a manual, deliberate act.

If you do need to reclaim registry space, do it by hand in the package's **Manage versions**
page, deliberately, having first checked with `cairn-build images` that no environment tag
points at the version you are about to destroy.

## Errors you will actually hit

**`the registry would not issue a read token (requested access to the resource is denied)`**

GHCR answers "you are not logged in", "this repository does not exist", and "this is private
and you cannot read it" with the *same* response, deliberately, so that guessing cannot reveal
which repositories exist. cairn's message lists all three causes because it genuinely cannot
tell them apart. Check them in that order — and check the spelling of the namespace, since a
typo is indistinguishable from a permissions problem.

**`unauthorized` / `denied` on push**

Your token has `read:packages` but not `write:packages`, or you are logged in as a different
account than you think. `podman login ghcr.io` again.

**`name unknown` or a 404 on a path you are sure exists**

Almost always capitalization. `ghcr.io/Datahenge/...` is not `ghcr.io/datahenge/...`.

**A pull fails on the VPS but works on your laptop**

The VPS's token is missing `read:packages`, or the package is linked to a private repository
and the token also needs `repo`, or the login was done as `root` and the pull is running as a
different user — Docker credentials are per-user.

## Next

- **[Setup](ghcr-setup.md)** — tokens, scopes, and getting a first push and pull working.
- **[Ownership & Cost](ghcr-ownership-and-cost.md)** — who owns the images after deployment,
  visibility defaults, and what an ERPNext-sized image actually costs.
- **[Choosing a container registry](choosing-a-registry.md)** — how GHCR compares to the other
  options.
