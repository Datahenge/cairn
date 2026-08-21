# cairn

**Frappe + ERPNext + your custom apps, on one VPS, running the commit you last pushed.**

cairn builds a Docker image from your app repositories, publishes it to a container
registry, and lets your server notice the new image and switch to it on its own.

There is no CI service to configure, no webhook to receive, and no build minutes to pay
for. Nothing reaches into your server from the outside.

Two small systemd timers do the polling, one on the machine that builds and one on the
machine that serves. Both dial outward. Your VPS never opens a port, never holds a
webhook listener, and never hands a deploy key to GitHub.

> *A cairn is a trail marker of stacked stones. Every deploy leaves one behind: the git
> ref, the commits it resolved to, the image tag, the digest. You can always walk back.*

---

## The problem

A customized ERPNext runs code that exists nowhere but your own repositories. Getting
that code onto a server usually means one of three things.

**SSH in and pull.** Fast, and it works. It also leaves no record. Two clients and six
months later, nobody can say with confidence what is actually running on which box, and
"roll it back" means finding the right commit and hoping the migration reverses.

**Wire up GitHub Actions to deploy over SSH.** Traceable, and now your production server
accepts inbound connections from a CI system holding a credential with root-adjacent
reach. That is a large amount of attack surface to accept for one ERP on one VPS.

**Stand up real deployment infrastructure.** Kubernetes, Argo, a pipeline. Correct, and
wildly out of scale for a single server running a single site.

cairn takes the middle path. Your code becomes a versioned, labeled image. Your server
pulls that image when it's ready to. Every deploy is recorded, reversible, and initiated
by the machine that will run it.

## What you get

- **A named image per deploy**, carrying its own provenance. Every image records the
  commits it was built from, the build arguments used, and the version of cairn's own
  build recipe that produced it. `docker inspect` answers "what is this, exactly" months
  later.
- **Rollback as a tag change.** Point the environment back at an earlier image. The
  server converges to it on its next poll. Nothing is rebuilt and nothing is downloaded
  that isn't already on disk.
- **A server that only talks outward.** No inbound port, no runner, no CI account with
  access to production.
- **One package, three roles.** `pipx install datahenge-cairn` gives you the builder, the
  target, and an optional self-hosted registry. Each machine uses whichever role applies
  to it.
- **Everyday verbs that can't get the arguments wrong.** `cairn-adopt logs`,
  `shell`, `console`, `mariadb`, `stop`, `start`. Each one assembles its own
  `docker compose` invocation from the environment's own configuration, so you stop
  hand-typing project names and override lists.

## What cairn will not touch

cairn moves code. It does not move data, and the boundary is deliberate.

- **Your database and your volumes are outside its reach.** The one write cairn ever
  makes is the `bench migrate` that follows a deploy.
- **It does not create sites.** Adopting a host means adopting a deployment that already
  exists and already serves a site.
- **It is not a backup tool.** It will verify that a backup exists before it first touches
  a site, and then it is done with the subject.
- **It is not multi-server orchestration.** One VPS, one site, done thoroughly.

## Where to go next

Read these in order the first time through.

1. **[Why cairn](why-cairn.md)** — what this replaces, and what it keeps. Start here.
   It's the fastest way to decide whether you want this.
2. **[Get Started](get-started/index.md)** — getting cairn onto a machine, for any role.
3. **[Registry](registry/choosing-a-registry.md)** — decide where images live. Do this
   before configuring a builder; both the builder and the target assume the answer.
4. **[Builder](builder/index.md)** — building images and moving environment tags.
5. **[Target](target/index.md)** — adopting a host and converging it.
6. **[Operating the stack](target/operating.md)** — logs, consoles, maintenance holds,
   reclaiming disk.
7. **[Reference](reference/index.md)** — every command, every configuration key.
