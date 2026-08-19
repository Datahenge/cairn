# Operating the Stack

Once a target is under cairn's management, `cairn-adopt` gives you verbs for the everyday work
— looking at logs, opening a console, taking the stack down for maintenance — so you never need
to reach for `docker compose` yourself.

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

*These commands are written ahead of a live run against a real target — check back for a note
once they have been verified in the field.*
