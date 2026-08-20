# Operating the Stack

Once a target is under cairn's management, `cairn-adopt` gives you verbs for the everyday work
— looking at logs, opening a console, taking the stack down for maintenance, reclaiming the disk
old images hold — so you never need to reach for `docker compose` yourself.

That matters more than convenience. cairn builds each `docker compose` invocation from the
environment descriptor: the project name, the compose file and its overrides, and the image
variables the file interpolates. A hand-written command that gets any of those wrong can start
the wrong image or, worse, appear to work. The verbs below get it right by construction, and
none of them needs an argument — everything comes from `/etc/cairn/adopt.toml`.

## Looking at a running stack

```bash
cairn-adopt logs                 # every service
cairn-adopt logs -f              # follow
cairn-adopt logs --tail 200 backend
```

```bash
cairn-adopt shell                # a shell in the bench container
cairn-adopt shell db             # ...or in another service
cairn-adopt console              # bench console, for this environment's site
cairn-adopt mariadb              # a MariaDB console, for this environment's site
```

`console` and `mariadb` already know which site to open — you don't pass a site name.

!!! note "Reading your own site config"
    cairn has no verb that prints `site_config.json` or `common_site_config.json`, and that is
    deliberate: `site_config.json` holds your database password, and cairn does not read or
    print secrets. Use `cairn-adopt shell` and read the file yourself — the credential then
    never passes through cairn or its output.

    ```bash
    cairn-adopt shell
    cat sites/common_site_config.json
    cat sites/<your-site>/site_config.json
    ```

## Taking the stack down

```bash
cairn-adopt stop --reason "adding a port mapping"
cairn-adopt start
cairn-adopt restart
```

`stop` brings the containers down **and holds the environment there**. `start` releases the
hold and brings it back, converging to whatever image the environment's tag points at.
`restart` does both in one step.

Volumes are never touched by any of these. `stop` stops containers; it does not remove them,
and it does not remove data.

## The hold

A held environment is one you have deliberately stopped. It is a real state, distinct from
"running" and from "broken", and cairn needs it: without a hold, the reconcile timer cannot
tell a stack you stopped on purpose from a host that has died — so it would bring it straight
back up, and run a database migration while it was at it.

While a hold is in place:

- `reconcile` reports the environment as held and changes nothing. The timer keeps running and
  keeps doing nothing, which is the point.
- `doctor` reports the hold on **every** run.

**A hold survives a reboot.** That is on purpose — a machine that reboots in the middle of your
maintenance window should stay down, not come back up half-configured. The consequence is that
a hold nobody clears will suspend deployments indefinitely, with nothing to expire it. This is
why `doctor` mentions it every single time:

```
WARN maintenance hold  held 2026-08-19 14:02:11Z — adding a port mapping.
                       This host will not converge until `cairn-adopt start`.
```

Two ways out: `cairn-adopt start`, or `cairn-adopt restart` — which clears a hold if it finds
one and tells you it did, so you can't resume a host somebody else stopped without noticing.
`restart` never leaves an environment held, even if it fails partway.

## Worked example: changing the compose file

The compose file is yours to edit — cairn writes it once and never regenerates it. Say you want
to publish MariaDB on the host's loopback so you can reach it through an SSH tunnel:

```bash
cairn-adopt stop --reason "publishing 3306 on loopback"
```

Edit the `db` service in `/etc/cairn/compose.yaml`:

```yaml
    ports:
      - "127.0.0.1:3306:3306"
```

!!! danger "Bind to loopback, not to everything"
    Write `"127.0.0.1:3306:3306"`, not `"3306:3306"`. The second form publishes your database
    to the open internet, and Docker writes its own firewall rules — `ufw` will not stop it.
    With the loopback prefix the port is reachable only from the host itself, and therefore
    only through SSH.

Then bring it back:

```bash
cairn-adopt start
```

`start` recreates any container whose configuration changed, so the new port mapping takes
effect. `cairn-adopt restart` would have done the same in one step, without holding it in
between — use `stop`/`start` when you want the environment to stay down while you work.

## Reclaiming disk

Every image this host has ever run stays in local storage after the stack moves on to a newer
one. That's deliberate — it's what makes a rollback a tag change rather than a download — but
left alone it grows without bound, and an ERPNext image is not small.

```bash
cairn-adopt prune --dry-run
```

```
Will remove 2 image(s) this host previously ran:
  7b3c1d9e0a42     1.4 GB  input hash a1b2c3d4e5f6  registry.acmecorp.net/erpnext-v16:v16-a1b2c3d4e5f6
  2f88ba60c715     1.4 GB  input hash 4d5e6f708192  registry.acmecorp.net/erpnext-v16:v16-4d5e6f708192
Reclaims 2.8 GB.

Keeping 1 image(s) for rollback headroom.
Currently running: d47f139c6ffe. Never removed.
3 other image(s) in local storage are not cairn-adopt's and are not listed — including
anything `cairn-build` produced here itself.
```

Drop `--dry-run` to be asked for confirmation, which defaults to **no**; add `--yes` to skip
the prompt when running unattended. If an individual image can't be removed, cairn says so and
carries on with the rest rather than abandoning the run.

### What it will not remove

- **The image the stack is currently running.** This is read from the running container, not
  guessed from which image is newest — the distinction matters after a rollback, where the
  running image is deliberately *older* than one that superseded it. `--keep` does not override
  this.
- **Volumes and containers.** `prune` removes images and nothing else. Your database and sites
  volume are not reachable from this command.
- **Images `cairn-build` made on this host.** On a machine that both builds and runs, the two
  roles share one local image store, and each cleans up only its own. They're counted in the
  summary so the omission is visible, not itemized.

### Choosing `--keep`

`--keep` is how many superseded images to retain beyond the running one, and it defaults to
**1**.

Treat that as a grace window, not a rollback guarantee. It buys you the immediately-previous
image — enough to reverse a deploy you regret within minutes of making it, without waiting on a
pull. It is not an archive, and it is not the mechanism you should rely on to reach a specific
older release: a registry that still holds the tag is. Raise it if the target has disk to spare
and you want more headroom; there is no reason to lower it.

!!! note "Why the builder's prune won't do this for you"
    `cairn-build prune` deliberately leaves these images alone. Once an image has been pushed,
    the builder has no way to know whether something on the host is still running it — so it
    refuses to guess. `cairn-adopt prune` is the side that *can* know, because it reads the
    running container. On a host with both roles, run both.

*Verified against a live target: `doctor`, `logs`, `shell`, `console`, `mariadb`, and
`restart`. Not yet exercised in the field: the held state itself — `stop` placing a hold,
`doctor` warning about one, `restart` clearing a hold that genuinely exists, and a hold
surviving a reboot — along with `prune`. Treat those as documented-but-unproven, and check
back for a note once they have been run.*
