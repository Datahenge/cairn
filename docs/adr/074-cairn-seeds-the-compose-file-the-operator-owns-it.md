---
status: authoritative
owner: technical
purpose: ADR-074 — cairn writes the first compose file on a fresh install and then hands it to the operator; it never regenerates it
---

# ADR-074 — cairn seeds the compose file; the operator owns it thereafter

**Decided:** 2026-08-18 (Brian)

`ADR-068` gave cairn initial provisioning but left unanswered what happens to the compose file
*after* it exists. `ADR-073`'s investigation forced the question: on the one live host, cairn
orchestrates a client-authored `pwd.yml` descendant it does not own, at a path it does not
control. Brian's framing separates two horizons — this particular VPS today, and cairn used by
dozens of operators tomorrow, installed on its own with `frappe_docker` never in the picture.

**The decision, in Brian's words: "Help them. But don't take away their control."**

Four commitments follow:

1. **cairn writes the *first* compose file** on a fresh installation, from its owned recipe
   (`BR-VEND-001`). A new operator does not hand-assemble a stack.
2. **cairn never regenerates it.** Seed-once, then hands off — the same pattern
   `registry_provision.py` already uses for the fully-commented starter
   `/etc/cairn/registry.toml`. This is what makes operator edits safe: there is no
   regeneration pass to clobber them, and therefore no `.rpmnew`-style conffile problem.
3. **`${CUSTOM_IMAGE}`/`${CUSTOM_TAG}` stay.** The indirection is deliberately retained so
   cairn can change the ERPNext image at will without rewriting the operator's file. This is
   the seam between the two ownerships: cairn owns *which image*, the operator owns
   *everything else about the stack*.
4. **The operator may read and edit it.** It is configuration, not a generated artifact.

## Location

`/etc/cairn/`, matching `registry.toml` — the tier for files cairn seeds once and the operator
owns thereafter. This is distinct from `/opt/cairn-registry/` (`ADR-063`), which holds files
cairn *rewrites* and the operator is not invited to edit, and from `/var/lib/cairn-registry`
(`ADR-060`), which holds data. The recipe's `compose.yaml` uses named volumes exclusively —
no relative bind mounts, no build context, no `env_file:` — so no path resolution depends on
where it sits; the choice is free, and consistency decides it.

## Consequence for `ADR-073`: unchanged, pending a question not yet asked

An earlier draft of this record claimed that retaining `${CUSTOM_IMAGE}` settles `ADR-073`'s
fork by making an on-disk `.env` permanent architecture. **That was wrong, and it was the
AI's inference, not Brian's decision.** It is corrected here rather than quietly deleted,
because the mistake is instructive.

cairn requires no `.env` and never has: it injects `CUSTOM_IMAGE`/`CUSTOM_TAG` into the
subprocess environment on every invocation (`reconcile.py:401-413`). Life Scientific's VPS has
no `.env` beside its compose file and converges correctly — direct evidence that nothing on
disk is needed for cairn's own operation. An `.env` serves exactly one actor: a human running
`docker compose` directly, bypassing cairn. Commitment 4 grants the operator the right to
**see and edit** the file. Whether it also grants the right to *run* it by hand is a separate
question Brian has not been asked, and the two do not follow from one another — an operator can
own, read, and edit a file that only cairn ever executes.

So this decision leaves `ADR-073` where it was. If hand-running is never wanted, no `.env` is
needed and that candidate disappears entirely. If it is wanted, there are at least two ways to
provide it — an `.env` on disk, or a `cairn-adopt compose -- <args>` passthrough that execs the
correct invocation — and the passthrough writes nothing into a group-shared directory, avoiding
the `BR-DEPLOY-011` question the `.env` raises.

What this record *does* settle for `ADR-073` is narrower and holds regardless: `BR-VEND-006`'s
`${VAR:?...}` guard means any attempt to run the stack without those variables fails loudly
instead of silently starting another vendor's image. That is the safety net; whether to also
provide a paved path is undecided.

## Open, deliberately not decided here

* Whether the `.env` cairn maintains may hold anything beyond `CUSTOM_IMAGE`/`CUSTOM_TAG`.
  `/etc/cairn` is group-shared when `cairn-adopt setup --admin-group` is used, and
  `BR-DEPLOY-011` forbids cairn handling secret values — so the file's mode and permitted
  contents need their own ruling before implementation.
* Whether take-ownership (`W-033`) converges an existing deployment's file onto cairn's recipe,
  or merely relocates and adopts whatever is already there. Life Scientific's VPS is the first
  case either way.

*(BR-VEND-001, BR-DEPLOY-007, BR-DEPLOY-010, BR-DEPLOY-011, ADR-059, ADR-063, ADR-068, ADR-073)*
