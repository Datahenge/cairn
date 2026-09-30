# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

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

## 2026-09-29 (`W-013` narrowed; the stale `ADR-073` queue row reconciled)

`docs/open/OPEN_WORK.md` (`W-013`) and `docs/open/OPEN_DECISIONS.md` (`ADR-073`) updated. No
requirement, decision, or code changed — both are corrections to what the queues were reporting.

Brian confirmed `setup` and `setup-timer` have been run against a real VPS, which closes
`setup-timer`'s happy path — one of `W-013`'s two remaining verifications. `doctor`'s
known-manifests listing is still unexercised and is now the only thing between that row and
`done`.

`ADR-073`'s queue row had been stale since 2026-08-18. The ADR answered both sub-questions that
day — the hold **is** durable at `/etc/cairn/hold`, and the `.env` collision is moot since
candidate (a) was rejected — and `W-035` implemented it, but the row still advertised both as
needing Brian and was read back to him as outstanding. Reconciled against the ADR and marked
`implemented`.

Brian separately asked whether reboot-survival could be configuration rather than a fixed choice.
No change made and none recorded: Claude's recommendation is against it, on the grounds that the
two failure modes are not symmetric — a hold lost at reboot lets the timer converge a stack
mid-maintenance silently, while a forgotten hold is visible, `BR-CLI-020` having made `doctor`
report one on every run precisely as the counterweight to choosing durable. An **expiring** hold
(`stop --for <duration>`) was offered as the better instrument if forgotten holds are the
concern, since a reboot bears no relation to how long maintenance takes. Awaiting Brian's ruling;
nothing is filed.

---

## 2026-09-29 (build-machine retention specified: `BR-CFG-016`, `BR-CLI-018`'s fourth restriction)

New `BR-CFG-016` in `docs/requirements/05-config.md`; `BR-CLI-018` amended in
`docs/requirements/06a-cli-build.md` from three concentric restrictions to four. `W-042` and the
implementation index updated. **No code changed** — `W-042` is now implementation-only.

`BR-CFG-016` defines `[retention]` in `/etc/cairn/builder.toml`: `enabled` (default `false`),
`keep_last` (per manifest), `require_pushed` (default `true`). `max_age_days` is deliberately
absent, unlike `[registry.retention]` — an age ceiling cannot bound disk, since a burst inside
the window is retained however large it grows, which is `W-041`'s defect. That absence is Brian's
count-over-age argument written into a requirement.

`BR-CLI-018`'s new restriction 4 removes only images beyond the newest `keep_last` per manifest,
grouped by the opaque id and never by a readable environment name. Restriction 3 bounds
duplicates *within* one build; restriction 4 bounds how many builds a manifest keeps — which is
the one that actually bounds disk, and the one that did not exist. With `[retention]` absent or
disabled, prune behaves exactly as before.

Two exemptions apply to restriction 4 **only**, with restrictions 1-3 still in force: legacy
images (no manifest id, unrelabellable because labels are immutable, left to the administrator
but MUST be reported), and unpushed images while `require_pushed` is true.

**Two defaults chosen by Claude, not ruled on by Brian, and flagged here rather than presented as
settled:** `keep_last = 10`, taken from `[registry.retention]` on the instruction to mirror that
table; and retention being file-only, with no `CAIRN_*` environment override and no CLI flag,
which follows the same mirroring but was not separately discussed. Either is a one-line change if
Brian wants it otherwise.

---

## 2026-09-29 (`OQ-005` and `OQ-006` answered; `W-042` unblocked)

`OQ-005` and `OQ-006` resolved in `docs/open/OPEN_QUESTIONS.md`; `W-042` moved from `blocked` to
`open`. No requirement text written yet; no code changed.

**`OQ-005` — images with no manifest label (Brian): ignore them.** An unlabelled image is assumed
legacy, is never selected by the per-manifest axis, and is left for the administrator to remove
by hand. Reporting is not optional — `BR-CLI-018` already binds prune to state what it leaves
alone, and an operator cannot make a call about images they are not shown. **Scope confirmed by Brian the same
day:** the exemption is scoped to the *new per-manifest axis only*, leaving today's
per-input-hash `--keep` applying to legacy images unchanged. The alternative reading would make `cairn-build prune` a no-op on every
existing host, since no image anywhere carries the label yet.

**`OQ-006` — the `require_pushed` default (Brian): `true`.** Ruled `false` and reversed the same
day as the safer default. A sweep must not evict an image that exists nowhere but this machine.
`ADR-072` is not overturned — it remains the behaviour when the knob is `false` — but it
deliberately removed pushed-ness as a protection, so a `true` default restores by default what
that decision dropped. A reader of `ADR-072` alone would not predict the shipped default, so the
requirement text must say so.

Every decision `W-042` needs is now taken: `[retention]` in `builder.toml` needs a `BR-CFG` id,
and the per-manifest axis needs `BR-CLI-018` amended or a new `BR-CLI` id.

---

## 2026-09-29 (`ADR-079` amended: an opaque manifest id carries the grouping)

`ADR-079` rewritten; `BR-BUILD-011` and `ADR-030`'s schema updated; `OQ-004`'s answer, `W-042`,
the ADR index and the implementation index follow. **No code changed.**

`ADR-079` had rejected an opaque digest hours earlier, on the grounds that it still binds the
image to one environment and so is equally false after a promotion — it merely hides the
falsehood. Brian reversed that: falsehood requires a claim, and an opaque value makes none. What
made a plaintext `environment=staging` harmful was the *intent* a reader infers from it, and no
reader infers intent from `d32jf32a`.

So `BR-BUILD-011` now stamps a plaintext `com.datahenge.cairn.client` **and** an opaque
`com.datahenge.cairn.manifest` — a deterministic digest of `(client, image_name, environment)`.
`BR-DEPLOY-009a` and `BR-BUILD-001` still stand unamended and no environment name reaches the
image. Retention groups per manifest after all, so the shared-pool consequence recorded in the
entry below no longer applies.

Brian's naming call, taken on a recommendation: the key is `manifest`, not `environment`. An
opaque value under an `environment` key would still announce that the image is bound to one,
moving the implied intent up a level rather than removing it. The digest covers the full triple.

The id must never enter the input hash, on the same footing as `series` (`ADR-032`) — were it an
input, renaming an environment would invalidate every existing image. Both the original
rejection and its answer are kept visible in `ADR-079`; the digest is recorded there as
obfuscation, not secrecy, and nothing relies on it being otherwise.

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
