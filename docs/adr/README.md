---
status: authoritative
owner: technical
purpose: Index and governance rules for cairn's Architectural Decision Records.
---

# Architectural Decision Records

This folder holds cairn's **consequential** decisions — ones where implementation would be
materially different depending on the outcome, that cross a boundary, or that are hard to
reverse once implementation begins. Lighter, easily-reversible decisions belong in
[../../decisions/](../../decisions/) instead.

Stable IDs (`ADR-NNN`) persist even if a decision reopens or is amended. When a still-open
question in `open/OPEN_DECISIONS.md` is decided, it's promoted here (or to `decisions/`),
carrying its original ID into the new file's `origin` field so a citation made while it was
open still resolves.

`status: exploratory` in a file's frontmatter means the decision is **not yet settled** — the
question is tracked live in [../../open/OPEN_DECISIONS.md](../../open/OPEN_DECISIONS.md) and
the full analysis lives here so nothing is lost while it's pending.

## Lifecycle

**Promotion threshold:** an entry graduates here (rather than `decisions/`) when multiple
reasonable options exist or the decision carries significant reversibility cost.

**Retirement:** when an ADR is **fully** superseded or struck (not merely amended), its full
body moves to [../archive/](../archive/) and a short stub is left at its original path here,
pointing to the superseding ADR and the archive copy — so existing citations keep resolving.
An ADR that is only **partially** amended keeps its amendment noted inline and stays in place,
unarchived.

## Index

| ADR | Status | Summary |
|---|---|---|
| [ADR-001](001-wrap-frappe-docker-never-modify-it.md) | `authoritative` | Wrap `frappe_docker`, never modify it |
| [ADR-002](002-target-single-host-vps-with-docker-compose.md) | `authoritative` | Target: single-host VPS with Docker Compose |
| [ADR-003](003-cli-substrate-python-click-typer.md) | `authoritative` | CLI substrate: Python (Click/Typer) |
| [ADR-004](004-image-build-strategy-custom-not-layered.md) | `authoritative` | Image build strategy: `custom`, not `layered` |
| [ADR-005](005-no-github-vps-ssh-access.md) | `authoritative` | No GitHub → VPS SSH access |
| [ADR-006](006-deploy-trigger-model-idempotent-reconcile-pull-loop.md) | `authoritative` | Deploy trigger model: idempotent reconcile + pull loop |
| [ADR-007](007-vendoring-via-ventwig-committed-drift-checked.md) | `authoritative` | Vendoring via `ventwig`, committed + drift-checked |
| [ADR-009](009-container-registry-registry-agnostic-ghcr-recommended-default.md) | `authoritative` | Container registry: registry-agnostic; no default recommended (amended by `ADR-038`) |
| [ADR-010](010-desired-state-pointer-the-environment-s-moving-registry-tag.md) | `authoritative` | Desired-state pointer = the environment's moving registry tag |
| [ADR-012](012-rollback-does-not-restore-the-database.md) | `authoritative` | Rollback does NOT restore the database |
| [ADR-013](013-backup-restore-db-movement-out-of-scope.md) | `authoritative` | Backup / restore / DB movement: OUT OF SCOPE |
| [ADR-014](014-bench-migrate-is-the-sole-sanctioned-db-interaction.md) | `authoritative` | `bench migrate` is the sole sanctioned DB interaction |
| [ADR-015](015-manifest-cairn-toml-and-app-pinning-model.md) | `authoritative` | Manifest (`cairn.toml`) and app-pinning model |
| [ADR-016](016-single-site-per-environment-multi-site-deferred.md) | `authoritative` | Single site per environment; multi-site deferred |
| [ADR-017](017-secrets-are-operator-provisioned-cairn-is-secret-agnostic.md) | `authoritative` | Secrets are operator-provisioned; cairn is secret-agnostic |
| [ADR-018](018-one-package-datahenge-cairn-command-cairn-split-deferred.md) | `authoritative` | One package `datahenge-cairn`; command `cairn`; split deferred |
| [ADR-019](019-cairn-and-cofferdam-are-mutually-unaware-strict-decoupling.md) | `authoritative` | cairn and cofferdam are mutually unaware (strict decoupling) |
| [ADR-020](020-strengthen-upstream-pin-immutability-ventwig-enhancement.md) | `exploratory` | Strengthen upstream-pin immutability (ventwig enhancement) |
| [ADR-021](021-deliberate-fork-of-frappe-docker-as-the-sanctioned-escape-hatch.md) | `exploratory` | Deliberate fork of frappe_docker as the sanctioned escape hatch |
| [ADR-022](022-cairn-operates-on-the-code-image-plane-the-data-plane-is-off.md) | `authoritative` | cairn operates on the code/image plane; the data plane is off-limits |
| [ADR-023](023-opt-in-bench-install-app-never-automatic.md) | `archived` | Opt-in `bench install-app`; never automatic |
| [ADR-024](024-reconcile-is-a-purpose-built-thin-orchestrator-not-watchtower.md) | `authoritative` | Reconcile is a purpose-built thin orchestrator (not Watchtower/Flux/Argo) |
| [ADR-025](025-deploy-failure-halt-report-rollback-stays-manual.md) | `authoritative` | Deploy failure = halt + report; rollback stays manual |
| [ADR-026](026-observability-stdout-stderr-optional-failure-webhook-host-owns.md) | `authoritative` | Observability: stdout/stderr + optional failure webhook; host owns monitoring |
| [ADR-027](027-build-engine-is-pluggable-docker-podman-deploy-engine-stays.md) | `authoritative` | Build engine is pluggable (`docker` \| `podman`); deploy engine stays Docker |
| [ADR-028](028-cairn-doctor-is-role-aware-detected-from-context.md) | `archived` | `cairn doctor` is role-aware, detected from context |
| [ADR-029](029-the-manifest-root-and-cairn-s-own-project-root-are-independent.md) | `authoritative` | The manifest root and cairn's own project root are independent |
| [ADR-030](030-provenance-label-schema-com-datahenge-cairn-standard-oci-keys.md) | `authoritative` | Provenance label schema: `com.datahenge.cairn.*` + standard OCI keys |
| [ADR-031](031-three-execution-contexts-a-build-transcript-only-when-nobody.md) | `authoritative` | Three execution contexts; a build transcript only when nobody else owns the record |
| [ADR-032](032-one-image-per-input-hash-prune-only-what-cairn-labelled.md) | `authoritative` | One image per input hash; prune only what cairn labelled |
| [ADR-033](033-the-declared-environment-list-is-a-cairn-environments-table-in.md) | `authoritative` | The declared environment list is a `[cairn.environments]` table in the manifest |
| [ADR-034](034-the-target-environment-descriptor-is-etc-cairn-environment-toml.md) | `authoritative` | The target environment descriptor is `/etc/cairn/adopt.toml`, one per host |
| [ADR-035](035-cairn-emits-systemd-units-it-never-installs-them.md) | `authoritative` | cairn emits systemd units; it never installs them |
| [ADR-036](036-cairn-speaks-the-registry-api-directly-rather-than-shelling-out.md) | `authoritative` | cairn speaks the registry API directly, rather than shelling out |
| [ADR-037](037-cairn-never-installs-an-app-the-install-app-clause-is-struck.md) | `authoritative` | cairn never installs an app; the `install-app` clause is struck |
| [ADR-038](038-the-image-belongs-in-the-account-that-owns-the-source.md) | `authoritative` | The image belongs in the account that owns the source |
| [ADR-039](039-registry-coordinates-belong-in-the-manifest-not-in-machine.md) | `authoritative` | Registry coordinates belong in the manifest, not in machine config |
| [ADR-040](040-provisioning-is-an-installer-beside-the-cli-never-a-verb-inside.md) | `authoritative` | Provisioning is an installer beside the CLI, never a verb inside it |
| [ADR-042](042-configuration-becomes-fully-explicit-and-host-shared-no.md) | `authoritative` | Configuration becomes fully explicit and host-shared: no directory search, no home directories, no local-override file |
| [ADR-043](043-cairn-provision-shares-etc-cairn-with-a-group-by-default.md) | `authoritative` | `cairn-provision` shares `/etc/cairn` with a group by default |
| [ADR-044](044-local-git-mirror-for-private-app-reachability-not-a-revival-of.md) | `exploratory` | Local git mirror for private-app reachability (not a revival of Option C) |
| [ADR-045](045-published-documentation-mkdocs-material-userdocs-default-github.md) | `authoritative` | Published documentation: mkdocs-material, `userdocs/`, default GitHub Pages URL |
| [ADR-046](046-two-cli-entry-points-cairn-build-and-cairn-adopt-replace-the.md) | `authoritative` | Two CLI entry points, `cairn-build` and `cairn-adopt`, replace the unified `cairn` binary and `cairn-provision` |
| [ADR-047](047-canonical-manifest-home-srv-cairn-scaffolding-and-setup-timer.md) | `authoritative` | Canonical manifest home `/srv/cairn/<client>/`, `setup` scaffolding, and the `setup`/`setup-timer` split |
| [ADR-048](048-cairn-registry-a-third-cli-for-local-registry-lifecycle.md) | `authoritative` | `cairn-registry`, a third CLI entry point for local-registry provisioning, retention, and garbage collection |
| [ADR-050](050-new-tag-and-retag-merge-into-assign-tag.md) | `authoritative` | `new-tag` and `retag` merge into one command, `assign-tag` |

`ADR-008`, `ADR-011`, `ADR-041`, and `ADR-049` are recorded in [../../decisions/](../../decisions/)
instead, as lightweight decisions.

## Design vocabulary (first-class concepts)

These aren't standalone decisions but are settled framing the design depends on:

- **Cairn marker** — a durable record binding **git ref → resolved commits → image tag →
  digest** (provenance), so any built/deployed image can be identified and navigated back to.
  *(No DB snapshot — the data plane is off-limits, `ADR-022`.)*
- **Desired-state pointer** — the "newest stone": a small artifact CI advances that says which
  ref the VPS should converge to. CI's job ends at *build image + advance pointer*; the VPS's
  job is *converge to pointer*.
- **Trigger on _image-ready_, not on commit** — a raw commit can't deploy (no image yet); the
  real event is "a new image is built & pushed."
