# BR-CLI — Command Surface & UX Requirements

_Status: **approved** 2026-07-24 (living — may be revised via CHANGELOG) · Last updated: 2026-07-24_

The `cairn` command surface. Mostly *cites* verbs defined in other areas; adds the
create/move/retire guards, global flags, and output/exit conventions. Conventions: see
`/CLAUDE.md`. Decisions cited: `ADR-003`, `ADR-018`, `ADR-023`.

---

## Substrate

**`BR-CLI-001`** — cairn is a **single Python CLI** (Click/Typer, `ADR-003`), invoked as
`cairn` (distribution `datahenge-cairn` + `datahenge-cairn` alias), with subcommands. One
package. *(ADR-003, ADR-018)*

## Command surface

**`BR-CLI-002`** *(build)* — `cairn build [--push] [--manifest <path>] [--no-cache]
[--dry-run]` — build the image from `cairn.toml` (resolve refs → apps.json → tagged image +
provenance labels). **Default is build-only**; `--push` also uploads. *(BR-BUILD-*)*

**`BR-CLI-003`** *(push)* — `cairn push [--id <tag>]` — upload a built image to the registry
(default: the current manifest's just-built image). *(BR-BUILD-*, BR-CFG-011)*

**`BR-CLI-004`** *(pointer verbs — create / move / retire)* —
- `cairn new-tag <env> <selector>` — **create** a new environment pointer.
- `cairn retag <env> <selector>` — **move** an existing pointer (server-side retag, no
  rebuild).
- `cairn retire <env>` — **decommission** an environment from cairn (see `BR-CLI-009`).

Selectors for `new-tag`/`retag`: `--latest | --previous | --id <ident> | --from <env>`
(`--from` points at whatever another env currently runs → cross-env promotion). Both accept
opt-in **`--install-app <apps>`** (`ADR-023`). *(BR-DEPLOY-004, ADR-023)*

**`BR-CLI-005`** *(introspection)* — `cairn images [--tags] [--json]` — registry
introspection: tags, digests, and provenance labels read **remotely** (no pull). *(BR-DEPLOY-005)*

**`BR-CLI-006`** *(vendor)* — `cairn vendor status | sync` — thin ventwig wrappers. *(BR-VEND-*)*

**`BR-CLI-007`** *(doctor)* — `cairn doctor` — **role-aware** preflight, role detected from
context (`ADR-028`). On a **build/control** machine: the selected build engine present and
capable of secret-mount builds (Docker Engine v23+, or podman v4+ — `ADR-027`); **`git`**,
which cairn resolves every manifest ref with (`BR-BUILD-005`); `ventwig status` clean;
config valid. On a **target**: Docker Engine + Compose, systemd, and registry
reachability. *(BR-VEND-005/006, BR-BUILD-005, BR-CLI-014, ADR-027, ADR-028)*

**`BR-CLI-008`** *(reconcile)* — `cairn reconcile` — the target-side, single-flight
pull-loop verb, run under systemd. *(BR-DEPLOY-001/003/016)*

## Guards & safety

**`BR-CLI-009`** *(existence guards; no auto-vivification)* — Environment existence is
determined by cairn's **declared environment list** (control-side, `BR-DEPLOY-009`).
- `new-tag <env>` MUST **error if `<env>` already exists**.
- `retag <env>` / `retire <env>` MUST **error if `<env>` does not exist**
  (`No such environment '<env>'`).

`retire <env>` removes `<env>` from the declared list, touches **no images**, and MUST warn
that the **registry tag name persists** (GHCR has no per-tag delete — see `03-deploy.md`).
*(BR-DEPLOY-009)*

**`BR-CLI-010`** *(prod gate)* — Any command that moves or retires a **`:production`**
pointer MUST require **explicit confirmation** — interactive prompt by default, `--yes` to
skip for automation. `--install-app` against Production is **doubly** explicit. *(BR-DEPLOY-015)*

**`BR-CLI-011`** *(least surprise)* — Nothing consequential is silent: no auto-rollback
(`ADR-025`), no auto-install (`ADR-023`), no data/volume/DB writes of cairn's own
(`ADR-022`). Consequential/destructive actions confirm; `--dry-run` is available on
`build`/`push`/`new-tag`/`retag`/`reconcile`.

**Silence cuts both ways.** A command MUST NOT appear to do nothing: any operation that
takes more than a moment (ref resolution, image build, push) MUST report what it is doing
and what it is doing it to, and MUST verify its own post-condition rather than trusting an
exit code — an engine that exits 0 without producing the image MUST be reported as a
failure, not as success. *(ADR-022, ADR-023, ADR-025)*

## Conventions

**`BR-CLI-012`** *(logging & exit codes)* — cairn logs **only to stdout/stderr**
(`BR-DEPLOY-019`) and MUST return **meaningful exit codes** (0 success, non-zero failure)
so systemd and CI detect outcomes. *(BR-DEPLOY-019)*

**`BR-CLI-013`** *(output)* — Human-readable by default; **`--json`** on read/introspection
commands (`images`, status) for CI/scripting. *(—)*

**`BR-CLI-014`** *(config discovery)* — cairn discovers the manifest (`cairn.toml`), build
config (`~/.config/cairn/config.toml` + optional `cairn.local.toml`), and (on targets) the
environment descriptor; the common case needs **no flags** (minimal typing). Precedence is
specified by `BR-CFG-012`. *(BR-CFG-008, BR-CFG-012, ADR-029)*

**`BR-CLI-015`** *(help & errors)* — Every command has `--help`; errors are actionable and
name the fix; convention over configuration. *(—)*
