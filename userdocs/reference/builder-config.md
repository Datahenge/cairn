# Machine-local build config — `builder.toml`

Where `cairn.toml` describes *what image to build*, `builder.toml` describes *how and
where this particular machine builds it* — the build engine, a default registry, where
transcripts land. Genuinely machine-local facts, never shared or committed. Named for the
**Builder** role: `build`, `push`, `images`, `prune`, `new-tag`/`retag`/`retire`, and
`doctor` read it. No target-side command (`reconcile`, `adopt`) ever touches it — a
target has its own separate descriptor, see [Target descriptor](target-descriptor.md).

It lives at `/etc/cairn/builder.toml` — a fixed, shared system path, not a per-user
`~/.config/` file. On a shared client VPS with several operator logins, a per-user file
means one operator sets their preference, logs out, and the next finds an empty config
with no explanation; `/etc/cairn/builder.toml` is one file every login reads identically.
Like the manifest, it's never discovered by searching a directory — there is no
"nearest match" lookup of any kind.

## Resolution order

Three layers, lowest precedence first — each overrides the previous **key-by-key**, not
wholesale, so setting only one override still leaves the rest in place:

1. **`/etc/cairn/builder.toml`** — the machine-wide base.
2. **The manifest's `[cairn.registry]`** — see [the manifest](manifest.md#cairnregistry).
   Committed with the deployment, since that registry is usually the client's, not this
   machine's.
3. **`CAIRN_ENGINE` / `CAIRN_REGISTRY` / `CAIRN_NAMESPACE` / `CAIRN_TRANSCRIPT_DIR`** —
   one environment variable per key, for a one-off override with nothing to create,
   gitignore, or forget.

With none of the three present, cairn builds a local, unregistered image
(`cairn/<image_name>`).

## File format

No `[cairn]` table wrapper — every key sits at the top level:

```toml
# /etc/cairn/builder.toml
engine         = "podman"
registry       = "registry.example.com"
namespace      = "your-personal-account"
transcript_dir = "/var/log/cairn/transcripts"
```

| Key | Meaning |
| --- | --- |
| `engine` | `"docker"` or `"podman"`. Auto-detected if unset — docker preferred when both are present. |
| `registry` | Registry hostname. Normally set in the manifest's `[cairn.registry]` instead — set it here only for a personal default that isn't any specific deployment's concern. |
| `namespace` | Registry account/org. Same caveat as `registry`. |
| `transcript_dir` | Where build transcripts are written, if not the default. |

Every key is optional; an unrecognized key fails at parse time, and every present value
must be a non-empty string. There's no scaffolding command for this file — most installs
never need one at all; create it by hand only if a machine default doesn't fit.

**Overriding one key without a file:** set the matching environment variable —
`CAIRN_ENGINE`, `CAIRN_REGISTRY`, `CAIRN_NAMESPACE`, or `CAIRN_TRANSCRIPT_DIR`. This is
the only per-invocation or per-session override cairn has; there is no second
`cairn.local.toml`-style file. For example, building with `podman` on a laptop with no
Docker daemon:

```bash
CAIRN_ENGINE=podman cairn-build build --manifest ./cairn.toml
```

cairn stores no credentials in either file — authenticate with `docker login` or
`podman login` before pushing.

## Private `github.com` apps

If a manifest's `[[cairn.apps]]` points at a private repository, set
`$CAIRN_GITHUB_TOKEN` when you run a build:

```bash
export CAIRN_GITHUB_TOKEN=github_pat_xxxxx
cairn-build build --manifest ./cairn.toml
```

This is deliberately **not** a `builder.toml` key — that file is machine-wide and, on a
shared box, group-*writable* by design (see below), which makes it the wrong place for a
secret. The token is read directly from the environment, used only for `github.com`
URLs, and never touches `cairn.toml`, `builder.toml`, provenance, or `--dry-run` output.

If you don't own the repository — the common case when building a client's private app
— ask the client for a **fine-grained** personal access token scoped to just that one
repository (read-only "Contents" is enough), rather than a classic, account-wide token.
A fine-grained PAT gives you the same one-repo isolation an SSH deploy key would, as a
token you can hand off directly.

## Sharing `/etc/cairn` across several operators

If more than one person administers a box — the common case for a consultancy's client
VPS — `cairn-build setup` shares `/etc/cairn` with a group by default, so editing
`builder.toml` doesn't need `sudo` every time:

```bash
sudo cairn-build setup --client acmecorp                       # creates and shares 'cairn-admins'
sudo cairn-build setup --client acmecorp --admin-group ops-team # a different group name
sudo cairn-build setup --client acmecorp --no-admin-group       # skip this; leave /etc/cairn as found
```

It creates the group if it doesn't already exist, and sets `/etc/cairn` group-owned,
group-writable, and **setgid** — so files created inside it later keep inheriting the
shared group rather than reverting to root's own. Add the operators who should be able
to edit configuration to that group (`sudo usermod -aG cairn-admins sara`) and they can
edit `/etc/cairn/builder.toml` without elevating.

`cairn-build doctor` reports the directory's current group, permissions, and whether
you're a member, but never changes any of it:

```
$ cairn-build doctor
...
OK    shared config   /etc/cairn owned by group 'cairn-admins' (setgid), group-writable, current user is a member
```
