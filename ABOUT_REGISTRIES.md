# Choosing a container registry

cairn builds an image and puts it somewhere; your servers pull it from there. That "somewhere"
is a **container registry**, and cairn works with any of them — it stores no credentials, hardwires
no hostname, and has no preference.

This document exists because *which* registry you pick is not a neutral technical choice when you
build software for clients. Two of the three rules below are about liability, not engineering.

---

## The three rules

### 1. The image belongs in the account that owns the source

You already do this with code: the client's GitHub holds their app, and you have been granted
access to read it. **The image is a build artifact of that code and inherits the same ownership.**

The failure this prevents is specific. If you are the sole owner of a client's built image, then
the day the relationship ends badly, that client cannot deploy or roll back software **they own**.
Their operations depend on your goodwill. That is not a position to be in, in either direction —
it is bad for them, and it is an obligation you did not agree to carry.

So: the registry account is theirs. You are granted access to it. When the engagement ends, they
revoke your access and lose nothing.

Your own projects are the obvious exception. Your registry, your account, your bill.

### 2. Your credential should reach the engagement's images and nothing else

Ask for write access to **the ERPNext image, or the repository holding it** — not to the client's
registry as a whole.

The reason is not that you might act badly. It is that **you will eventually make a mistake**, and
the size of the mistake should be bounded by the credential. A token that can write exactly one
repository cannot destroy a client's other images no matter what you type. This protects you more
than it protects them: it means a bad afternoon cannot become a liability event.

A corollary worth stating: **do not accept broad access when it is offered.** A client who makes
you an administrator of their whole registry to "save time" has handed you a risk, not a
convenience. Ask to be narrowed.

### 3. Nobody's credentials live in cairn

cairn never asks for, stores, writes, or logs a password or token. You run `podman login` or
`docker login`; the container engine keeps the credential; cairn reads it when it needs to and
forgets it. What cairn stores is a hostname and an account name, neither of which is a secret.

---

## What cairn needs from you

Two values, in the deployment's `cairn.toml`, committed:

```toml
[cairn.registry]
host      = "ghcr.io"
namespace = "acme-corp"      # the client's account — not yours
```

These are committed deliberately, so the client can take the deployment over and keep publishing
to their own registry without needing anything from your laptop. Machine-specific settings —
which container engine you build with, where transcripts go — stay in your own config and are
never committed.

Absent a `[cairn.registry]`, images stay local and cairn never guesses a registry.

To publish somewhere else temporarily without editing a client's file, a `cairn.local.toml` beside
the manifest overrides it.

---

## The options

Ordered by how well they satisfy rules 1 and 2. **Verify current pricing before committing** — it
changes, and the numbers below are indicative.

### Client-owned cloud registry — the default recommendation

AWS **ECR**, Google **Artifact Registry**, Azure **ACR**.

- **Ownership** — unambiguous. It is inside the client's cloud account, alongside everything else
  of theirs.
- **Least privilege** — the strongest available. ECR scopes IAM policies to an individual
  repository ARN; Artifact Registry grants a writer role on a single repository; ACR offers
  repository-scoped tokens. You can hold a credential that can write `erpnext-acme` and literally
  nothing else.
- **Cost** — the best fit by a wide margin at ERPNext image sizes. Storage is flat per GB with no
  small included cap to blow through, and **egress is often free or trivial when the VPS is in the
  same cloud and region** — which is the single biggest cost lever available, since every deploy
  pulls a multi-gigabyte image.
- **Credential handling** — one login per registry hostname. Because the hostname *is* the
  identity, there is no ambiguity about which client you are pushing to and no browser session
  involved.
- **Cost to you** — the most setup. Each client needs a cloud account and someone to create the
  repository and the scoped credential.

**Pick this when** the client already has a cloud account, or their VPS is already in one.

### Client-owned GitHub organization

- **Ownership** — good. The package belongs to their org.
- **Least privilege** — good, and better than it first appears: packages carry their own
  Read/Write/Admin access list, and a package **linked to a repository inherits that repository's
  permissions** — so the familiar per-repo model applies to images too. Link the image to the
  ERPNext repo you already have write on, and your image access is exactly your repo access.
  Plain org membership grants nothing on existing private packages, and a mistyped push either
  creates a new package or is denied; it cannot overwrite one you were never granted. **Do not
  accept org ownership** — that is the configuration that would make access effectively
  boundless.
- **Credential handling** — the simplest of any option. **One** GitHub account and one token, for
  every client. Authorization resolves server-side per organization. No second login, ever.
- **Cost** — **the weak point, and the reason this is not the default.** GitHub Packages prices
  multi-gigabyte artifacts poorly: a small included allowance, then per-GB storage at roughly
  2.5× a purpose-built registry, plus per-GB egress on every pull to a VPS. It is made worse by
  the upstream build recipe having no per-app layer seam, so **every build is a fresh full-size
  layer** rather than a cheap delta — layer sharing saves you almost nothing, and each retained
  rollback version costs close to a whole image.
- See **[ABOUT_GHCR.md](ABOUT_GHCR.md)** for the mechanics: tokens, scopes, visibility, and the
  deletion rule that is genuinely surprising.

**Pick this when** the client is already on GitHub, images are small or few, or the convenience of
one credential outweighs the bill.

### Registry on the client's own VPS

Run a registry container on the deploy target itself.

- **Ownership** — their hardware, their disk. Unambiguous.
- **Least privilege** — you have access to their server anyway, so this adds no new exposure.
- **Cost** — no registry bill at all, and pulls never leave the machine, so they are instant and
  free. Attractive given cairn targets a single VPS.
- **The real cost** — your **rollback history shares a failure domain with the thing you would
  roll back.** Lose the host and you lose every stored image with it. It also puts disk pressure
  on the server that is running production.

**Pick this when** cost dominates and off-host rollback history is genuinely not needed — or
alongside another registry, not instead of one.

### Your own namespace

- Correct for **your own projects** and nothing else.
- For client work it fails rule 1 outright.
- It is defensible in exactly one business model, which is not cairn's assumption: if you were a
  SaaS host and clients logged into *your* hosted ERPNext, the images would legitimately be yours
  — while their source stayed in their own accounts with you granted read.

---

## What to ask a client for

Concretely, so the request is small and easy to grant:

> I need somewhere to publish the ERPNext container image I build for you. It should live in an
> account **you** own, so you are never dependent on me to deploy or roll back your own software.
>
> Please create one container repository named `erpnext-<yourname>` and grant me **write access to
> that repository only** — not to your registry as a whole. If anything goes wrong on my end, I
> want the damage to be limited to this one repository.
>
> Your servers will also need a **read-only** credential to pull it.

That last line matters: the deploy target gets a **pull-only** credential. It is what makes a
compromised server unable to overwrite the image it runs, and it is the same separation on every
registry.

---

## Further reading

- **[ABOUT_GHCR.md](ABOUT_GHCR.md)** — GitHub's registry in detail, for your own projects or a
  client already on GitHub.
- [`docs/requirements/05-config.md`](docs/requirements/05-config.md) — the rules above stated as
  requirements, including why the registry coordinates are committed with the deployment.
- [`docs/requirements/03-deploy.md`](docs/requirements/03-deploy.md) — how cairn uses a registry
  tag as the desired-state pointer your servers converge to.
