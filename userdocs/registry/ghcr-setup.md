# GitHub Container Registry: Setup

For someone who has used GitHub for years but never pushed a container image to it: what you
are actually signing into, who ends up owning what, and how to get a first push and pull
working end to end.

*GitHub Container Registry (GHCR) guide: **Setup** · [Ownership & Cost](ghcr-ownership-and-cost.md) ·
[Tags & Troubleshooting](ghcr-tags-and-troubleshooting.md)*

!!! note "Read [Choosing a container registry](choosing-a-registry.md) first"
    **GHCR is not cairn's recommended default.** It is one option, and it is the weakest of
    them on cost: GitHub Packages prices multi-gigabyte artifacts poorly, and an ERPNext image
    is roughly 2.75 GB with no cheap incremental layer (see [Ownership &
    Cost](ghcr-ownership-and-cost.md#what-it-costs)).

    This page is most useful for **your own projects**, or for a client already committed to
    GitHub. For client work generally, the ownership and least-privilege rules in [Choosing a
    container registry](choosing-a-registry.md) come first, and a client-owned cloud registry
    usually wins.

cairn is **registry-agnostic** — nothing here is required. Set `[cairn.registry]` in the
deployment's `cairn.toml` and the rest of cairn behaves identically against any registry.

!!! warning "Verify against GitHub's own current docs"
    The mechanics below are stable; the pricing and fine-grained-token details are the parts
    GitHub changes. Check GitHub's own documentation before committing money or credentials.

## What GHCR actually is

`ghcr.io` is a container registry — a web service that stores container images and hands them
out. It speaks the same standard protocol as Docker Hub, so `podman`, `docker`, and cairn all
talk to it the same way.

It is one component of a larger feature called **GitHub Packages**, which also stores npm,
NuGet, Maven, and RubyGems artifacts. Those share your account's storage quota with GHCR but
are otherwise unrelated. When you read GitHub's docs, "Packages" is the umbrella and
"Container registry" is the part you want.

### "Package" — GitHub's word for a Docker concept

GitHub's docs and UI say **package** where you would say *repository*, and **version** where
you would say *image*. The vocabulary is generic because the same permissions, UI, and API
cover npm tarballs and Maven jars too. Translated:

| Docker / OCI | GHCR calls it | Example |
| --- | --- | --- |
| repository | a **package** (of type `container`) | `ghcr.io/acme-corp/erpnext-acme` |
| image / manifest — one digest | a **package version** | `sha256:1b019793…` |
| tag | a **tag** on a version | `:production`, `:v16-1b019793dc20` |

So a "package" is not vague: for containers it is **exactly one image repository** — the name,
plus every version and tag beneath it. Two things follow that matter later:

- **Permissions are per package, meaning per image repository.** "Write access to the
  `erpnext-acme` package" grants exactly that one repository and nothing else in the account.
- **Deletion operates on a version, not a tag.** That is *why* deleting takes every tag on that
  image with it — see [Tags & Troubleshooting: deleting
  images](ghcr-tags-and-troubleshooting.md#deleting-images-the-genuinely-sharp-edge).

One side effect of the shared umbrella: the storage quota covers **all** package types in the
account, so a client's npm packages and your container images draw from the same allowance.

An image lives at a path with three parts:

```
ghcr.io/datahenge/erpnext-v16:production
└─┬───┘ └───┬────┘ └──────┬──────┘ └───┬────┘
registry  owner        image name     tag
```

- **owner** — a GitHub user or organization. Yours.
- **image name** — whatever you choose. cairn takes it from `image_name` in `cairn.toml`.
- **tag** — a movable label. cairn writes several per image; see [Tags &
  Troubleshooting](ghcr-tags-and-troubleshooting.md).

**Both the owner and the image name must be lowercase.** This is a registry rule, not a GitHub
one, and it is the first thing that bites people: the organization displayed as `Datahenge` is
addressed as `datahenge`.

## What you are logging into

```
podman login ghcr.io
```

It prompts for a username and a password. What it wants:

- **Username** — your GitHub username. Not the organization name, even when you are pushing to
  the organization. You authenticate *as yourself*; authorization is separate.
- **Password** — **not your GitHub password.** GHCR will not accept it. It wants a **Personal
  Access Token**, which is a long generated string you create in GitHub's settings and treat as
  a password.

Use a **classic** personal access token. GitHub has two kinds — "classic" and "fine-grained" —
and the container registry's support for fine-grained tokens has historically lagged. Classic
is the documented, reliable path. If you prefer fine-grained, check GitHub's current docs first
rather than assuming.

Create one at **Settings → Developer settings → Personal access tokens → Tokens (classic)**.
The scopes (checkboxes) that matter:

| Scope | Grants | Who needs it |
| --- | --- | --- |
| `read:packages` | Pull images | **The VPS** |
| `write:packages` | Push images (includes read) | **Your build machine** |
| `delete:packages` | Delete image versions | Nobody, ideally — see [Tags & Troubleshooting](ghcr-tags-and-troubleshooting.md#deleting-images-the-genuinely-sharp-edge) |

If a package is linked to a **private** repository, a classic token may also need the `repo`
scope to read it. If a pull fails with a permission error despite `read:packages`, that is the
first thing to try.

**Make two separate tokens.** The build machine gets `write:packages`; the VPS gets
`read:packages` and nothing else. This is not ceremony — it is the entire mechanism by which a
compromised VPS cannot overwrite your production image. cairn's design leans on it: the roles
are separated by *credentials*, not by shipping different code to each machine.

Give the tokens an expiry you will actually notice, and save them somewhere retrievable — GitHub
shows a token exactly once.

## How this relates to your GitHub account and repos

The part that surprises people: **a package is owned by an account, not by a repository.** When you push
`ghcr.io/datahenge/erpnext-v16`, GHCR creates a *package* belonging to the `datahenge`
organization. It exists whether or not any repository is involved. It did not come from a repo
and it is not inside one.

You can optionally **link** a package to a repository afterwards. Linking:

- makes the package appear in that repo's sidebar, so people find it;
- lets GitHub Actions *in that repo* push to it using the automatic `GITHUB_TOKEN`, with no
  personal token at all;
- can make the package inherit the repo's access permissions, so your collaborators get access
  without being granted it package-by-package.

Link it manually in the package's settings page, or automatically by stamping the image with a
label naming the repository:

```
org.opencontainers.image.source = https://github.com/Datahenge/cairn
```

GHCR reads that label on push and links the package for you. **cairn does not currently stamp
this label** — it stamps creation time, title, version, and revision, but not source. Until
that changes, link manually if you want the linkage.

**Repos you merely participate in are irrelevant here.** Being a contributor to someone else's
project grants you nothing on their packages, and your packages are invisible to them unless
you make them public or grant access. Package permissions are their own system.

### How narrow can access be? Narrower than it looks

If you are pushing into a *client's* organization: does write access mean you could overwrite
all hundred of their packages? **No.**

- `write:packages` on a token is a **ceiling on what the token may attempt**, not a grant of
  what you may touch. Authorization is resolved per package, every time.
- Each package has its own access list with **Read / Write / Admin** roles, granted to a user
  or a team, **per package**.
- A package **linked to a repository inherits that repository's permissions**. So the per-repo
  model you are used to applies to images: link the ERPNext image to the repo you already have
  write on, and your image access is exactly your repo access — nothing more.
- **Plain org membership grants nothing** on existing private packages. They are invisible.
- **A typo cannot clobber anything.** Pushing to a misspelled name either creates a *new*
  package, or is denied if that name exists and you lack Write on it. There is no path where a
  mistyped push overwrites a package you were never granted.

The configuration that *would* be dangerous is being made an **organization owner**, or being
put in a team with admin over all packages. Do not ask for that, and decline it if offered — see
[Choosing a container registry](choosing-a-registry.md#2-your-credential-should-reach-the-engagements-images-and-nothing-else).
Ask for write on one package, or on the one repository it is linked to.

## First-time setup, start to finish

**On your build machine, once:**

1. Create a classic token with `write:packages`.
2. `podman login ghcr.io` — your GitHub username, then the token as the password.
3. Verify with a read: `cairn-registry images --host ghcr.io --namespace datahenge --image
   erpnext-v16` (your owner and image name in place of these). It will report an empty
   repository rather than a permission error. This reads the repository directly rather than
   listing the registry, which is what reaches GHCR at all — see [Registry CLI:
   images](cli.md#images).

The credential is stored by podman, not by cairn — normally in
`${XDG_RUNTIME_DIR}/containers/auth.json`. cairn only ever *reads* it. Note that
`XDG_RUNTIME_DIR` is on a tmpfs that is cleared at reboot, so a login there does not survive
one. If you want it to persist, `podman login` writes to `~/.config/containers/auth.json` when
the runtime directory is unavailable, or you can point it there explicitly.

**Then build and publish:**

```bash
cairn-build build --push
cairn-registry images --host ghcr.io --namespace datahenge --image erpnext-v16   # confirm it arrived
```

**On the VPS, once:**

1. Create a *second* classic token with only `read:packages`.
2. `docker login ghcr.io` with that one.
3. Nothing else. cairn on the target reads that credential through Docker and stores nothing of
   its own.

**Then set visibility.** Go to the package's settings and confirm it is private. It will be,
but confirm it, because the consequence of being wrong is publishing your client's source code
— see [Ownership & Cost: visibility](ghcr-ownership-and-cost.md#visibility-private-by-default).

## What cairn does and does not do with your credentials

Stated plainly, because it is a reasonable thing to want to know about a tool you point at a
production registry:

- cairn **never** asks you for a password, stores one, writes one to disk, or puts one in a log
  or a build transcript.
- cairn **reads** the credential file your `podman login` or `docker login` already created,
  uses it for the duration of one command, and forgets it.
- cairn tries **unauthenticated** access first. For a public repository it never opens your
  credential file at all.
- The build config that names your registry and namespace holds **no secrets** — just the
  hostname and the owner — which is why it is safe to keep beside a deployment.
- On a target, the environment descriptor also holds no secrets. It names the *mechanism*
  holding them and nothing more.

## Next: ownership, cost, and tags

- **[Ownership & Cost](ghcr-ownership-and-cost.md)** — who owns the images after deployment,
  visibility defaults, and what GHCR actually charges for an ERPNext-sized image.
- **[Tags & Troubleshooting](ghcr-tags-and-troubleshooting.md)** — what cairn writes to the
  registry, the deletion rule that is genuinely surprising, and the errors you'll actually hit.
