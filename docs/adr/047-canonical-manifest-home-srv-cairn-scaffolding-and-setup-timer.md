---
status: authoritative
owner: technical
purpose: ADR-047 — Canonical manifest home `/srv/cairn/<client>/`, `setup` scaffolding, and the `setup`/`setup-timer` split
---

# ADR-047 — Canonical manifest home `/srv/cairn/<client>/`, `setup` scaffolding, and the `setup`/`setup-timer` split

**Decided:** 2026-08-03
**Amends:** `ADR-046`, `BR-CLI-021`.

Raised while writing the published Builder guide (`BR-DOCS`) against a real client VPS: the
first command suggested for "where does the manifest go" was a personal home directory,
which a future coworker or maintainer can't reach without `sudo` and doesn't discover on
their own. `README.md`'s own example (`/srv/acme/cairn.toml`) already gestured at the right
neighborhood but was never load-bearing — nothing created that path, checked it, or enforced
a convention around it.

## Decision

**Canonical location: `/srv/cairn/<client>/cairn.toml`.** Not bare `/srv/<client>/` — a host's
`/srv` may already hold unrelated application data cairn has no business assuming anything
about. `/srv/cairn/` is cairn's own namespace within `/srv`; everything under it is cairn's,
everything beside it is not cairn's concern. `<client>` keeps deployments legible on a builder
that serves more than one client — `ls /srv/cairn` names them, where a flat directory of
numbered files would not.

**`cairn-build setup` provisions it, gated by a required `--client <name>`.** It creates
`/srv/cairn/` and `/srv/cairn/<name>/` if absent, owned by the same `cairn-admins` group and
setgid bit `ADR-043` already applies to `/etc/cairn` — one shared-access discipline, reused,
not reinvented. No `--client` is a hard error: there is no default client name to fall back to
silently.

**`setup` scaffolds a starter `cairn.toml`, only if one is not already there.** If
`/srv/cairn/<name>/cairn.toml` exists, `setup` reports it present and does not touch it — the
same "never silently overwrite" discipline `BR-DEPLOY-021` already requires of every file
`setup` can write. If it does not exist, `setup` writes the existing illustrative example — the
one already published in `README.md` and `userdocs/reference/manifest.md`, `BR-BUILD-003`'s
ordered-list comment included — verbatim. One template, reused; not a second one invented for
this purpose.

This **strikes** `README.md`'s current "there's no scaffolding command either — you hand-write
the manifest" line (tracked for the wider rewrite under `W-012`, not fixed piecemeal here). The
risk that line was guarding against — cairn silently choosing or overwriting the wrong file —
does not apply to a create-only-if-absent scaffold: `setup` never reads an existing manifest to
decide behavior, and never selects one for another command to act on.

**`setup` and `setup-timer` split, on both CLIs.** `cairn-build setup` now runs `preflight`,
`admin-group`, `registry`, and the new manifest stage — not the build-automation timer. A new,
separate command, `cairn-build setup-timer`, runs only that stage. Symmetrically,
`cairn-adopt setup` drops its `timers` stage to a new `cairn-adopt setup-timer`. The stage
itself is unchanged in substance — installed enabled but **not started**, exactly as
`ADR-046`/`stage_timers_build` already documented, specifically so a first build or reconcile
gets run and watched by hand before anything is automated. What changes is discoverability:
that reasoning was previously buried behind `setup --only timers`, a flag most first-time
readers would not find before their first manual run; as its own top-level command it appears
directly in `cairn-build --help` / `cairn-adopt --help`.

**Bonus, informational only: `doctor` may report manifests found under `/srv/cairn/*/cairn.toml`.**
This is a report, not a discovery mechanism — no command ever uses this listing to choose a
manifest to act on. `BR-CLI-014`'s rule stands unchanged: every manifest-consuming command
still requires an explicit `--manifest` or `$CAIRN_MANIFEST`.

## Consequences

- `BUILD_STAGES` loses `timers` and gains a manifest-scaffolding stage; `setup-timer` becomes
  its own single-stage command rather than a value of `--only`.
- `ADOPT_STAGES` loses `timers` the same way.
- `cairn-build setup` gains a required `--client <name>` option with no default.
- `README.md` remains deliberately stale on this point, per `W-012`, until the wider rewrite
  folds it in alongside the rest of the `cairn-build`/`cairn-adopt` split.
  `userdocs/reference/manifest.md` (2026-08-04) documents `setup`'s scaffolding correctly and
  is not affected. `CONFIGURATION.md` itself was retired the same day, its content absorbed
  into `userdocs/reference/`.

*(BR-CLI-021, BR-CLI-022, BR-CLI-023, BR-DEPLOY-021, BR-BUILD-003, BR-CLI-014, ADR-043,
ADR-046)*
