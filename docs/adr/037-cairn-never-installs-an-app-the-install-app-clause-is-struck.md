---
status: authoritative
owner: technical
purpose: ADR-037 — cairn never installs an app; the `install-app` clause is struck
---

# ADR-037 — cairn never installs an app; the `install-app` clause is struck

**Decided:** 2026-07-25
`BR-DEPLOY-003` permitted `bench install-app` during a reconcile behind an opt-in directive,
and `BR-CLI-004` expressed that opt-in as `--install-app <apps>` on the pointer verbs. The
implementation exposed that nothing carried the directive across: the two halves of an
environment are joined **only by the tag name** (`BR-DEPLOY-009`), and a tag name has no room
for a payload.

The obvious response was to invent a transport — a label on the image, a field in the
descriptor, a second artifact in the registry. Brian leaned toward striking the clause
instead, and asked for a recommendation. **Struck**, and the reason is structural rather than
one of convenience:

**A convergence loop cannot host a one-shot mutation.** `reconcile` makes actual state match
desired state, repeatedly, forever, and is safe precisely because repeating it is a no-op.
`install-app` is irreversible and must happen exactly once. Hosting it would require cairn to
remember whether it already had — durable state cairn deliberately does not keep
(`BR-DEPLOY-019`). Absent that memory it either re-runs on every poll, or depends on a flag
that goes stale the moment it is used. Every candidate transport was really a proposal for
where to keep that state.

Two further reasons, either sufficient on its own:

- **It is a second data-plane write.** cairn's sole permitted DB touch is `bench migrate`
  (`ADR-022`, `BR-DATA-005/006/008`). `install-app` creates DocTypes and inserts records.
- **It breaks rollback.** Install an app, then move the pointer back (`BR-DEPLOY-004`): the
  schema remains, the code that understands it is gone — a state cairn would have
  manufactured. `bench migrate` is safe after every image enable because it reconciles schema
  to code that *exists*; `install-app` creates schema for code that may vanish.

**Consistency clinches it.** `BR-DEPLOY-007` already makes `bench new-site` the operator's
job: cairn deploys to environments that already exist. Installing an app is the same class of
act — it changes what the environment *is*, not which version of the code it runs. So
`install-app` joins `new-site` on the operator's side of the line, permanently.

Recorded as `BR-DEPLOY-003a`. `--install-app` is removed from `BR-CLI-004`. `reconcile`'s
behaviour does not change: it never installed.
*(BR-DEPLOY-003a, BR-DEPLOY-007, BR-CLI-004, BR-DATA-005/006/008, ADR-022, ADR-023, ADR-026)*
