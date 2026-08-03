---
status: authoritative
owner: technical
purpose: What GHCR is, who owns what, and its sharp edges, for someone who has never pushed an image to it.
---

# About GHCR — GitHub Container Registry

Written for someone who has used GitHub for years but has never pushed a container image to
it. This explains what you are actually signing into, who ends up owning what, and the handful
of sharp edges that are genuinely surprising.

> ### Read [ABOUT_REGISTRIES.md](ABOUT_REGISTRIES.md) first
>
> **GHCR is not cairn's recommended default.** It is one option, and it is the weakest of them
> on cost: GitHub Packages prices multi-gigabyte artifacts poorly, and an ERPNext image is
> roughly 2.75 GB with no cheap incremental layer (see §6).
>
> This document is most useful for **your own projects**, or for a client already committed to
> GitHub. For client work generally, the ownership and least-privilege rules in
> `ABOUT_REGISTRIES.md` come first, and a client-owned cloud registry usually wins.

cairn is **registry-agnostic** — nothing here is required. Set `[cairn.registry]` in the
deployment's `cairn.toml` and the rest of cairn behaves identically against any registry.

> **Verify the pricing and token details against GitHub's own documentation before
> committing money or credentials.** The mechanics below are stable; the numbers and the
> fine-grained-token story are the parts GitHub changes.

---

## 1. What GHCR actually is

`ghcr.io` is a container registry — a web service that stores container images and hands them
out. It speaks the same standard protocol as Docker Hub, so `podman`, `docker`, and cairn all
talk to it the same way.

It is one component of a larger feature called **GitHub Packages**, which also stores npm,
NuGet, Maven, and RubyGems artifacts. Those share your account's storage quota with GHCR but
are otherwise unrelated. When you read GitHub's docs, "Packages" is the umbrella and
"Container registry" is the part you want.

### "Package" — GitHub's word for a Docker concept

GitHub's docs and UI say **package** where you would say *repository*, and **version** where you
would say *image*. The vocabulary is generic because the same permissions, UI, and API cover npm
tarballs and Maven jars too. Translated:

| Docker / OCI | GHCR calls it | Example |
| --- | --- | --- |
| repository | a **package** (of type `container`) | `ghcr.io/acme-corp/erpnext-acme` |
| image / manifest — one digest | a **package version** | `sha256:1b019793…` |
| tag | a **tag** on a version | `:production`, `:v16-1b019793dc20` |

So a "package" is not vague: for containers it is **exactly one image repository** — the name,
plus every version and tag beneath it. Two things follow that matter later in this document:

- **Permissions are per package, meaning per image repository.** "Write access to the
  `erpnext-acme` package" grants exactly that one repository and nothing else in the account
  (§3).
- **Deletion operates on a version, not a tag.** That is *why* deleting takes every tag on that
  image with it: `production`, `v16`, and `v16-1b019793dc20` are three tags on one version (§8).

One side effect of the shared umbrella: the storage quota covers **all** package types in the
account, so a client's npm packages and your container images draw from the same allowance.

An image lives at a path with three parts:

```
ghcr.io/datahenge/erpnext-btu-v16:production
└─┬───┘ └───┬────┘ └──────┬──────┘ └───┬────┘
registry  owner        image name     tag
```

- **owner** — a GitHub user or organization. Yours.
- **image name** — whatever you choose. cairn takes it from `image_name` in `cairn.toml`.
- **tag** — a movable label. cairn writes several per image; see §7.

**Both the owner and the image name must be lowercase.** This is a registry rule, not a
GitHub one, and it is the first thing that bites people: the organization displayed as
`Datahenge` is addressed as `datahenge`.

## 2. What you are logging into

```
podman login ghcr.io
```

It prompts for a username and a password. What it wants:

- **Username** — your GitHub username. Not the organization name, even when you are pushing
  to the organization. You authenticate *as yourself*; authorization is separate.
- **Password** — **not your GitHub password.** GHCR will not accept it. It wants a
  **Personal Access Token**, which is a long generated string you create in GitHub's
  settings and treat as a password.

Use a **classic** personal access token. GitHub has two kinds — "classic" and "fine-grained"
— and the container registry's support for fine-grained tokens has historically lagged.
Classic is the documented, reliable path. If you prefer fine-grained, check GitHub's current
docs first rather than assuming.

Create one at **Settings → Developer settings → Personal access tokens → Tokens (classic)**.
The scopes (checkboxes) that matter:

| Scope | Grants | Who needs it |
| --- | --- | --- |
| `read:packages` | Pull images | **The VPS** |
| `write:packages` | Push images (includes read) | **Your build machine** |
| `delete:packages` | Delete image versions | Nobody, ideally — see §8 |

If a package is linked to a **private** repository, a classic token may also need the `repo`
scope to read it. If a pull fails with a permission error despite `read:packages`, that is the
first thing to try.

**Make two separate tokens.** The build machine gets `write:packages`; the VPS gets
`read:packages` and nothing else. This is not ceremony — it is the entire mechanism by which
a compromised VPS cannot overwrite your production image. cairn's design leans on it: the
roles are separated by *credentials*, not by shipping different code to each machine.

Give the tokens an expiry you will actually notice, and put them somewhere you can find them
again. GitHub shows a token exactly once.

## 3. How this relates to your GitHub account and repos

This is the part that surprises people, so plainly:

**A package is owned by an account, not by a repository.** When you push
`ghcr.io/datahenge/erpnext-btu-v16`, GHCR creates a *package* belonging to the `datahenge`
organization. It exists whether or not any repository is involved. It did not come from a
repo and it is not inside one.

You can optionally **link** a package to a repository afterwards. Linking:

- makes the package appear in that repo's sidebar, so people find it;
- lets GitHub Actions *in that repo* push to it using the automatic `GITHUB_TOKEN`, with no
  personal token at all;
- can make the package inherit the repo's access permissions, so your collaborators get
  access without being granted it package-by-package.

Two ways to link. Manually, in the package's settings page. Or automatically, by stamping the
image with a label naming the repository:

```
org.opencontainers.image.source = https://github.com/Datahenge/cairn
```

GHCR reads that label on push and links the package for you. **cairn does not currently stamp
this label** — it stamps creation time, title, version, and revision, but not source. That is
a deliberate gap rather than an oversight: adding it means deciding *which* repository an
image points at (the deployment's, or the tool's), which is a design question and not a
detail. Until it is decided, link manually if you want the linkage.

**Repos you merely participate in are irrelevant here.** Being a contributor to someone
else's project grants you nothing on their packages, and your packages are invisible to them
unless you make them public or grant access. Package permissions are their own system.

### How narrow can access be? Narrower than it looks

The question that matters if you are pushing into a *client's* organization: does write access
mean you can overwrite all hundred of their packages? **No.**

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
put in a team with admin over all packages. Do not ask for that, and decline it if offered —
see rule 2 in `ABOUT_REGISTRIES.md`. Ask for write on one package, or on the one repository it
is linked to.

## 4. Who owns the images after deployment

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
  and they cannot deploy or roll back software they own. This is a rule, not a caveat —
  `ABOUT_REGISTRIES.md` rule 1, and a requirement in `docs/requirements/05-config.md`. Push to
  an account **they** own: set `[cairn.registry]` in their deployment's `cairn.toml` and
  nothing else about cairn changes.
- **Anyone with `read:packages` on a private package can pull the whole image**, which
  contains your application code. Treat pull tokens as code access, because that is what they
  are.

## 5. Visibility: private by default

A newly pushed package is **private**. Nobody but you (and accounts you grant) can pull it.

You can change a package to **public** in its settings, and then *anyone on the internet* can
pull it anonymously, with no token. For a proprietary ERPNext build that is almost certainly
wrong — the image contains your custom app source.

Two facts about public that are easy to miss:

- Public packages are **free**, in both storage and bandwidth. Private ones are not. See §6.
- A public image version that has been downloaded more than a few thousand times **cannot be
  deleted at all.** See §8.

## 6. What it costs — read this before you push several images

GHCR is free for public packages. For **private** packages, storage and outbound data
transfer count against your plan's GitHub Packages allowance, and you are billed per gigabyte
beyond it.

**This matters more for ERPNext than for most projects, because the images are large.** A
custom Frappe + ERPNext image is roughly **2.75 GB**. The allowances included with the
personal and small-team plans are on the order of a couple of gigabytes of storage and ten
gigabytes of monthly transfer — meaning **one single image can exceed your entire included
storage**, and one deployment pull can consume a meaningful share of the monthly transfer.

Do the arithmetic for your own situation, with current prices from GitHub's billing docs, on
these three numbers:

1. **Image size** × **how many versions you keep** = storage. Rollback headroom is not free;
   keeping five versions of a 2.75 GB image is about 14 GB.
2. **Image size** × **deploys per month** = outbound transfer. Every `cairn reconcile` that
   actually converges pulls an image.
3. Transfer *into* GitHub Actions is free. Transfer to your VPS is not.

Two things that make this better or worse than it looks:

- **Better:** layers are shared. Two images differing only in an upper layer store the common
  layers once, and a pull only fetches what the host lacks.
- **Worse, and specific to this stack:** the upstream build recipe installs Frappe and every
  app in a *single* step, so changing one line in one custom app rebuilds that entire step.
  The result is a new multi-gigabyte layer rather than a small one — so in practice a
  custom-app change costs close to a full image in both storage and transfer. This is a known
  characteristic of the upstream recipe, recorded in cairn's design notes as one of the
  standing arguments for eventually maintaining our own build recipe. It now has a cost in
  money as well as in build minutes.

If the bill turns out to be the deciding factor, the alternatives are a registry with cheaper
egress, or one you host yourself. cairn does not care which you choose.

## 7. What cairn puts in the registry

Per build, cairn writes **two** tags pointing at the same image:

- a **deterministic** tag like `v16-1b019793dc20`, where the trailing hash is derived from
  every resolved input — the Frappe commit, each app's commit, and the build settings. The
  same inputs always produce the same name.
- a **moving** tag like `v16`, which is repointed to the newest build.

Then, per environment, you point an **environment tag** at a chosen image:

```
cairn new-tag production --latest
```

`production` is now a third name for the same underlying image, and it is the name your VPS
watches. Moving that tag is what deploying, promoting, and rolling back all are — no rebuild,
no upload, just a new name written server-side.

So a single image commonly carries three or more tags at once, and `cairn images` folds them
together and reports them as one image, because that is what they are.

One thing to be clear about, because the word invites the wrong inference: cairn's
deterministic tag is **deterministic, not immutable.** Same inputs → same name. The name is
still a pointer, and a registry will happily move it. The thing that never changes is the
**digest** — the `sha256:…` value. That is the real identity of an image, and it is what
cairn's deploy machinery actually compares.

## 8. Deleting images — the genuinely sharp edge

GHCR's deletion model does not work the way you would guess, and cairn is shaped around it.

**There is no way to delete a single tag.** Deletion operates on a *version* — one underlying
image — and deleting a version removes **every tag pointing at it, and the image itself.**

Read that against §7. If `v16-1b019793dc20`, `v16`, and `production` all point at one image,
then "deleting the `v16` tag" is not an operation GHCR offers. Attempting to clean up a tag
name destroys the image your production environment is running.

Also: **a public version with more than a few thousand downloads cannot be deleted at all**,
by anyone, including you.

This is why `cairn retire <env>` deletes nothing. It tells you what to remove from your
manifest, and warns you that the registry tag will still exist and still resolve. And it is
why `cairn prune` operates only on your **build machine's** local images and never on the
registry. Registry-side cleanup is deliberately left as a manual, deliberate act.

If you do need to reclaim registry space, do it by hand in the package's **Manage versions**
page, deliberately, having first checked with `cairn images` that no environment tag points at
the version you are about to destroy.

## 9. First-time setup, start to finish

**On your build machine, once:**

1. Create a classic token with `write:packages`.
2. `podman login ghcr.io` — your GitHub username, then the token as the password.
3. Verify with a read: `cairn images`. It will report an empty repository rather than a
   permission error.

The credential is stored by podman, not by cairn — normally in
`${XDG_RUNTIME_DIR}/containers/auth.json`. cairn only ever *reads* it. Note that
`XDG_RUNTIME_DIR` is on a tmpfs that is cleared at reboot, so a login there does not survive
one. If you want it to persist, `podman login` writes to `~/.config/containers/auth.json`
when the runtime directory is unavailable, or you can point it there explicitly.

**Then build and publish:**

```
cairn build --push
cairn images                        # confirm it arrived
```

**On the VPS, once:**

1. Create a *second* classic token with only `read:packages`.
2. `docker login ghcr.io` with that one.
3. Nothing else. cairn on the target reads that credential through Docker and stores nothing
   of its own.

**Then set visibility.** Go to the package's settings and confirm it is private. It will be,
but confirm it, because the consequence of being wrong is publishing your client's source
code.

## 10. Errors you will actually hit

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

## 11. What cairn does and does not do with your credentials

Stated plainly, because it is a reasonable thing to want to know about a tool you point at a
production registry:

- cairn **never** asks you for a password, stores one, writes one to disk, or puts one in a
  log or a build transcript.
- cairn **reads** the credential file your `podman login` or `docker login` already created,
  uses it for the duration of one command, and forgets it.
- cairn tries **unauthenticated** access first. For a public repository it never opens your
  credential file at all.
- The build config that names your registry and namespace holds **no secrets** — just the
  hostname and the owner — which is why it is safe to keep beside a deployment.
- On a target, the environment descriptor also holds no secrets. It names the *mechanism*
  holding them and nothing more.

---

## Further reading

- GitHub's own docs: *Working with the Container registry*, and *About billing for GitHub
  Packages* — the authoritative source for tokens and pricing, both of which change.
- [`docs/requirements/03-deploy.md`](../requirements/03-deploy.md) — how cairn uses the
  registry as the desired-state pointer, and the deletion constraints above stated as
  requirements.
- [`docs/requirements/05-config.md`](../requirements/05-config.md) — where registry settings
  live, and why credentials are the container engine's job and never cairn's.
