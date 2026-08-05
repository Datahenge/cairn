---
status: authoritative
owner: technical
purpose: ADR-060 — the registry's default data_dir moves from /opt/cairn-registry/data to /var/lib/cairn-registry, correcting ADR-053's FHS citation
---

# ADR-060 — the registry's default `data_dir` moves from `/opt/cairn-registry/data` to `/var/lib/cairn-registry`

**Decided:** 2026-08-05 (raised by Brian, questioning `ADR-053`'s claim that `/opt` was the
FHS-correct home for registry blobs).
**Amends:** `ADR-053`, in part — the split itself (low-churn config in `/etc/cairn`, relocatable
bulk data elsewhere) is unchanged; only *where* "elsewhere" defaults to changes.

**The correction.** `ADR-053` justified `/opt/cairn-registry` for blob storage as mirroring
"ordinary FHS convention (`/etc` = configuration, `/opt` = self-contained application data)."
That overstates what `/opt` is for. `hier(7)`/FHS reserves `/opt` for add-on **application
software packages** — where a program's own files live, historically third-party/self-contained
installs (`/opt/google/chrome`) — not a service's growing runtime state. FHS's own home for that
is `/var/lib`: "state information for programs... modified as the program runs," with `/var/lib/
docker`, `/var/lib/mysql`, and `/var/lib/postgresql` as its own canonical examples. Registry
blobs are exactly this shape — mutable, growing, persistent service state — and the `registry:2`
container's own internal storage path already uses this convention
(`registry_provision.py`'s compose bind-mount target, `/var/lib/registry`). Cairn's host-side
default should match.

**Decision.** `RegistryConfig._DEFAULT_DATA_DIR` (`registry_config.py`) changes from
`/opt/cairn-registry/data` to `/var/lib/cairn-registry`. `data_dir` remains fully
operator-relocatable via `[registry] data_dir` in `/etc/cairn/registry.toml` — this only changes
what an operator gets who never sets it.

**`PROJECT_DIR` (`/opt/cairn-registry`, the compose project file) is unaffected.** It holds only
the generated `compose.yaml` — the installed application's own tree, which is what `/opt`
actually means — not bulk runtime data. `ADR-053`'s split between "low-churn shared config" and
"relocatable bulk data" still holds; only the bulk-data default moved to the path FHS actually
assigns that role.

**Scope.** No migration tooling and no `userdocs/` procedure — pre-1.0 (`0.4.x`), and the one
live deployment (`open/OPEN_WORK.md`) is being moved by hand. New installs simply get the
corrected default. *(BR-REG-002, BR-REG-003, `ADR-053`)*
