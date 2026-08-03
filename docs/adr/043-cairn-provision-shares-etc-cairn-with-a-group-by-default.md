---
status: authoritative
owner: technical
purpose: ADR-043 — `cairn-provision` shares `/etc/cairn` with a group by default
---

# ADR-043 — `cairn-provision` shares `/etc/cairn` with a group by default

**Decided:** 2026-07-26

A direct consequence of `ADR-042`: once `/etc/cairn/builder.toml` is the *only* place machine
build settings live — no per-user fallback — a root-only directory means every operator on a
multi-login box needs `sudo` for a routine edit. Left to each client engagement to solve by hand,
this is exactly the kind of setup step Brian has already rejected documenting as a runbook
(`ADR-040`): "if it's worth doing for safety/checks, it's worth building it as a reusable
installer."

**Decision:** `cairn-provision` gains a stage, run by default on every role, that:

1. Creates a group (`--admin-group`, default `cairn-admins`) if it does not already exist.
2. Ensures `/etc/cairn` exists, is owned by that group, and is mode `2775` — `rwxrws r-x` **plus
   setgid**, not merely group-writable. Brian's own suggestion was `chmod g+rw`; setgid and the
   execute bit are an addition made while implementing it, not a reinterpretation: a directory
   needs the execute bit for a group member to traverse into it or open a file inside at all —
   `g+rw` without `g+x` would leave the directory group-readable/writable but not enterable,
   which is not a usable permission set for a directory. Setgid (`g+s`) ensures files *later*
   created inside — by a future `cairn-provision` re-run, or by root writing the descriptor —
   inherit the shared group automatically rather than reverting to the creating process's own
   primary group, which would otherwise silently re-break sharing the day after this stage runs.
3. Is fully idempotent (`BR-DEPLOY-021` rule 1): an existing group is left alone and reported,
   not recreated; already-correct ownership and mode are reported and left untouched, not
   reapplied.

This runs **before** `registry` and `descriptor` (which also write under `/etc/cairn`), so the
setgid bit is already in place when those stages create their own files. `--no-admin-group`
skips the stage entirely, leaving the directory exactly as found — for an operator who already
has their own scheme, or who wants `/etc/cairn` to stay root-only.

**Amended in part 2026-08-03 (`ADR-046`):** this stage now runs as part of `cairn-build setup`
or `cairn-adopt setup` rather than a separate `cairn-provision` program — same stage, same
ordering guarantee, same idempotency, only its home moved.

**What cairn itself (not the installer) does with this fact: nothing, and reports it.** Per
`ADR-040`'s standing invariant — cairn prints host configuration, the operator (here,
`cairn-provision`, the one sanctioned exception) installs it — creating or chowning a group is a
host mutation and therefore cannot live inside `cairn` proper. `cairn doctor` instead gains a
**read-only** check reporting `/etc/cairn`'s current group, whether setgid is set, whether it is
group-writable, and whether the invoking user is a member — informational only, prescribing no
particular group name and never mutating what it finds, matching every other doctor check.

**Consequence for `BR-DEPLOY-021`.** The new stage is held to the same seven-point installer
contract as every other stage: idempotent, dry-run prints exactly what it would do, no secret
material is involved, prerequisites (root) are already gated by the existing preflight stage,
and the stage confirms its own postcondition (the directory's actual group and mode) rather than
assuming the commands it ran succeeded.
*(BR-DEPLOY-021, BR-CFG-010, ADR-040, ADR-041, ADR-042)*
