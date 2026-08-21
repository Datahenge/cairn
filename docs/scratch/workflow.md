# The workflow

This page describes a working cairn deployment in ordinary use. Nothing here is a setup
instruction. The point is to show you what you'd be signing up for before you spend an
afternoon on the installation.

The example is a client called Acme, running ERPNext plus two custom apps on a single VPS
at `erp.acmecorp.com`, with a second small machine doing the builds.

---

## Monday: you ship a change

You finish a change to one of Acme's custom apps and merge it to `main`. That's the whole
deploy step. You close the laptop.

Within the hour, the build machine's timer wakes up, notices that `main` resolves to a
commit it hasn't built, and builds an image. It pushes that image to the registry and
moves the `production` tag to point at it.

A few minutes later, the VPS's own timer wakes up, sees that `production` now resolves to
a digest it isn't running, pulls it, restarts the stack, runs `bench migrate`, and waits
for the site to come back healthy.

Nobody typed anything. If you want to watch it happen instead of trusting it, both sides
log to the journal:

```
journalctl -u cairn-reconcile -f
```

```
Environment production — site erp.acmecorp.com
Watching ghcr.io/acmecorp/erpnext-v16:production
Pulling ghcr.io/acmecorp/erpnext-v16:production
Starting the stack
Migrating erp.acmecorp.com
Verifying health
  containers are up
Converged to sha256:3f9a1c2e...
```

## Tuesday: you want to know what's running

Not "roughly which branch." The actual commits.

```
cairn-build images
```

```
cairn/erpnext-v16:v16-d47f139c6ffe  (input hash d47f139c6ffe)
  frappe       v16.25.0         9a8daf34
  erpnext      v16.26.1         fd00cebb
  built from recipe a1c2e3f4
    a1b2c3d4e5f6    1.79 GB       2m  cairn/erpnext-v16:v16-d47f139c6ffe
```

Every app, every resolved commit, and the version of the build recipe that assembled
them. The same information travels with the image as OCI labels, so the answer survives
the terminal scrollback and can be read off a container running on a host you're seeing
for the first time.

## Wednesday: something's wrong and you need to look

You don't reach for `docker compose`. The compose project name, the base file, the
override list, and the image variables are all recorded on the host, and cairn builds the
invocation from them.

```
cairn-adopt logs -f backend
cairn-adopt shell
cairn-adopt console          # bench console, already on the right site
cairn-adopt mariadb          # MariaDB console, already on the right site
```

`console` and `mariadb` know which site to open. You don't pass a site name, and you
can't accidentally open the wrong one.

## Thursday: the change was bad

Deploys go wrong. cairn's answer is to move the environment backward and let the target
converge to it, the same way it converges to anything else.

Point the environment's manifest back at the earlier ref and reassign:

```
cairn-build assign-tag --manifest /srv/cairn/acmecorp/cairn_production.toml
```

The old image is still sitting in the VPS's local storage, so the next reconcile is a
restart and a migration rather than a download. The site is back on the previous release
in about the time a `bench migrate` takes.

Two things worth being clear-eyed about:

- **The migration runs forward, not backward.** cairn re-migrates against the older code.
  It does not reverse the migration the bad deploy performed. If that deploy dropped a
  column, rolling the image back will not bring the column back.
- **cairn will never do this by itself.** A failed deploy halts and reports. It does not
  attempt an automatic rollback, because deciding to go backward is a judgment about your
  data, and cairn does not make judgments about your data.

## Friday: you need the box to hold still

You want to edit the compose file, or resize a volume, or take an hour of downtime for a
database change. If you just stop the containers, the reconcile timer will helpfully start
them again and run a migration while you're mid-surgery.

So you tell cairn the stack is down on purpose:

```
cairn-adopt stop --reason "publishing 3306 on loopback"
```

That's a **hold**. It's a real state, distinct from "running" and from "crashed." While
it's in place, the timer keeps waking up and keeps deliberately doing nothing, and every
`doctor` run reminds you the hold is there:

```
WARN maintenance hold  held 2026-08-19 14:02:11Z — publishing 3306 on loopback.
                       This host will not converge until `cairn-adopt start`.
```

A hold survives a reboot, on the theory that a machine rebooting in the middle of your
maintenance window should stay down rather than come back half-configured. Nothing expires
it. That's why `doctor` mentions it every single time.

When you're finished:

```
cairn-adopt start
```

The hold lifts, containers whose configuration changed get recreated, and the host
converges to whatever the environment tag currently points at.

## Eventually: the disk fills up

Every image the host has ever run stays in local storage. That's what makes Thursday's
rollback fast, and an ERPNext image is not small.

```
cairn-adopt prune --dry-run
```

```
Will remove 2 image(s) this host previously ran:
  7b3c1d9e0a42     1.4 GB  input hash a1b2c3d4e5f6
  2f88ba60c715     1.4 GB  input hash 4d5e6f708192
Reclaims 2.8 GB.

Keeping 1 image(s) for rollback headroom.
Currently running: d47f139c6ffe. Never removed.
```

The running image is read off the running container, never inferred from which image is
newest. After a rollback those are different, and guessing would delete the one thing you
can't afford to lose. Volumes and containers are out of scope for this command entirely.

---

## What this adds up to

Merging is deploying. Every deploy is a labeled image you can identify months later.
Reversing one is a tag move, not an archaeology project. Your production server never
accepts an inbound connection to make any of it happen.

That's the whole proposition. If it's the shape of workflow you want, the next two pages
are [Concepts](concepts.md) and [Install](install.md).
