# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-11-27 (app in a repository subfolder proposed, `BR-BUILD-020`)

Life Scientific is moving its app into a monorepo, at `apps/lifescientific/`. bench clones an
app at its repository root, so cairn could not build it. Contributed as a pull request; nothing
here is approved yet.

- **`BR-BUILD-020`** (new, proposed). `[[cairn.apps]]` takes an optional `subdir`. The builder
  stage clones the repository, copies the folder into a local git repository, and points a
  rewritten `apps.json` at it before `bench init`. The rewrite is deleted in the same step.
- **`BR-BUILD-002`, `BR-BUILD-007`** amended to name the key and hash it. A manifest without it
  renders the same `apps.json`, cache bust, and tags as before.
- **Recipe**: a new staging script and a changed builder step. Images rebuild once.
- Two questions for Brian: whether to hash the folder's tree instead of the whole commit
  (`OQ-007`), and the key's name (`OQ-008`). Live build tracked as `W-045`.

---

## 2026-11-17 (opt-in hot swap proposed, `ADR-081`, `BR-DEPLOY-025`)

**Health probe names the site (`BR-DEPLOY-017`).** Frappe picks the site from `X-Frappe-Site-Name` or Host and has no default-site fallback, so a probe of `localhost` answered 404 on Life Scientific's healthy production target. Both probes now send `X-Frappe-Site-Name: <site>`.

**First live hot swap (prod target).** Site stayed up; nginx now reloads right after the old backend retires, closing a 30 second hang (`ADR-081`).

Life Scientific runs user acceptance testing on its staging target and asked for a converge
that does not take the site down. Contributed as a pull request; nothing here is approved yet.

- **`BR-DEPLOY-025`** (new, proposed). `[deploy] strategy = "hot-swap"` in the descriptor
  migrates from a one-off container of the new image, starts the new web containers beside the
  old ones, then retires the old ones. Sequence, limits and rejected alternatives are in
  `ADR-081` (`exploratory`), tracked in `docs/open/OPEN_DECISIONS.md` with three open points.
- **`BR-DEPLOY-003`, `BR-DEPLOY-016`** amended to name `recreate` as the default strategy.
  Behavior is unchanged for every existing descriptor.
- **Recipe entrypoint** now leaves `sites/assets` alone when the link already points at the
  container's baked assets (`BR-VEND-001`). Images rebuild once, since the recipe changed.
- `userdocs/reference/target-descriptor.md` documents `[deploy]`. Implementation index row and
  `W-044` (live verification) added. Unit-tested only; never run on a real target.

---

## 2026-11-06 (`cairn-adopt cp` and `container-info`; data boundary amended, `ADR-080`)

Brian followed `userdocs/guides/restoring-a-backup.md` on a live VPS and the step 3 container
lookup came back empty. The page assumed the reader knew their compose project name; on his
target it is `erpnext`, matching neither client nor site. With the right name the label filter
worked, so the command was sound and the page was not.

Brian then asked for two verbs:

- **`BR-CLI-032` `cp`** (new). Brian decided: allowed, both directions, with `BR-DATA-003` and
  `BR-DATA-006` amended so an operator-directed transfer is the operator acting rather than
  cairn moving data. Rationale and the rejected alternative are in `ADR-080`. Three details of
  the requirement are Claude's proposals awaiting Brian's review, listed in `ADR-080`.
- **`BR-CLI-031` `container-info`** (new). Brian decided: the descriptor's project only, with
  columns service, name, ID, image, status. Claude's proposals awaiting review: sorting by
  service, including stopped containers (`ps --all`), reading the project name back from
  compose, and a sentence instead of a bare header for an empty project.

The restore guide's step 3 now uses `cairn-adopt cp` and says outright that it runs on the
target, not in the container shell step 2 leaves open. The project-name lookup is gone from the
guide, since `cp` needs none. `userdocs/target/operating.md` and `userdocs/reference/cairn-adopt.md`
document both verbs. Neither verb has been run against a live target: they were written on a
workstation with no Docker engine. Unknowns to check on a real host: compose's `ps` JSON field
names on the target's compose version (`ID`, `Service`, `Status`, `Project` assumed), and whether
`cp` reaches a container of a held, stopped stack.

`docs/technical/05-implementation-index.md`'s word ceiling raised 2300 -> 2600 at Brian's
direction (the file sat at 2299 before the new row). Raised rather than split because it is one
table with no clean seam; the allowlist note names the long Completion Judgment cells as the
thing to trim next time.

---

## 2026-11-06 (userdocs: operator how-to for restoring a database backup)

New `userdocs/guides/restoring-a-backup.md`, linked from the Guides index and the mkdocs nav.
cairn's scope is unchanged. `BR-DATA-003` and `ADR-013` still keep restore out of cairn. The
page documents the operator running Frappe's own `bench restore` by hand, as `ADR-013` says
operators remain free to do. No new `BR`/`ADR` id: the page is documentation and changes no
behavior.

Brian settled three choices for the page (2026-11-06):

- **Scope:** cover both a backup already on the sites volume and one brought in from another
  site. The second case shows a raw `sudo docker cp` into the bench container, found by its
  compose labels, because no cairn verb transfers files. The page also covers the data
  `encryption_key` step a cross-site restore needs (`bench --site … set-config encryption_key`).
- **Reconcile during a restore:** the page has the operator stop `cairn-reconcile.timer`
  before restoring and start it again after. `cairn-adopt stop` can't serve, since it takes
  down the containers the restore runs in.
- **Placement:** Guides, not Target.

`bench restore`'s flags and prompts, the backup file naming, and the `encryption_key` /
`backup_encryption_key` split come from reading Frappe 16.20.0's source. The claim that
`cairn-adopt restart` runs `bench migrate` comes from `lifecycle.restart` → `reconcile.run_locked`:
the stack is down, so the pass converges. The page's footer says none of it has been exercised
against a live target.

---

## 2026-09-29 (`bump_version.sh`: the version bump re-locks)

New `bump_version.sh` at the repository root, beside `push_to_pypi.sh`. Tooling, so a
`docs/CHANGELOG.md` entry and no `BR`/`ADR` id (`01-documentation-conventions.md`'s
process/product rule). `uv.lock` re-locked from `0.4.9` to `0.4.15`.

`pyproject.toml` is the single source of truth for the version, but `uv.lock` records the whole
resolved graph and this project is a node in it, so the lock carries a copy. uv keeps the two in
step whenever it runs — and a bump done by hand never runs uv. The lock sat at `0.4.9` for seven
weeks and five bumps; `uv.lock` and the installed `.dist-info` share a timestamp of 2026-08-08
16:13, the last time uv ran at all. Nothing warned about it.

The script bumps the patch level (or takes an explicit version), then runs `uv lock`. Re-locking
at the *current* version is deliberately not an error — it is how a drifted lock is repaired
without inventing a release, and it is how today's drift was cleared. `--check` verifies the two
agree and changes nothing, so it suits a pre-push hook or CI; it is the guard the manual routine
never had.

Correcting a claim made earlier in the session: a `uv sync` would **not** have installed the
stale `0.4.9`. uv detects the drift (`uv lock --check` reports it) and re-resolves. The stale
venv was stale because uv had not run, not because the lock would have imposed it.

---

## 2026-09-29 (`W-042` implemented: build-machine retention)

Code for `BR-BUILD-011`, `BR-CFG-016` and `BR-CLI-018`, per `ADR-079`. 27 new tests (1008 →
1035). `W-042` moves to `in_progress` — landed and unit-tested, unverified against a real host,
which is this project's usual meaning for that status.

- `tagging.manifest_id` — the opaque `(client, image_name, environment)` digest, sharing
  `_digest`'s component termination so a manifest declaring no environment cannot collide with
  one that declares any.
- `config.client_from_path` — the non-raising client derivation. `MANIFEST_ROOT` moved from
  `provision.py` to `config.py` because `build.py` needs it and cannot import `provision`
  without a cycle; `provision` re-exports it, and `client_from_manifest` is now the raising
  wrapper over one shared derivation. The root is injectable so `provision`'s existing test
  seam still relocates the tree.
- `config.Retention` — `[retention]` parsed and validated. `_build_config_values` had insisted
  every value was a string, which a table is not, so the table is lifted out before that check.
  An invalid value is an error naming file and key, never a silent default: an operator who
  mistyped a ceiling would otherwise believe one is in force while nothing is reclaimed.
  `max_age_days` is rejected **by name**, since it is `[registry.retention]`'s key and the
  likeliest thing to be copied across.
- `prune.select_by_manifest` and `prune.plan_for` — restriction 4, and the composition that
  makes "both apply" true by running it over restriction 3's survivors rather than the original
  groups. Both exempt populations are reported, `BR-CLI-018` binding prune to state what it
  leaves alone.

Checked against the case that opened this work — 11 images across 11 input hashes, one manifest:
prune removes nothing today, and with `keep_last = 3` reclaims 6.68 GB.

Not addressed here, and worth stating: the labels reach only images built *after* this change,
and they cannot be backfilled. Every image on an existing builder is legacy until rebuilt, so the
first live runs will correctly reclaim nothing. `enabled` also defaults to `false`, so an
operator must opt in.

`cli_build.py` is left unformatted where `ruff format` would rewrite an unrelated block; it was
already so at `HEAD`, and fixing it here would mix unrelated churn into this change.

---

## 2026-09-29 (staleness sweep of the open queues)

`docs/open/OPEN_QUESTIONS.md` swept; `ADR-073` reconciled in three places; `ADR-079` and
`ADR-071`'s queue row corrected. No requirement changed; no code changed.

Prompted by finding that `ADR-073`'s `OPEN_DECISIONS.md` row had been advertising two answered
sub-questions as needing Brian, and being read back to him as fact. The sweep looked for the same
shape elsewhere and found it three more times:

- **`ADR-073` was stale in two further places** beyond the queue row: its own frontmatter still
  read `status: exploratory` with a purpose phrased as an open question, and `docs/adr/README.md`
  repeated it. The decision was settled 2026-08-18 and implemented under `W-035` (`done`,
  2026-08-19). Both now read `authoritative` and state the decision rather than the question.
- **`ADR-079` cited `OQ-005` as unanswered** — true when written this morning, false by
  afternoon. Now points at `BR-CLI-018`'s legacy exemption.
- **`ADR-071`'s row deferred on "ship the narrower `--all` first"**, which has shipped
  (`cli_build.py`, build-timer scope only, `ADR-070`). The deferral stands, but its condition is
  now "is it proven out?" rather than "ship it" — and `W-013`'s open item, `doctor`'s
  known-manifests listing being unexercised live, is the evidence it waits on.

`OQ-004`, `OQ-005` and `OQ-006` were swept out on the `OQ-001`-`003` precedent: all three are
authoritative elsewhere (`ADR-079`, `BR-BUILD-011`, `BR-CLI-018`, `BR-CFG-016`) and the queue row
added nothing. **Open Questions is now empty.**

Checked and found accurate, not changed: `ADR-044` and `ADR-071` correctly carry
`status: exploratory` while deferred; `W-009` is correctly blocked on `ADR-044`, still deferred;
`DOCS-02` is unaffected by anything this session.

**The lesson, recorded because it caused a wrong answer to Brian:** a decision that moves leaves
its status in at least four places — the ADR's frontmatter, the ADR index row, the
`OPEN_DECISIONS` row, and any document citing it. `ADR-073` updated one of four in August.
Nothing mechanical checks this today; `docs_check.py` validates links and size, not whether a
queue agrees with the record it points at.

---

## 2026-09-29 (`W-043` filed: an expiring maintenance hold)

New `W-043` in `docs/open/OPEN_WORK.md`. No requirement, decision, or code changed. `ADR-073` is
**not** reopened — it decided the hold's durability, which is unchanged; an expiry layers on top.

Filed at Brian's request after he asked whether reboot-survival should be configuration. Nothing
about the shape is chosen, and the row says so: `--for`'s optionality, whether an expired hold is
deleted or ignored, and how `doctor` distinguishes held-indefinitely from held-until-T are all
open.

**The item carries a conflict to resolve before any code.** `BR-DEPLOY-024` states that the
hold's *"presence is the whole signal"* and `hold.py` that its contents *"are never parsed for
meaning"* — an expiry read from the file contradicts both. Three candidate shapes are recorded
(expiry in the file with an open amendment; expiry as host policy against the file's mtime;
expiry in the filename, giving up `ADR-034`'s fixed path). Claude leans to the first; **Brian has
not ruled**, and the lean is recorded as a recommendation only.

One rule is recorded as *not* open, because it follows from existing reasoning rather than a new
choice: a malformed or unreadable expiry must keep the hold, matching `is_held`'s existing stance
that failing open on a parse error would resume deploys on a host somebody deliberately stopped.

---

## Archived entries

Older entries are moved out once this file grows past its word-count budget
(`.docs_check_allowlist`), by `tools/changelog_rotate.py` — each archive covers a
contiguous range, newest-first within it same as here.

- [CHANGELOG-2026-07.md](archive/CHANGELOG-2026-07.md)
- [CHANGELOG-2026-08-03.md](archive/CHANGELOG-2026-08-03.md)
- [CHANGELOG-2026-08-04-early.md](archive/CHANGELOG-2026-08-04-early.md)
- [CHANGELOG-2026-08-04.md](archive/CHANGELOG-2026-08-04.md)
- [CHANGELOG-2026-08-04-to-2026-08-05.md](archive/CHANGELOG-2026-08-04-to-2026-08-05.md)
- [CHANGELOG-2026-08-05-to-2026-08-06.md](archive/CHANGELOG-2026-08-05-to-2026-08-06.md)
- [CHANGELOG-2026-08-06.md](archive/CHANGELOG-2026-08-06.md)
- [CHANGELOG-2026-08-06-to-2026-08-18.md](archive/CHANGELOG-2026-08-06-to-2026-08-18.md)
- [CHANGELOG-2026-08-18-to-2026-08-19.md](archive/CHANGELOG-2026-08-18-to-2026-08-19.md)
- [CHANGELOG-2026-08-19-to-2026-08-20.md](archive/CHANGELOG-2026-08-19-to-2026-08-20.md)
- [CHANGELOG-2026-08-20.md](archive/CHANGELOG-2026-08-20.md)
- [CHANGELOG-2026-09-02-to-2026-09-28.md](archive/CHANGELOG-2026-09-02-to-2026-09-28.md)
- [CHANGELOG-2026-09-29.md](archive/CHANGELOG-2026-09-29.md)
- [CHANGELOG-2026-09-29-2.md](archive/CHANGELOG-2026-09-29-2.md)
