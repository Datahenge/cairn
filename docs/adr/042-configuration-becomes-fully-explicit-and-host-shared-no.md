---
status: authoritative
owner: technical
purpose: ADR-042 — Configuration becomes fully explicit and host-shared: no directory search, no home directories, no local-override file
---

# ADR-042 — Configuration becomes fully explicit and host-shared: no directory search, no home directories, no local-override file

**Decided:** 2026-07-26

Prompted by a future Brian named explicitly: cairn running containerized, where a "working
directory" is meaningless or arbitrary. But the sharper, present-tense problem he raised is a
**multi-user VPS** — most of his clients' actual boxes, where several human operators (his own
running example: Brian, Sara, Jim) hold separate Linux logins with different permissions to the
same one deployment.

Two mechanisms this project already had turned out to be wrong for that shape of host:

1. **Manifest discovery walked up from the working directory** (`ADR-029`). Brian's objection:
   it "assumes a generic filename I don't like," and more importantly, "the outcome can silently
   drift too easily" — cd into the wrong directory, or a nested checkout with its own stray
   `cairn.toml`, and the wrong deployment is silently the one acted on.
2. **Machine build config lived under `~/.config/`** (`ADR-041`, at the time still per-user).
   XDG's per-user model is right for a single-operator laptop and actively wrong for a shared
   ops box: Brian sets his engine preference, logs out; Sara logs in tomorrow to an empty config
   and no visible reason why. Invisible-until-it-bites is worse than not having the feature.

**Decision, in three parts:**

1. **Manifest resolution drops the directory search entirely.** `--manifest <path>` or
   `$CAIRN_MANIFEST` — nothing else, no fallback default path of any kind. This reverses
   `BR-CFG-012`'s former "the common case MUST require no flags" clause, confirmed explicitly
   with Brian rather than walked back quietly. The underlying reasoning is the same one already
   governing registry defaults: `BR-CFG-013` forbids cairn from inferring a registry/namespace
   from anything — the machine, the git remote, the operator's other deployments. Silent
   directory-walking is the identical failure mode (guessing at *which deployment*, an even
   larger thing to get silently wrong than *which registry*) and there is no principled place to
   keep one implicit fallback while forbidding all the others. Systemd units and CI jobs set
   `$CAIRN_MANIFEST` once in their own config and never touch it again; interactive use is one
   `export` per session or a per-client shell alias — the same shape kubectl (`$KUBECONFIG`) and
   the AWS CLI (`$AWS_PROFILE`) already ask of their users for the identical reason.
2. **`builder.toml` moves to `/etc/cairn/builder.toml`.** No `$XDG_CONFIG_HOME`, no home
   directory, no per-user tier at all. One file, shared identically by every login on the box —
   the same fix, for the same reason, `/etc/cairn/environment.toml` (the target descriptor)
   already had by construction. Everything machine-scoped-but-not-tied-to-one-checkout now lives
   under `/etc/cairn/`, without exception. Who may *write* it is deliberately left to ordinary
   Unix permissions — cairn assumes nothing about ownership; an admin is free to `chown` it to a
   shared group (`ADR-043`) or leave it root-only.
3. **`cairn.local.toml` is removed outright**, not merely relocated. Its only job — a personal,
   no-root, per-checkout override — is fully covered once every invocation already carries an
   explicit manifest reference: the same environment-variable mechanism extends trivially to the
   build-config keys themselves. One `CAIRN_<KEY>` variable per `BUILD_CONFIG_KEYS` entry
   (`CAIRN_ENGINE`, `CAIRN_REGISTRY`, `CAIRN_NAMESPACE`, `CAIRN_IMAGE_BASE`,
   `CAIRN_TRANSCRIPT_DIR`) replaces it, sitting at the same highest-precedence layer the file
   used to occupy. This is *more* Twelve-Factor than the file was (config that varies by
   instance belongs in the environment, not in a second config file beside the first), and it
   deletes a footgun along with the mechanism: a file whose entire purpose was "don't commit
   this" is no longer sitting in a git working tree one `git add .` away from being committed
   anyway.

**Final precedence:**

- **Manifest:** `--manifest <path>` › `$CAIRN_MANIFEST`. No default.
- **Build config**, three layers, key-by-key, lowest first: `/etc/cairn/builder.toml` ›
  the resolved manifest's `[cairn.registry]` › `CAIRN_ENGINE`/`CAIRN_REGISTRY`/
  `CAIRN_NAMESPACE`/`CAIRN_IMAGE_BASE`/`CAIRN_TRANSCRIPT_DIR`.

**Considered and rejected:** keeping one non-cwd implicit fallback, such as a fixed
`/etc/cairn/cairn.toml` default for "the one deployment this host has." Rejected because it
reintroduces exactly the silent-inference risk the whole change exists to remove — a second
manifest later added to that path would silently change what a flagless invocation does, the
same failure shape as the directory walk it would be replacing. Also considered: keeping
`cairn.local.toml` as a rarely-used escape hatch alongside the env vars. Rejected — a mechanism
that exists but is redundant with a strictly simpler one is a maintenance and documentation cost
with no offsetting benefit.

**Explicitly out of scope:** `cairn`'s own project-root discovery for vendoring
(`src/cairn/project.py`, `ADR-029`) is unaffected. Finding the checkout that holds cairn's own
`pyproject.toml`/`[tool.ventwig]` while developing cairn itself is a genuinely different
question from which *deployment* a command targets, and cwd means something real there — a
developer editing cairn's own source is, by construction, standing inside cairn's own checkout.
*(BR-CFG-008, BR-CFG-009, BR-CFG-010, BR-CFG-011, BR-CFG-012, BR-CFG-013, BR-CFG-014, BR-CLI-014,
BR-CLI-016, ADR-029, ADR-039, ADR-041, ADR-043)*
