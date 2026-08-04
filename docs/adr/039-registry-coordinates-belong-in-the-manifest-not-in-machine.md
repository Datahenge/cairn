---
status: authoritative
owner: technical
purpose: ADR-039 — Registry coordinates belong in the manifest, not in machine config
---

# ADR-039 — Registry coordinates belong in the manifest, not in machine config

**Decided:** 2026-07-25
`BR-CFG-008` put registry and namespace in machine-local build config and stated that "the
manifest MUST remain free of local/build/registry settings". Under `ADR-038` that becomes a
defect: the fact that Acme's images belong in `ghcr.io/acme-corp` would live only on the
operator's laptop — undocumented state, lost if the laptop dies, and invisible to the client who
is supposed to be able to take the deployment over.

**Decision:** the manifest declares `[cairn.registry]` with a required `host` and an optional
`namespace`.

```toml
[cairn.registry]
host      = "ghcr.io"
namespace = "acme-corp"      # the client's org
```

**Why the original reasoning inverted.** `BR-CFG-008` excluded these on the assumption that one
manifest might target many registries, making the target a machine fact. With client-owned
registries, **one manifest means one owner means one registry** — the target is the most
deployment-specific fact there is. Nor are they secrets (`BR-CFG-010` governs credentials, and
these are a hostname and an account name), so nothing about committing them is unsafe.

**Precedence, and why the manifest sits in the middle** (`BR-CFG-012`): machine-wide config,
then the manifest's registry, then `cairn.local.toml`. The manifest overriding machine-wide
config is the load-bearing half — otherwise a machine-wide `namespace = "datahenge"` would
silently publish a client's image into the operator's account, which is precisely what
`BR-CFG-013` forbids. Keeping `cairn.local.toml` *above* the manifest preserves the local escape
hatch: publish a client's deployment somewhere else for a test without editing, and committing,
their file.

**What stays machine-local:** `engine`, `transcript_dir`. These describe the machine, not the
deployment. `[cairn.registry]` accepts only `host` and `namespace`, and rejects anything else as
an unknown key, so the boundary cannot erode by accident.
*(BR-CFG-014, BR-CFG-008, BR-CFG-012, BR-CFG-013, ADR-029, ADR-038)*

**Amended 2026-08-03 — `image_base` removed.** It originally stayed machine-local alongside
`engine` and `transcript_dir` as a full override of the composed `<registry>/<namespace>/
<image_name>` string, for a registry path the standard composition couldn't produce. No
concrete case for it ever surfaced in practice, and Brian judged it unjustified complexity
sitting next to the exact composition `BR-CFG-011` already defines. Dropped from
`BUILD_CONFIG_KEYS`, `BuildConfig`, and `CAIRN_IMAGE_BASE`; `resolve_image_base()` now always
composes from `registry`/`namespace`, with no override path.
