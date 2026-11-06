---
status: authoritative
owner: technical
purpose: ADR-080 — `cairn-adopt cp` is an operator-directed transfer, which the data-plane boundary permits because cairn chooses neither the content nor the destination
---

# ADR-080 — An operator-directed `cp` is not cairn moving data

**Decided:** 2026-11-06 (Brian, after following the restore guide on a live VPS).

**Amends:** `BR-DATA-003`, `BR-DATA-006`. **Adds:** `BR-CLI-032`. **Relates to:** `ADR-013`,
`ADR-022`, `ADR-073`, `ADR-075`.

## Context

`userdocs/guides/restoring-a-backup.md` brings a backup from another site into the bench
container with a raw `sudo docker cp`, after finding the container by its compose labels. On
Brian's target the lookup came back empty: the compose project is `erpnext`, which matches
neither client nor site, and nothing in the guide made that discoverable. `ADR-073` already says
an operator should not be driving a cairn-managed stack with raw Docker commands, and the guide
was asking them to.

`cairn-adopt` already knows the project and compose files from the descriptor. A `cp` verb
removes the lookup entirely. But two approved requirements read as forbidding it: `BR-DATA-006`
("MUST NOT itself read, write … persistent Docker volumes") and `BR-DATA-003` ("MUST NOT …
relocate, or otherwise move SQL data between environments"). Copying a production backup onto
a staging target's sites volume is the motivating case for both.

## Decision

`cairn-adopt cp SOURCE DEST` is allowed (`BR-CLI-032`), in both directions. The two
requirements are amended in place to say that an operator-directed transfer verb is the operator
acting, not cairn.

The line is **who chooses**. cairn never chooses, defaults, inspects, or rewrites what is copied
or where; the operator names both ends. That is the same footing `ADR-075` gave `shell` and
`mariadb`: cairn hands over a capability and the operator does the work. It is also what still
separates `cp` from the `site_config.json` printing verb `ADR-075` refused. There, cairn itself
would have read a named file and put a credential on the terminal.

## Rejected alternative

**Refuse `cp` and keep the raw `docker cp` in the guide.** This kept the boundary text
untouched. It was rejected because it leaves the operator doing exactly what `ADR-073` says they
should not, with a lookup that has already failed in practice. It also does not keep any data
out of cairn's reach that `shell` and `mariadb` do not already put within the operator's.

## Claude's recommendations, recorded as such

Brian chose: allow `cp`, both directions, amend the boundary wording. The following details of
`BR-CLI-032` were proposed by Claude while drafting and await Brian's review:

- refusing before running anything when neither or both arguments name a container;
- making the host-side path absolute against the operator's working directory, so it cannot be
  resolved against compose's `--project-directory` instead;
- requiring an explicit `SERVICE:` rather than defaulting to the bench container the way `shell`
  does.

*(BR-CLI-030, BR-CLI-032, BR-DATA-003, BR-DATA-006, ADR-013, ADR-022, ADR-073, ADR-075)*
