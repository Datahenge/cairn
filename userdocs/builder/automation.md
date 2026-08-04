# Build Automation

Repeats the manual build → push → point-the-environment sequence from [Builder](index.md) on
a schedule, unattended — no GitHub Actions, no webhook, and no reliance on how a merge
happened. Do this only after that sequence has worked by hand at least once for a given
manifest — a timer that fires before a manifest is confirmed working turns one wrong
configuration into a wrong deploy every few minutes.

## Install the timer

```bash
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn_production.toml
```

No `--environment` flag — the manifest declares at most one (see [the manifest
reference](../reference/manifest.md#environments)), so the timer reads it from the file
instead of asking a second time. `--build-interval` controls the cadence (default `15min`).
This installs and **enables** the timer but does not **start** it — cairn prints exactly this
after it runs:

```
cairn-build-production.timer is enabled but NOT started — run the first build by hand first,
then `systemctl start cairn-build-production.timer`
```

The unit name is derived from the environment (`cairn-build-<environment>`), so installing a
timer for a second manifest — `cairn-build setup-timer --manifest
/srv/cairn/acmecorp/cairn_staging.toml` — writes a separate, independently-managed unit rather
than colliding with the first. Nothing further is required before starting either one, even
for an environment you've never used before — see below.

## What it actually runs

`setup-timer` writes a small script and a systemd service + timer that runs it. The script
does two things, in order:

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn_production.toml --push --assign-tag --yes
cairn-build prune --keep 1 --yes
```

`build --push` is already an idempotent change detector: with no new commits, it resolves
refs, sees the input hash is already built — locally, or, absent a local copy, in the registry
itself — and exits without building or pushing again, so the timer firing every 15 minutes
costs almost nothing when there's nothing new. `--assign-tag` folds the pointer move into the
same call: whatever image resulted (freshly built, or already there), it points this
manifest's own environment at it, creating the pointer the first time and moving it every time
after — there's no separate manual step to run before starting the timer, even the first time.
`prune` then removes anything the build just superseded on this machine's own local disk, so
the timer also keeps disk use bounded without a second, separate job.

## A worked example: three environments, no GitHub Actions

Say you want `test`, `staging`, and `production`, each tracking its own git branch, each
converging within minutes of a push — with no SSH, no manual CLI, and no dependency on
GitHub's merge semantics. Three manifests, three timers, on one build machine:

```bash
sudo cairn-build setup --client acmecorp --environment test
sudo cairn-build setup --client acmecorp --environment staging
sudo cairn-build setup --client acmecorp --environment production
```

Edit each scaffolded manifest so its apps' `ref` tracks that environment's own branch (e.g.
`cairn_test.toml` pins to `test`, `cairn_staging.toml` to `staging`) — see [ref
resolution](../reference/manifest.md#cairnfrappe) for why a branch, not a tag, is what makes
this auto-track without editing the manifest. Then install all three timers:

```bash
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn_test.toml
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn_staging.toml
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn_production.toml
sudo systemctl start cairn-build-test.timer cairn-build-staging.timer cairn-build-production.timer
```

From here, `git push` to any of those branches is the whole workflow — the corresponding
timer notices within its poll interval, builds, and points that environment at the result.
Nothing needs to know about the other two.

**Promotion is proof, not a command.** If `staging`'s branch is fast-forwarded to a commit
`production`'s branch is later reset to as well, `production`'s own timer resolves that same
commit set, finds `staging` already built it, and retags onto it — no rebuild, byte-for-byte
identical to what `staging` ran. Nothing asserts "this is a promotion"; it falls out of every
environment independently proving its own state against the registry. To promote by hand,
faster than waiting for the next poll, run the same command a human would:

```bash
cairn-build assign-tag --manifest /srv/cairn/acmecorp/cairn_production.toml
```

If nothing in the registry yet matches `production`'s currently-resolved refs, this reports
that and changes nothing — it never triggers a build. Rollback is the same idea: reset the
branch to an earlier commit (a git-level action, outside cairn) and either wait for the next
poll or run `assign-tag` again — if that commit's image still exists in the registry, it
retags instantly.

## Verify it's actually running

Each timer has its own unit name, so you don't need to wade through all of journald —
filtering to one unit already scopes the output to just that timer:

| Role | Unit |
| --- | --- |
| Build machine, per environment | `cairn-build-<environment>.service` / `.timer` |
| Target (`cairn-adopt reconcile`) | `cairn-reconcile.service` / `cairn-reconcile.timer` |
| Registry host | `cairn-registry-maintenance.service` / `cairn-registry-maintenance.timer` |

```bash
# Next/last trigger for every cairn timer on this host, at a glance:
systemctl list-timers --all | grep cairn

# That unit's own output, scoped — not all of journald:
journalctl -u cairn-build-production.service --since -1d
```
