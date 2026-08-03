---
status: authoritative
owner: technical
purpose: ADR-035 — cairn emits systemd units; it never installs them
---

# ADR-035 — cairn emits systemd units; it never installs them

**Decided:** 2026-07-25
`BR-DEPLOY-001` requires `reconcile` to run on a systemd timer but does not say who creates
the unit files. Three options were weighed: cairn ignores them entirely, cairn prints them,
cairn writes them to `/etc/systemd/system` and reloads the daemon.

**Decision:** a command prints the service and timer to stdout; the operator reviews and
installs. cairn performs **no privileged host writes**.

**Why not install.** Everything cairn does today is scoped to images, the registry, and a
compose stack. Writing to `/etc/systemd/system` and running `daemon-reload` is a different
class of act — it needs root, it changes the host outside cairn's stated boundary, and it is
the kind of convenience that is discovered later as a surprise. `BR-DEPLOY-008` positions
cairn as a thin orchestrator over docker, the registry, and systemd; emitting a unit is
orchestration, adopting the host's init configuration is not.

**Why not ignore them either.** The cadence, the single-flight expectation, and the fact that
journald owns the log (`BR-DEPLOY-019`) are cairn's knowledge, not the operator's guesswork.
Printing a correct unit is documentation that cannot drift from the code, and it composes
with review: `cairn systemd-units | less`, then install deliberately.
*(BR-DEPLOY-001, BR-DEPLOY-008, BR-DEPLOY-016, BR-DEPLOY-019, BR-CLI-019, ADR-024, ADR-026)*

**Amended in part 2026-08-03 (`ADR-046`):** "the operator installs" is no longer the only
sanctioned path — `cairn-adopt setup` may also install the unit, as an explicit,
privilege-gated subcommand replacing the retired `cairn-provision`. `systemd-units` itself
is unchanged: still print-only, still never touches the host or reloads the daemon on its
own.
