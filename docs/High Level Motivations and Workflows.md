# High-Level Motivations and Workflows

Why cairn is shaped the way it is, what it costs to run, and how to actually operate it.

This is the "why" document. It assumes no knowledge of cairn's internals and cites no
requirement numbers — for those, see `docs/`. Everything here derives from one practice and its
real constraints.

---

## 1. The practice this is built for

A solo full-cycle ERPNext practitioner. Requirements through go-live, no handoff. Work splits
into personal projects and **client** projects — and client projects contain the client's own
private customizations and apps.

Two consequences drive almost every design decision in cairn:

**The client owns their code, and therefore their images.** A built image is a derivative of
their source. If the practitioner is the *sole* owner of that image, then the day a relationship
ends badly the client cannot deploy or roll back software they own. That is not a technical
inconvenience; it is holding a business hostage. It has to be structurally impossible.

**One practitioner, many clients, one identity.** Nobody is going to maintain a separate GitHub
account per client. Browsers cache logins, and "which account am I in right now?" is a question
whose wrong answer is expensive. Whatever cairn requires must work with **one** login per
registry, with authorization resolved on the registry's side.

---

## 2. Three modes of operation, and why change velocity matters

An ERPNext engagement is not one workload. It is three, with wildly different rhythms.

| Mode | Duration | Image refresh rate |
| --- | --- | --- |
| **1. Implementation** — building toward go-live | Several months | 1–2 per day |
| **2. Go-live support** | Several weeks | 3–4 per day |
| **3. Normal operations** | Indefinite | 1–3 per week |

**Change happens fast in the first two, and it is not optional.** Progress gets made, the client
wants to see it. A bug surfaces during go-live, it gets hotfixed and shipped immediately. The
value of a hotfix decays by the hour, sometimes by the minute.

So a deploy pipeline for this practice is not judged on throughput. It is judged on whether
shipping a one-line fix is **cheap enough to do without thinking about it**. Anything that makes
a practitioner hesitate before deploying is a defect, because hesitation is how go-live support
goes wrong.

Over one engagement — call it three months of implementation plus three weeks of go-live
support — that is roughly **150 image builds and deployments.**

---

## 3. What that actually costs

Measured and estimated on a real ERPNext image (Frappe + ERPNext + one custom app): about
**2.75 GB unpacked**, roughly **1.2 GB compressed** on the wire.

**Per cycle** — one code change, built, published, deployed:

| | Cost |
| --- | --- |
| Download while building | ~1 GB (warm cache) |
| Local disk churn | ~4 GB |
| Upload to registry | ~0.5 GB |
| Download by the server | ~0.5 GB |

**Per engagement** (~150 cycles):

| | Cost |
| --- | --- |
| Download while building | ~150 GB |
| Local disk churn | ~600 GB |
| Upload to registry | ~75 GB |
| Download by the server | ~75 GB |
| **Total network** | **~300 GB** |

### Five things these numbers teach

**Build time is latency, not labour.** You say "go" and walk away. The server polls, finds the
new image, pulls it, and restarts itself. Nobody watches a progress bar. This is the single most
important property of the pull-based design, and it means build *duration* is a service-level
question ("how fast does a hotfix land?") rather than a cost of your working day.

**The build does not have to happen on your laptop.** All you strictly have to do is push code.
A CI runner can build and publish, and cairn treats that as a first-class situation — it
suppresses its own build transcript there, because the CI system already keeps the record. Your
laptop then contributes nothing but a `git push`.

**Polling is free.** The server checks for a new image every few minutes by fetching a manifest —
kilobytes. Hundreds of checks a day are noise. **Cost scales with deployments, not with how often
the server looks.** Worth knowing, because it looks like it should be expensive and isn't.

**Disk churn is a housekeeping problem, not a cost.** 600 GB of writes over three months is
nothing to a modern SSD. What you need is ~15 GB of free space at all times and the habit of
pruning. Note that cleanup is *two* commands: cairn removes its own superseded images, and the
container engine removes stale build stages, which cairn deliberately refuses to touch so that it
can never destroy your build cache.

**Cost is dominated by two decisions, and neither is "how often do you deploy".** They are
**where the registry lives** and **how many versions you keep.** Deploy frequency barely moves
the bill.

### So what do you tell a client?

> Storage is a few dollars a month — we keep the last handful of versions so we can roll back
> instantly. Transfer is about half a gigabyte per deployment. During implementation and go-live
> expect $10–25 a month; after that, a few dollars. If we put the image registry in the same
> cloud as your server, transfer is effectively free and it's just the storage.

That last sentence is the real answer. Registry *placement* takes the dominant line item to near
zero. And the surprise-invoice scenario is almost always retention: keeping every one of 150
versions instead of the last five turns a couple of gigabytes into seventy-five.

---

## 4. Where images live, and who owns them

Two rules, both about liability rather than engineering.

**The image belongs in the account that owns the source.** You already do this with code — their
GitHub holds their app and you are granted access. An image is a build artifact of that code and
inherits the same ownership. So the registry account is theirs; you are granted access to it;
when the engagement ends they revoke your access and lose nothing.

**Your credential should reach the engagement's images and nothing else.** Ask for write access
to the one image repository, not the client's registry as a whole. The reason is not that you
might act badly — it is that **you will eventually make a mistake**, and the size of that mistake
should be bounded by the credential. This protects you more than it protects them. Decline broad
access when it is offered; an administrator role handed over to "save time" is a risk, not a
convenience.

cairn is built so both rules are satisfiable: the registry coordinates live in the deployment's
own manifest, committed, so a client can take a deployment over without needing anything from
your laptop. Details and a per-option comparison are in **`ABOUT_REGISTRIES.md`**.

---

## 5. The workflows

### A. Laptop-built (the simple case)

```
edit code  →  cairn build --push  →  cairn retag <env> --latest  →  walk away
```

The server converges within a few minutes. Good for personal projects and low-velocity work.
Costs your uplink ~0.5 GB per deploy.

### B. CI-built (the one to grow into)

```
git push  →  CI builds and publishes  →  cairn retag <env> --latest  →  walk away
```

Your laptop uploads nothing but source. The build's download cost moves to the runner, and if the
runner and the registry are in the same place, the publish step is often free.

This also composes with the ownership rule in a pleasing way: **put the pipeline in the client's
account.** The runner's built-in credentials can read their app repository and publish to their
registry. The build happens in their account, billed to them, owned by them — and you never hold
a long-lived push credential at all.

One wrinkle: if the app repository and the pipeline are in *different* accounts, built-in
credentials won't span them and you're back to managing a token. Keeping both in the client's
account avoids it.

### C. Bootstrap — one laptop, one server, nothing paid for

See §6. This is where you start.

---

## 6. Starting from nothing

The situation: one laptop, one cloud server, no paid registry account, and a client who has not
yet agreed to any of this. You need to be delivering now and migrate later.

**The free tiers of hosted registries will not survive implementation velocity.** A ~1.2 GB
compressed image against a free-tier allowance measured in hundreds of megabytes of storage and a
gigabyte or two of monthly transfer means you are over the limit on your first or second deploy —
and with no payment method configured, pushes simply start failing.

**So run the registry on the server itself.** It is the deploy target; the images have to reach
it anyway.

What this buys:

- **No registry bill, ever.** Your server's included bandwidth covers it.
- **Pulls are local.** The server fetches from itself — instant, and it never counts against
  anyone's transfer allowance. The recurring cost of the whole model drops to zero.
- **Real deletion.** Unlike some hosted registries, a self-hosted one lets you delete a single
  image version, so retention is actually manageable.
- **Nothing is exposed.** Bind it to localhost and reach it over an SSH tunnel; the tunnel is the
  authentication, so there are no registry credentials and no certificates to manage.

What it costs:

- **~10 GB of server disk** for a few versions.
- **Your rollback history lives on the machine you would roll back.** Lose the server and you
  lose the stored images with it. Acceptable while bootstrapping, and the reason this is a
  starting point rather than a destination.
- Pushing still crosses the internet at ~0.5 GB per deploy. That cost is inherent — the bytes
  have to get there.

**Migrating later is cheap.** When the client agrees to own their registry, the change is two
lines in the deployment's manifest and one rebuild-and-push. Nothing else about cairn's operation
differs.

---

## 7. What is deliberately not solved

- **The atomic build step.** The upstream recipe installs Frappe and every app in a single step,
  so changing one line in one app re-clones and rebuilds everything. This is why a warm rebuild
  costs about half of a cold one instead of a tenth, and the saving does not improve as your
  change gets smaller. It is the strongest standing argument for eventually maintaining our own
  build recipe, and it is tracked as an open decision rather than acted on.
- **Installing a Frappe App during a deploy.** cairn will not do it, ever. A deploy loop is safe
  because repeating it changes nothing; installing a Frappe App is a one-shot irreversible database
  change. Adding a Frappe App to a live site is a deliberate manual act, exactly as creating the site
  was.
- **Anything inside the database.** cairn ships code. It runs the schema migration the framework
  provides and touches nothing else — no volumes, no SQL, no site configuration.
