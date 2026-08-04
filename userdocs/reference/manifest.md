# The manifest — `cairn.toml`

One file declares one image: the Frappe source, the ordered list of apps, and build
knobs. It's meant to be committed and shared — it carries no machine-specific settings,
and no environment name reaches it. Every command that reads a manifest names it
explicitly (`--manifest <path>`, or `$CAIRN_MANIFEST`); cairn never searches a directory
for one.

```toml
[cairn]
image_name = "erpnext-v16"
series = "v16"                      # the readable half of the image tag
environment = "production"          # this manifest's declared environment — optional,
                                     # and at most one per manifest

[cairn.frappe]
url = "https://github.com/frappe/frappe"
ref = "v16.25.0"                    # a tag: reproducible. A branch (e.g. "version-16")
                                     # always builds its latest commit instead — cairn warns
                                     # when one is used, but it stays supported on purpose.

# Order matters: apps install in this order, and cairn never reorders or resolves
# dependencies for you. List every app after the apps it depends on.
[[cairn.apps]]
name = "erpnext"
url = "https://github.com/frappe/erpnext"
ref = "v16.26.1"

# Uncomment and edit to add another app, after the apps it depends on:
# [[cairn.apps]]
# name = "your_custom_app"
# url = "https://github.com/your-org/your_custom_app"
# ref = "v1.2.3"

[cairn.build]
python_version = "3.14.2"
node_version = "24.13.0"
install_chromium = true
```

`cairn-build setup --client <name> --environment <name>` scaffolds exactly this template
— see [Builder](../builder/index.md). Only `image_name`, `[cairn.frappe]`, and at least
one `[[cairn.apps]]` entry are required; everything else is optional and falls back to
the defaults described below.

## `[cairn]`

| Key | Required | Meaning |
| --- | --- | --- |
| `image_name` | yes | The image's name. Lowercase letters, digits, and `-`/`_`/`.` separators only — it becomes an OCI repository path component, and those are lowercase-only. |
| `series` | no | The human-readable half of the image tag, e.g. `"v16"`, yielding tags like `v16-1b019793dc20`. No hyphens — the tag reads as `<series>-<hash>`, split on the last hyphen. Absent, the series is derived from the declared Frappe `ref` instead (`version-16` → `v16`). It's a **label, not a build input**: changing it later renames future images without invalidating or orphaning existing ones. |
| `environment` | no | This manifest's declared environment — see [Environments](#environments) below. A manifest declares **at most one**. |

## `[cairn.frappe]`

Frappe's own source — supplied to the build as `FRAPPE_PATH`/`FRAPPE_BRANCH`, never
through the app list.

| Key | Required | Meaning |
| --- | --- | --- |
| `url` | yes | Git URL to clone. |
| `ref` | yes | Branch or tag — not a commit SHA. A 40-character hex string is rejected outright: cairn resolves refs to commits itself and records the result, so pinning a literal commit here would bypass that and go stale silently. **Tags are reproducible** — the same tag always resolves to the same commit, which is why the scaffolded template pins to one. **A branch (e.g. `version-16`) is a moving pointer** — cairn resolves it fresh at every build, so it's a legitimate way to always pick up the newest release without editing the manifest; the tradeoff is that two builds from the same manifest, days apart, can produce different images. cairn warns rather than refuses when a manifest pins to a branch, since that may be exactly what you want. |

## `[[cairn.apps]]`

One entry per app, **in install order** — cairn never reorders or resolves
dependencies, so an app must be listed after every app it depends on. Each entry needs
`name`, `url`, and `ref` (same commit-SHA restriction as Frappe's `ref`, above). A name
listed twice is rejected — the list is an ordered install sequence, and a repeat would
make "install order" ambiguous.

An empty list is technically valid — nothing stops a Frappe-only image — but ERPNext is
almost never omitted in practice.

**Private repositories:** if an app's `url` points at a private `github.com` repo, set
`$CAIRN_GITHUB_TOKEN` when you build — see [builder.toml](builder-config.md#private-githubcom-apps).
The manifest itself never carries a credential.

## `[cairn.build]`

Optional. Three knobs are recognized by name and type-checked:

| Key | Type | Meaning |
| --- | --- | --- |
| `python_version` | string | The base image's Python version. |
| `node_version` | string | Node version installed via `nvm`. |
| `install_chromium` | boolean | Whether `chromium-headless-shell` is installed. Frappe's PDF/print/report generation shells out to it — turning this off shrinks the image but breaks anything that needs headless rendering. |

Any other key in this table is passed through **unchecked**, uppercased, as a
Containerfile build-arg — `debian_base = "bookworm"` becomes `DEBIAN_BASE=bookworm`, for
example. It only has an effect if a matching `ARG` exists in the underlying
Containerfile; there's no validation that it does. This is the deliberate long-tail
escape hatch for the rare knob not worth naming explicitly above.

Every knob left unset falls back to the Containerfile's own `ARG` default, which is what
actually gets recorded as the build's effective, provenance-bearing input — not a value
cairn invents.

## Environments

`[cairn] environment` is optional, and **not a build input at all** — declaring it doesn't
build, push, or point anything; no environment name ever reaches the image, and nothing
happens to the registry until you separately run `assign-tag`. It names this manifest's
**one** environment — its value **is** the registry tag a target watches, e.g.
`environment = "production"` means the environment's tag in the registry is `production`.
It's what `cairn-build assign-tag`/`retire` act on, and it's the half of the deploy model
that `cairn-adopt reconcile` matches against a target's own descriptor, by tag name.

**A manifest declares at most one environment.** If you have `test`, `staging`, and
`production`, that's three manifests — `cairn_test.toml`, `cairn_staging.toml`,
`cairn_production.toml` — each with its own `environment` line, typically each pinned to
its own git branch. `cairn-build setup --client <name> --environment <name>` scaffolds
one at a time. Absent, this manifest declares no environment — `assign-tag`/`retire`
report that rather than inventing one.

**Why one-per-manifest, and why this exists at all — build once, promote by proof.** An
image is deliberately environment-agnostic: the same artifact can run under `test`, then
`staging`, then `production`, without ever being rebuilt. What moves between environments
is only a registry tag. `assign-tag` never takes another environment's word for it,
though — it always resolves *this* manifest's own refs, right now, and only points the
tag at an image if the registry already holds one matching exactly that resolution. If
`test` and `staging` happen to declare the same refs at some moment (because, say, a
release branch was fast-forwarded), `staging`'s own `assign-tag` finds the image `test`
already built and points at it — proven by the registry, never asserted by a flag.
`production` always requires deliberate confirmation before its pointer changes, whether
that's the first time it's pointed at anything or the fiftieth.

A worked example — three manifests, one client:

```toml
# cairn_test.toml — tracks the `test` branch
[cairn]
image_name  = "erpnext-v16"
environment = "test"

[cairn.frappe]
url = "https://github.com/frappe/frappe"
ref = "v16.25.0"

[[cairn.apps]]
name = "your_custom_app"
url  = "https://github.com/your-org/your_custom_app"
ref  = "test"                       # a branch: resolved fresh on every poll
```

```bash
# Each manifest's own build+retag, typically run on a timer (see Build Automation):
cairn-build build --manifest cairn_test.toml --push --assign-tag --yes
cairn-build build --manifest cairn_staging.toml --push --assign-tag --yes
cairn-build build --manifest cairn_production.toml --push --assign-tag --yes

# Rolled staging's branch back to an earlier commit and want production caught up faster
# than waiting for its own next poll — no --from, just ask again:
cairn-build assign-tag --manifest cairn_production.toml
```

Every step above only resolves refs and, if proven, moves a tag in the registry —
`cairn-adopt reconcile` on the actual target is what notices the pointer moved and
converges to it on its next poll. See [Build Automation](../builder/automation.md) for
the full unattended version of this, with no manual command at all.

## `[cairn.registry]`

Optional. Where this deployment's images belong, once you've chosen a registry:

```toml
[cairn.registry]
host      = "registry.example.com"
namespace = "acmecorp"
```

`host` is required if the table is present; `namespace` is optional. cairn has no
opinion on *which* registry — see
[About container registries](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md)
and [About GHCR](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_GHCR.md)
for how to choose one and what it costs. Absent this table, images stay local
(`cairn/<image_name>`) — nothing is inferred on your behalf. This table is read as part
of [build config](builder-config.md), layered under any `CAIRN_REGISTRY`/`CAIRN_NAMESPACE`
override.

## Creating one

There's no `cairn init`. Either let `cairn-build setup --client <name> --environment
<name>` scaffold the starter template above into a fresh
`/srv/cairn/<client>/cairn_<environment>.toml` (see [Builder](../builder/index.md)), or
hand-write one starting from that same template. Every table except `[cairn.build]`
rejects unknown keys, so a typo fails at parse time naming the bad key, rather than
quietly producing the wrong image.
