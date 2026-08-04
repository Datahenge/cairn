---
status: archived
owner: technical
purpose: ADR-050 — `new-tag` and `retag` merge into one command, `assign-tag`
---

# ADR-050 — `new-tag` and `retag` merge into one command, `assign-tag`

**Decided:** 2026-08-04
**Relates to:** `ADR-010` (desired-state pointer = moving registry tag), `ADR-033`/`ADR-049`
(the declared environment list), `BR-CLI-004`, `BR-CLI-009`, `BR-CLI-010`, `BR-DEPLOY-004`,
`BR-DEPLOY-009`.

**Raised** the same session as `ADR-049`, while writing the Builder user docs: `new-tag` vs
`retag` as two verbs for what a user experiences as one action ("point this environment at that
image") was a source of confusion worth checking against the actual implementation rather than
just renaming around.

## What the two-command split was actually guarding

`cli_build.py`'s `_pointer_move` is already the shared body of both commands — `new-tag` and
`retag` differ only in which of two independent existence checks they run:

1. **Is `<env>` a declared name at all** (`environments.require()`) — errors "No such
   environment" either way. Identical for both commands today; this is *not* what separates
   them.
2. **Has this environment's registry tag already been created** (`environments.assert_creating`/
   `assert_moving`) — `new-tag` refuses if the pointer already exists, `retag` refuses if it does
   not. This is the actual, and only, difference between the two verbs.

So the split guards against one specific mistake: typing `new-tag` for an environment that's
already live (would silently re-home a pointer under the "create" verb), or `retag` for one that
has never been pointed anywhere (would fail confusingly on something that looks like a rollback
but isn't). Both are real but narrow — and cost a second verb an operator has to remember to
choose correctly every time, for an action (BR-DEPLOY-004: deploy, promote, and rollback are the
*same* operation) the requirements already describe as one thing.

## The concrete cost of keeping them separate

`cairn-build setup-timer`'s generated build script (`ADR-047`) calls `retag <env> --latest --yes`
on every scheduled run. `retag` refuses to run against a pointer that doesn't exist yet
(guard 2 above) — so the *first* automated run against a brand-new environment fails, and an
operator must remember to run `new-tag <env> --latest` by hand once, before ever enabling the
timer. Nothing in `setup-timer`'s own output says so today. This is a real operational trap, not
a naming complaint.

## Decision

Merge into one command, `cairn-build assign-tag <env> <selector>`: creates the pointer if it
doesn't exist, moves it if it does. `retire` is unaffected — decommissioning is still a distinct,
one-directional act.

- **Guard 1 is unchanged** — `<env>` must still be a declared name (`BR-CLI-009`,
  `BR-DEPLOY-009a`); a typo still errors exactly as it does today.
- **Guard 2 becomes reporting, not refusal** — `assign-tag` always succeeds at whichever of
  create/move applies, but its output states which one happened ("`production` did not exist —
  created it" vs. "`production` moved to …"), so the distinction stays visible to a human even
  though it is no longer a separate verb to choose correctly in advance.
- **The `:production` confirmation gate is unchanged and now stated explicitly for both cases**
  (`BR-CLI-010`) — moving *or creating* a `:production` pointer prompts unless `--yes`. (The
  running code already gated both cases identically, since the check in `_pointer_move` was
  never conditioned on `creating`; the requirement text previously only said "moves or retires,"
  which undersold what the code already did — corrected here.)
- **`setup-timer`'s generated script switches to `assign-tag`**, closing the bootstrap trap
  above: the first automated run creates the pointer, every run after moves it, with no manual
  prerequisite step.

**Why `assign-tag` and not `set-tag` or `point`.** Keeps the existing "tag" vocabulary consistent
with `--id <tag>`, `cairn-build images`, and the registry's own tag model, rather than
introducing a new noun. "Assign" reads correctly for both the create and the move case, where
"set" or "point" lean more toward "move only."

## Scope

`BR-CLI-004` (command list), `BR-CLI-009` (existence guards → create-or-move + reporting),
`BR-CLI-010` (prod gate wording), `BR-DEPLOY-009` (which commands the declared list gates);
`environments.py` (`assert_creating`/`assert_moving` collapse into one reporting path),
`cli_build.py` (`new_tag_command`/`retag_command` collapse into `assign_tag_command`),
`provision.py`'s build script; tests; and every `userdocs/` reference. Pre-1.0 (`0.2.x`, Alpha)
and no live deployment has used either verb yet (`open/OPEN_WORK.md`'s `W-001` is still open),
so this is a clean cut, not a deprecation shim — no `new-tag`/`retag` aliases are kept.
*(BR-CLI-004, BR-CLI-009, BR-CLI-010, BR-DEPLOY-004, BR-DEPLOY-009, ADR-010, ADR-047, ADR-049)*

**Superseded 2026-08-04 (`ADR-052`), the same day, after stress-testing the design against a
real multi-environment CI workflow:** the selector menu this ADR designed
(`--latest`/`--previous`/`--id`/`--from`) is retired. `--from` in particular turned out to be
the wrong shape — an explicit assertion of "this is a promotion" where what's actually needed is
proof (does the registry already hold an image matching this environment's own currently-resolved
refs). `assign-tag` keeps its name and its create-or-move framing, but drops every selector in
favor of a single resolve-and-check operation, and drops its positional `<env>` argument for
`--manifest <path>` (`ADR-052`: no command takes an environment name directly anymore, only a
manifest, since a manifest now declares at most one).
