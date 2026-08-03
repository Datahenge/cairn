---
status: authoritative
owner: technical
purpose: ADR-019 — cairn and cofferdam are mutually unaware (strict decoupling)
---

# ADR-019 — cairn and cofferdam are mutually unaware (strict decoupling)

**Decided:** 2026-07-21
cairn MUST NOT rely on, leverage, or have awareness of `cofferdam` /
`cofferdam-app`, and nothing in cofferdam should be aware of Docker. If cofferdam is
installed and configured, it works; otherwise it does not — that is cofferdam's own
self-contained, fail-closed contract, needing no external orchestrator. cofferdam-app,
if used, is treated as an ordinary `[[cairn.apps]]` entry with zero special-casing.

**Rationale:** Separation of concerns — cairn is a build/deploy/data tool;
cofferdam is a runtime outbound guard at the Frappe app layer. Coupling would bloat
cairn and amputate cofferdam's bare-metal / non-Docker audience. The tools
compose as *independent* defense-in-depth layers, not as a dependency.

**Consequence (correct-by-construction):** the one scenario that seemed to need
cofferdam-awareness — restoring a Production DB into a non-prod stack — is instead met
by a **generic** rule that names no app: *a restore replaces the database (and optionally
file attachments) and MUST NOT overwrite local environment configuration on the sites
volume.* That generic rule protects `site_config.json`, local secrets, and any local
policy files (e.g. a cofferdam `environment_policy.toml`) as a side effect, without the
tool knowing their meaning. It becomes a normative `BR-DATA-###` / `BR-CFG-###`
requirement in Phase-2.

**Superseded in part by `ADR-022`:** this consequence assumed cairn might perform restores.
Under `ADR-022`, cairn performs **no** restore or data movement at all, so the generic
restore rule is moot as a cairn *feature* — its never-clobber-config principle survives only
as `BR-CFG`/`BR-DATA` prohibitions. The decoupling decision itself stands unchanged.

**Retracts:** an earlier proposal that cairn enforce cofferdam policy presence /
run `cofferdam validate` as a deploy invariant — that coupling is withdrawn.
