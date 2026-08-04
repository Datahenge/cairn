---
status: authoritative
owner: technical
purpose: Full reference for cairn's manifest and build-config files.
---

# Configuring cairn

cairn reads two kinds of file, kept deliberately apart: the **manifest** (what image to
build — shared, committed) and **build config** (how and where this machine builds it —
local, never shared). Neither is ever discovered by searching a directory — every
invocation says explicitly which manifest it means, and build config's machine-wide layer
lives at one fixed, shared system path rather than a per-user one. See
[README.md](README.md) for the quickstart version of this; this document is the full
reference.

## The manifest — `cairn.toml`

One file declares one image: the Frappe source, the ordered list of apps, and build
knobs. It's meant to be committed and shared — it carries no machine-specific settings.
It *may* also carry the deployment's registry coordinates, in an optional
`[cairn.registry]` table (see below), because those describe the deployment rather than
the machine building it.

```toml
[cairn]
image_name = "erpnext-btu-v16"
series = "v16"                      # the readable half of the image tag

[cairn.frappe]
url = "https://github.com/frappe/frappe"
ref = "version-16"

# Order matters: apps install in this order, and cairn never reorders or resolves
# dependencies for you. List every app after the apps it depends on.
[[cairn.apps]]
name = "erpnext"
url = "https://github.com/frappe/erpnext"
ref = "version-16"

[[cairn.apps]]
name = "your_custom_app"
url = "https://github.com/your-org/your_custom_app"
ref = "version-16"

[cairn.build]
python_version = "3.14.2"
node_version = "24.13.0"
install_chromium = true

[cairn.environments]
production = "production"
staging    = "staging"
```

**Locating it: no discovery, ever.** Every command that reads a manifest names it one of
two ways — there is no third, implicit option:

1. `--manifest <path>` — wins if given.
2. `$CAIRN_MANIFEST` — read otherwise.

Neither given is an error naming both. cairn deliberately never walks the working
directory or any ancestor of it looking for a `cairn.toml` — on a shared machine, or in a
container, "the nearest match" is a silent way to act on the wrong deployment, not a
convenience. In practice this costs little: a systemd unit or CI job sets `$CAIRN_MANIFEST`
once, in its own config, and never touches it again; interactively, `export
CAIRN_MANIFEST=/srv/acme/cairn.toml` once per shell session (or a per-client shell alias)
covers it.

**Creating one.** There's no `cairn init` — you hand-write `cairn.toml`, starting from
the example above and adjusting `image_name`, `frappe`, and `cairn.apps` for your
deployment. Every table except `[cairn.build]` rejects unknown keys, so a typo fails at
parse time naming the bad key rather than producing a subtly wrong image an hour later.

Only `image_name`, `[cairn.frappe]` (`url`, `ref`), and `[[cairn.apps]]` are required.
`series`, `[cairn.registry]`, `[cairn.build]`, and `[cairn.environments]` are all
optional — absent, the documented defaults apply (images stay local; apps build with
their upstream default `Dockerfile` build-args).

**Publishing to a registry.** Add `[cairn.registry]` — a required `host` and an optional
`namespace` — once you've chosen where this deployment's images belong:

```toml
[cairn.registry]
host      = "registry.example.com"
namespace = "acme-corp"
```

cairn has no opinion on *which* registry, and no example here should read as a
recommendation — see [ABOUT_REGISTRIES.md](ABOUT_REGISTRIES.md) for how to choose one for
client work, and why that choice isn't neutral. Absent `[cairn.registry]`, the image
stays local (`cairn/<image_name>`); nothing infers a registry on your behalf.

## Machine-local build config — `/etc/cairn/builder.toml`

Named for the **Builder** role (the same Builder/Target split the README's install
section describes), because that's exactly what reads it: `build`, `push`, `images`,
`prune`, `new-tag`/`retag`/`retire`, and `doctor`. No target-side command
(`reconcile`, `adopt`, `systemd-units`) ever touches it — a target has its own separate
descriptor (below).

It lives under `/etc/cairn`, not a personal home directory — deliberately. A per-user
`~/.config/cairn/` file works fine on a laptop one person alone operates, and badly on a
shared client VPS with several separate logins (a common shape for a consultancy's client
box): one operator sets their engine preference, logs out, and the next operator to log in
finds an empty config with no visible explanation. `/etc/cairn/builder.toml` is instead
one file every login on the host reads identically. Who may *write* it is left entirely to
ordinary filesystem permissions — cairn assumes nothing about ownership. `cairn-provision`
can share the directory with a group by default (see below) so that doesn't mean "root
only edits it," but that's a provisioning choice, not something cairn itself requires.

Which build engine to use, where to push (absent an explicit manifest registry), and
where transcripts land — genuinely machine-local facts, not properties of the
deployment — resolve in three layers, lowest precedence first:

1. `/etc/cairn/builder.toml` — the machine-wide base, shared by every login on the host.
2. the manifest's `[cairn.registry]` — where *this deployment's* images belong.
3. `CAIRN_ENGINE` / `CAIRN_REGISTRY` / `CAIRN_NAMESPACE` / `CAIRN_IMAGE_BASE` /
   `CAIRN_TRANSCRIPT_DIR` — the deliberate override, one environment variable per key.

Each layer overrides the previous **key-by-key**, not wholesale — setting only
`CAIRN_NAMESPACE` still keeps the engine from layer 1 and the host from layer 2. All
three are optional; with none present, cairn builds a local, unregistered image
(`cairn/<image_name>`).

**Creating `/etc/cairn/builder.toml`.** There's no scaffolding command for this
either — it's a plain file you create by hand only if a machine default doesn't fit.
Most installs never need one at all. Unlike `cairn.toml`, it has **no `[cairn]` table
wrapper** — every recognized key sits at the file's top level:

```toml
# /etc/cairn/builder.toml
engine         = "podman"
registry       = "registry.example.com"
namespace      = "your-personal-account"
transcript_dir = "/var/log/cairn/transcripts"
```

Every key is optional and every value is a non-empty string; an unrecognized key fails
at parse time. What each does:

| Key | Meaning |
| --- | --- |
| `engine` | `"docker"` or `"podman"`. Auto-detected if unset — docker preferred when both are present. |
| `registry` | Registry hostname. Normally set in the manifest instead (see below) — set it here only for a personal default that isn't a specific deployment's concern. |
| `namespace` | Registry account/org. Same caveat as `registry`. |
| `transcript_dir` | Where build transcripts are written, if not the default. |

**Overriding one key without a file at all:** set the matching environment variable —
`CAIRN_ENGINE`, `CAIRN_REGISTRY`, `CAIRN_NAMESPACE`, or
`CAIRN_TRANSCRIPT_DIR`. This is the *only* per-invocation or per-session override cairn
has; there is no `cairn.local.toml` or equivalent second file — once every invocation
already carries an explicit manifest reference, a stray env var covers the same need
(e.g. building with `podman` on a laptop with no Docker daemon: `CAIRN_ENGINE=podman
cairn build --manifest ./cairn.toml`) with no file to create, gitignore, or forget beside
the manifest.

**Can `builder.toml` itself be overridden by a directory search?** No, and this is
deliberate: it is meant to be genuinely machine-wide, not per-directory, so there is no
"nearest match" lookup of any kind for it — only the three explicit layers above.

**Why `registry`/`namespace` usually belong in the manifest, not here:** a client's
image should be reproducible and publishable without your personal machine's config
existing at all. See [ABOUT_REGISTRIES.md](ABOUT_REGISTRIES.md) for the reasoning, and
[ABOUT_GHCR.md](ABOUT_GHCR.md) for GitHub's registry specifically. Set them in build
config only for a genuinely personal/experimental image that isn't a deployment yet.

cairn stores no credentials, in either file — authenticate with `docker login` or
`podman login` before pushing.

## Private `github.com` apps

If a manifest's `[[cairn.apps]]` points at a private repository on `github.com`, set
`$CAIRN_GITHUB_TOKEN` when you run `cairn build` (or `reconcile`, if a target ever resolves
refs itself):

```
export CAIRN_GITHUB_TOKEN=github_pat_xxxxx
cairn build --manifest ./cairn.toml
```

This is deliberately **not** a `builder.toml` key — that file is machine-wide and, on a shared
box, group-*writable* by design (see below), which makes it the wrong place for a secret.
`$CAIRN_GITHUB_TOKEN` is read directly, used only for `github.com` URLs, and never touches
`cairn.toml`, `builder.toml`, provenance, or `--dry-run` output.

If you don't own the repository — the common case building a client's private app — ask the
client to create a **fine-grained** personal access token scoped to just that one repository
(read-only "Contents" is enough) rather than a classic, account-wide token. A fine-grained PAT
gives you the same one-repo isolation an SSH deploy key would, as a token you can hand off
directly; a classic PAT is broader than this needs and shouldn't be used for it.

## Sharing `/etc/cairn` across several operators

If more than one person administers a box — the common case for a consultancy's client
VPS — `cairn-provision` shares `/etc/cairn` with a group by default, so editing
`builder.toml` doesn't require `sudo` every time:

```
sudo cairn-provision --role builder                       # creates and shares 'cairn-admins'
sudo cairn-provision --role builder --admin-group ops-team # a different group name
sudo cairn-provision --role builder --no-admin-group       # skip this; leave /etc/cairn as found
```

It creates the group if it doesn't already exist, and sets `/etc/cairn` group-owned,
group-writable, and **setgid** — so files created inside it later (by a re-run, or by
root writing the target descriptor) keep inheriting the shared group rather than reverting
to root's own. Add the operators who should be able to edit configuration to that group
(`sudo usermod -aG cairn-admins sara`) and they can edit `/etc/cairn/builder.toml` without
elevating.

`cairn` itself never creates or changes this group — only `cairn-provision` does, matching
the rule that cairn prints host configuration while the installer is the one thing allowed
to change it. `cairn doctor` reports the directory's current group, permissions, and
whether you're a member, but never changes any of it:

```
$ cairn doctor
...
OK    shared config   /etc/cairn owned by group 'cairn-admins' (setgid), group-writable, current user is a member
```

## The target's descriptor — `/etc/cairn/environment.toml`

A target doesn't hand-author configuration either. Run `cairn adopt` against its running
`frappe_docker` stack, review the descriptor it prints, and install it yourself at
`/etc/cairn/environment.toml`. That descriptor — not the manifest, not build config — is
what `cairn reconcile` reads, and its presence is what marks a machine as a target at
all.
