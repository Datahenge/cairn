# Why cairn

<!--
  MAINTENANCE NOTE: every factual claim on this page about frappe_docker is checked
  against frappe/frappe_docker @ main. frappe_docker changes. Re-verify this page
  whenever you touch it, and update the "checked against" line at the bottom.
-->

If you run a customized ERPNext today, you almost certainly run
[frappe_docker](https://github.com/frappe/frappe_docker). So does cairn: cairn's build
recipe was bootstrapped from frappe_docker's own Containerfile, and cairn's compose
configuration descends from frappe_docker's.

This page is not an argument that frappe_docker is bad. It's an argument about scope.

frappe_docker gives you **parts**: a Containerfile that can build a custom image, compose
files with overrides for the database, cache, and TLS, and documentation for wiring them
together. That's what it set out to provide, and it provides it well.

What it deliberately does not give you is a **lifecycle**. Nothing in frappe_docker knows
what you built last time, what's running now, how to get from one to the other, or how to
get back. Its own documentation, at the end of the build instructions, points you toward
CI/CD pipelines. That's an accurate handoff: the lifecycle is yours to build.

cairn is that lifecycle, built once, for the specific shape almost every Frappe
integrator actually has: one VPS, one site, a handful of custom apps, no platform team.

---

## The problem underneath the annoyance

Start with the part that isn't about convenience.

frappe_docker's `apps.json` identifies your apps by **branch**:

```json
[
  { "url": "https://github.com/frappe/erpnext",  "branch": "version-16" },
  { "url": "https://github.com/acmecorp/acme_custom", "branch": "main" }
]
```

Branches move. Build from that file on Tuesday and again on Thursday and you get
different code, from identical inputs, under whatever tag you typed on the command line.
Nothing in the image records which commits went into it. Nothing checks whether you
already built this exact combination last week.

So the question "what is running in production right now" has no reliable answer. You have
a tag you chose by hand, and the honest response is to open a shell in the container and
start reading version strings.

cairn resolves every app reference to a commit at build time, records those commits
in the image as OCI labels alongside the build arguments and the version of the recipe
that produced it, and derives the image tag from the resolved content rather than from
your typing. The same inputs produce the same tag. Different inputs cannot collide.

`cairn-build images` reports that back: for each image on the machine, the tag, the input
hash it was derived from, the ref and commit of frappe and of every custom app, and the
recipe commit that built it. It reads off any host, at any time, months later, without
opening a shell in a container.

## One changed line, both ways

A client reports a bug. You fix it in one of their custom apps and merge to `main`.

### With frappe_docker

On your workstation, or wherever you build:

```bash
cd frappe_docker
$EDITOR apps.json                       # confirm branches are still what you want
docker build \
  --build-arg=FRAPPE_PATH=https://github.com/frappe/frappe \
  --build-arg=FRAPPE_BRANCH=version-16 \
  --secret=id=apps_json,src=apps.json \
  --tag=ghcr.io/acmecorp/erpnext-v16:???   \
  --file=images/custom/Containerfile .
docker push ghcr.io/acmecorp/erpnext-v16:???
```

The `???` is the first real decision. Increment a number by hand and hope you don't
collide with something. Reuse `latest` and lose the ability to say what's deployed. Use a
date and hope you never build twice in one day.

Then SSH to the server:

```bash
ssh erp.acmecorp.com
cd /opt/frappe_docker
$EDITOR .env                            # CUSTOM_TAG=... the number you just invented
docker compose --project-name acmecorp \
  -f compose.yaml \
  -f overrides/compose.mariadb.yaml \
  -f overrides/compose.redis.yaml \
  -f overrides/compose.https.yaml \
  up -d
docker exec -it acmecorp-backend-1 bash
  bench --site erp.acmecorp.com migrate
  exit
docker compose --project-name acmecorp -f ... logs -f    # the whole -f chain again
```

Get one override out of that chain and the stack comes up subtly wrong. Get the project
name wrong and compose creates a second, parallel deployment.

Some weeks later, the disk fills. `docker image prune` doesn't know which images this host
has actually run, which one is live, or which ones your builder produced and still needs,
so pruning becomes something you do carefully by hand, at the worst possible moment.

And if the fix was itself broken, "roll back" means reconstructing which tag was running
before, editing `.env` again, and running the whole sequence again.

### With cairn

```bash
git push
```

The builder's timer resolves the refs, notices the commit is new, builds, pushes, and
moves the environment's tag. The target's timer notices the tag moved, pulls, restarts,
migrates, and verifies health. Both machines dial outward. Nothing reaches into the
server.

If you'd rather drive it yourself, the manual form is three commands and no invented
identifiers:

```bash
cairn-build build   --manifest /srv/cairn/acmecorp/cairn_production.toml
cairn-build push    --manifest /srv/cairn/acmecorp/cairn_production.toml
cairn-build assign-tag --manifest /srv/cairn/acmecorp/cairn_production.toml
```

On the server, the everyday verbs carry no arguments, because the project name, compose
file, override list, and site name are all recorded in the environment descriptor:

```bash
cairn-adopt logs -f
cairn-adopt console
cairn-adopt stop --reason "adding a port mapping"
cairn-adopt prune --dry-run
```

## Side by side

|                          | frappe_docker                                    | cairn                                                         |
| ------------------------ | ------------------------------------------------ | ------------------------------------------------------------- |
| App versions pinned by   | branch, which moves                              | resolved commit                                                |
| Image tag                | whatever you type                                | derived from resolved inputs                                   |
| What's inside an image   | not recorded                                     | commits, build args, and recipe version, as OCI labels         |
| Getting code to a server | SSH, edit `.env`, compose up, exec, migrate      | the server polls and converges                                 |
| Inbound access needed    | yes, you are SSHing in; more if you add CI       | none                                                           |
| Registry                 | bring your own                                   | bring your own, or `cairn-registry` hosts one                  |
| Daily operations         | `docker compose` with the full override chain    | `cairn-adopt logs / shell / console / mariadb / stop / start`  |
| Maintenance windows      | stop the containers and remember not to touch it | a recorded hold that automation respects and `doctor` reports  |
| Old images               | `docker image prune`, carefully, by hand         | `cairn-adopt prune`, which reads the running container         |
| Scheduled builds/deploys | build it yourself                                | two systemd timers, installed by `setup-timer`                 |

## What cairn keeps

- **The recipe.** cairn's Containerfile started as frappe_docker's and stays close to it.
  You are not getting an exotic image.
- **The compose model.** Same services, same shape, same override concept. The compose
  file on your host is yours to edit; cairn writes it once and never regenerates it.
- **The escape hatch.** Everything cairn manages is ordinary Docker. If cairn disappeared
  tomorrow, you'd be left holding a normal compose deployment and a registry full of
  normal images.

## What cairn does not try to be

- **It is not multi-server orchestration.** One VPS, one site. If you need to schedule
  across a fleet, you want Kubernetes, and frappe_docker's Helm chart is a better starting
  point than this.
- **It does not create sites.** Adopting a host means adopting a deployment that already
  exists and already serves a site.
- **It does not manage your data.** The one database write cairn makes is the
  `bench migrate` that follows a deploy. Backups, volumes, and site config stay yours.

---

*Checked against `frappe/frappe_docker` @ main, 2026-08-20. frappe_docker's build and
deployment documentation changes; if something here no longer matches, the error is
ours.*

*Every cairn command named on this page exists and was checked against the source. The
`cairn-build images` report described above has not been captured from a live run for this
page, so no sample of its output is shown here.*
