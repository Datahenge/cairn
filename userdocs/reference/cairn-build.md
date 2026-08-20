# `cairn-build` — command surface

Every `cairn-build` command. For what the builder role does and why you'd want it, see
[Builder](../builder/index.md) — this page is just the command surface.

Most commands need a manifest. `--manifest <path>` names it explicitly; without the flag,
cairn reads `$CAIRN_MANIFEST`. There is no "nearest `cairn.toml`" search of the current
directory — a manifest is always named, never discovered. Machine-local settings (build
engine, default registry, transcript location) come from
[`builder.toml`](builder-config.md) instead, and are never passed as flags.

## build

```bash
cairn-build build --manifest /srv/cairn/acmecorp/cairn_production.toml
cairn-build build --push --yes
```

Resolves every ref in the manifest to a commit, hashes those inputs, and builds the image if
that exact combination hasn't been built already. Build-only by default.

Flags:

- `--manifest <path>` — the manifest to build. Default: `$CAIRN_MANIFEST`.
- `--push` — also upload the result to the configured registry.
- `--assign-tag` / `--no-assign-tag` — also point this manifest's declared environment at the
  pushed image. On by default whenever `--push` is given and the manifest declares an
  environment; `--no-assign-tag` opts out.
- `--yes` — don't ask for confirmation before moving that pointer.
- `--dry-run` — show what would be built, build nothing.
- `--rebuild` — build again even if these exact inputs were already built. Distinct from
  `--no-cache`: this overrides cairn's own "already built this" short-circuit.
- `--no-cache` — ignore the engine's layer cache. Rarely needed.
- `--no-cache-tag` — leave the reusable build layers unnamed in the engine's image list.
- `--transcript <path>` / `--no-transcript` — write the build output to a file as well as the
  terminal, or suppress the file entirely.

## images

```bash
cairn-build images
cairn-build images --json
```

What this build machine holds, and what each image was built from. **Local only** — it reads
no registry. To ask the same question of a registry, this machine's own or a client's remote
one, use `cairn-registry images` ([Registry CLI](../registry/cli.md#images)).

Flags: `--json` for machine-readable output.

## prune

```bash
cairn-build prune --dry-run
cairn-build prune --keep 2 --yes
```

Removes superseded images **this machine built**. Only untagged images are candidates, and
the newest of each set of build inputs is kept.

Flags:

- `--keep <n>` — images to keep per set of build inputs. Default `1`, minimum `1`.
- `--dry-run` — show what would be removed, remove nothing.
- `--yes` — don't ask for confirmation.
- `--manifest <path>` — default `$CAIRN_MANIFEST`.

This deliberately leaves alone any image a target on the same host is running or has run —
reclaiming those is [`cairn-adopt prune`](cairn-adopt.md#prune)'s job, because it's the side
that can read the running container. On a machine with both roles, run both.

## push

```bash
cairn-build push
cairn-build push --id acmecorp/erpnext-v16:v16-a1b2c3d4e5f6
```

Uploads an already-built image. Requires `docker login` or `podman login` to the target
registry first — **cairn stores no credentials of its own** and never writes one to disk.

Flags:

- `--id <tag>` — push this tag instead of the current manifest's tags.
- `--manifest <path>` — default `$CAIRN_MANIFEST`.

## assign-tag

```bash
cairn-build assign-tag --dry-run
cairn-build assign-tag --yes
```

Points this manifest's declared environment at a matching image **already in the registry**,
if one exists. Never builds, and never uploads. This is the pointer move a target polls for.

Flags: `--manifest <path>`, `--dry-run`, `--yes`.

## retire

```bash
cairn-build retire --manifest /srv/cairn/acmecorp/cairn_test.toml
```

Decommissions this manifest's environment from cairn. Touches no image and no registry tag —
the images stay where they are, and so does anything currently running from them.

Flags: `--manifest <path>`.

## doctor

```bash
cairn-build doctor
cairn-build doctor --all
```

Checks that this machine can build: container engine, `git`, build inputs, config, disk, and
memory. Safe to run anywhere, any time; it changes nothing.

Flags:

- `--manifest <path>` — default `$CAIRN_MANIFEST`.
- `--all` — report build-timer status for every manifest under `/srv/cairn/`, not just the
  one named. Without either, the timer check names itself as skipped rather than passing
  silently.

## setup

```bash
sudo cairn-build setup --client acmecorp --environment production --dry-run
sudo cairn-build setup --client acmecorp --environment production
```

Provisions this machine to build: the client's home under `/srv/cairn/<client>/`, a
scaffolded manifest, and shared config under `/etc/cairn`. Must be run with `sudo`.
Idempotent — safe to re-run.

Flags:

- `--client <name>` *(required)* — provisions `/srv/cairn/<name>/`.
- `--environment <name>` *(required)* — scaffolds `cairn_<name>.toml`.
- `--dry-run` — print every action, change nothing.
- `--force` — replace existing files; the old ones are kept alongside.
- `--only <stage>` — run one stage: `preflight`, `admin-group`, or `manifest`.
- `--workdir <path>` — directory to record in reported paths.
- `--skip-disk-free` — proceed even if free disk is below the minimum.
- `--admin-group <name>` / `--no-admin-group` — the group `/etc/cairn` is shared with
  (default `cairn-admins`), or leave its ownership as found.

## setup-timer

```bash
sudo cairn-build setup-timer --manifest /srv/cairn/acmecorp/cairn_production.toml
```

Installs — but does **not** start — the build-automation timer for one manifest. Must be run
with `sudo`. Starting it is a deliberate second step; see [Build
Automation](../builder/automation.md).

Flags:

- `--manifest <path>` *(required)* — the manifest this timer advances.
- `--build-interval <span>` — how often to poll, as a systemd time span. Default `15min`.
- `--dry-run`, `--force` — as for `setup`.
