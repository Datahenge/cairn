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

[cairn.environments]
production = "production"
staging    = "staging"
```

`cairn-build setup` scaffolds exactly this template — see [Builder](../builder/index.md).
Only `image_name`, `[cairn.frappe]`, and at least one `[[cairn.apps]]` entry are
required; everything else is optional and falls back to the defaults described below.

## `[cairn]`

| Key | Required | Meaning |
| --- | --- | --- |
| `image_name` | yes | The image's name. Lowercase letters, digits, and `-`/`_`/`.` separators only — it becomes an OCI repository path component, and those are lowercase-only. |
| `series` | no | The human-readable half of the image tag, e.g. `"v16"`, yielding tags like `v16-1b019793dc20`. No hyphens — the tag reads as `<series>-<hash>`, split on the last hyphen. Absent, the series is derived from the declared Frappe `ref` instead (`version-16` → `v16`). It's a **label, not a build input**: changing it later renames future images without invalidating or orphaning existing ones. |

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

## `[cairn.environments]`

Optional, and **not a build input at all** — no environment name ever reaches the
image. It's the control-side declared list of which environments exist: a table mapping
environment name → registry tag, e.g. `production = "production"`. It's what
`cairn-build`'s pointer commands (`new-tag`, `retag`, `retire`) check against — you can
only move a pointer for an environment named here — and it's the half of the deploy
model that `cairn-adopt reconcile` matches against a target's own descriptor, by tag
name.

Two environments may not point at the same tag: the tag *is* the pointer, so sharing one
would make retagging either one silently redeploy both. Absent or empty, **no
environment exists** — the pointer commands report that rather than creating one on your
behalf.

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

There's no `cairn init`. Either let `cairn-build setup --client <name>` scaffold the
starter template above into a fresh `/srv/cairn/<name>/cairn.toml` (see
[Builder](../builder/index.md)), or hand-write one starting from that same template.
Every table except `[cairn.build]` rejects unknown keys, so a typo fails at parse time
naming the bad key, rather than quietly producing the wrong image.
