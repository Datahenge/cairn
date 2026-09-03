# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-09-03 (`02-build.md` split; `02a-build-tagging.md` is new)

`docs/requirements/02-build.md` reached its 2200-word ceiling admitting `BR-BUILD-019`
(previous entry). The bump taken then is retired one day later in favour of a split, at
Brian's direction.

The bump's own note guessed that "Private `github.com` apps" was the section to move.
Measurement disagreed: that section is 486 words, while "Cache & tagging" is 887 — 39% of
the file and nearly double the guess. "Cache & tagging" moved instead, to the new
`02a-build-tagging.md`, carrying `BR-BUILD-007`, `008`, `014`, `014a`, and `018`. This is the
same lesson the 2026-08-18 `06-cli.md` split recorded — measure the sections rather than guess
which one grew — and it is now recorded twice, which is the argument for measuring first.

The split is by *topic*, not merely by size: `02a` owns how an image is **named and reused**
(cache invalidation, the deterministic primary tag, input-hash deduplication, the ownership
marker), and `02-build.md` keeps what a build **is** (manifest inputs, ref resolution,
invocation, provenance, the reproducibility bar, and the `github.com` credential rules).

No requirement was renumbered, reworded, or withdrawn — IDs are stable across a move. The
spine is ~1419 words and `02a` ~1011, so the allowlist override is retired outright rather
than re-pointed, matching how `06-cli.md`'s was handled. `00-overview.md`'s area table gains
an `02a` row, `25-documentation-authority.md` gains an authority row, and
`05-implementation-index.md`'s Build and Images/prune rows now cite the document that
actually owns the requirement they implement.

---

## 2026-09-02 (frappe clone authenticates; `ADR-077`, `BR-BUILD-019`)

A `cairn-build build` on the Life Scientific test VPS failed in the builder stage at
`bench init`, with git's `could not read Username for 'https://github.com'`. Diagnosis:
GitHub refused an *unauthenticated* git operation from that host's IP — `GET /info/refs`
returned `200`, the protocol-v2 `POST /git-upload-pack` returned `401` with
`www-authenticate: Basic realm="GitHub"`. The repository is public; anonymous access is
rate-limited per IP and is not a guaranteed floor.

`ADR-077` records the decision and its rejected alternatives. `BR-BUILD-016`'s closing
paragraph — which excluded frappe on the reasoning that "a token has no safe channel to
reach it" — is replaced. Two errors in that reasoning: it conflated frappe's URL (which
must stay a plain build-arg, since provenance depends on it) with frappe's credential
(which needs no build-arg at all), and `apps.json` had been demonstrating the safe channel
all along. The exclusion was also only half-observed in practice: `resolve.resolve_manifest()`
already tokenizes frappe's `ls-remote` exactly as it does every app's, so only the
in-container clone was ever anonymous.

`BR-BUILD-016`'s "both places" clause becomes three. New `BR-BUILD-019` keeps the token
optional — a build with none configured proceeds anonymously with a warning — and requires
cairn to name `$CAIRN_GITHUB_TOKEN` when a build fails on an anonymous refusal, rather than
passing through git's message, which names a terminal prompt that was never the problem.

Brian's calls at decision time: token optional rather than mandatory (requiring one would
fail every manifest with no private app, and every timer provisioned without the
`EnvironmentFile=-` token file `ADR-065` permits); and a `credential.helper` reading the
mount rather than a `url.insteadOf` rewrite, which would write the literal token into a
gitconfig file and leave it in the builder layer. `doctor` is unchanged — detecting this
pre-build would mean shelling out to a container, which is not what a host-side tool is for.

`BR-BUILD-017`/`-018` were not available: `-017` is reserved by the git-mirror plan
(`W-009`, `ADR-044`) and `-018` by `ADR-061`. The mirror is complementary, not a
substitute — as scoped it covers `[[cairn.apps]]` entries, not frappe, and its
start-of-build `git fetch` is still a `github.com` operation from the same IP.

---

## 2026-08-20 (orientation pages promoted; README rewritten)

`userdocs/index.md` is replaced by the funnel-ordered rewrite from `docs/scratch/`, and
`why-cairn.md` is new. Both follow `26-userdocs-style.md`. The old front page opened with "a
thin, opinionated wrapper" (§3.4's verbatim *before* example) and carried "Two pillars",
"low-thought", "a strict data-plane boundary", and "it ships code, not data" — all four of
§3.3's banned-by-example slogans — plus a project-status admonition inventorying unverified
pages, which §6 says must not appear on `index.md`.

Two changes to the drafts as promoted. The mermaid diagram is dropped: `mkdocs.yml` configures
`pymdownx.superfences` with no mermaid custom fence, so it would have rendered as a literal code
block. And `why-cairn.md`'s sample `cairn-build images` listing is replaced with prose, because
it was composed rather than captured — faithful to `images.render()`'s shape but missing the
per-image line that function always emits, which is exactly the drift §5 warns about. This
workstation has no container engine, so no real capture was possible; the page's footer says so.

Links are retargeted at today's page tree rather than the funnel filenames the drafts assumed,
per `W-039`. `docs/scratch/workflow.md` stays in scratch: it depends on `concepts.md` and
`install.md`, which do not exist yet.

The root `README.md` is rewritten in the same pass, at Brian's direction: mermaid diagram
removed, slogans out, and a "How it works" paragraph that says what actually happens instead of
asserting that it is magic. `README.md` is outside `26-userdocs-style.md`'s scope by that
document's own first paragraph, but the voice rules were applied anyway.

---

## 2026-08-20 (`docs_check.py` gains DOC005: unresolved link fragments)

`docs_check.py` verified that a link's target file existed but never that its `#anchor`
resolved, which is how `ghcr-setup.md` pointed at `#what-it-costs` while the heading was "What
it costs — read this before you push several images". Found by hand earlier the same day; now
mechanical.

Both slug conventions are accepted for every heading, because `docs/` is read on GitHub and
`userdocs/` through mkdocs and the two disagree: python-markdown drops the em dash and collapses
the surrounding spaces into one hyphen, GitHub deletes it in place and turns each remaining
space into its own. Accepting both catches an anchor that exists under *neither*, which is what
an invented fragment looks like, without inventing false positives. `attr_list` ids, hand-written
HTML anchors, duplicate-heading suffixes, and code spans in headings are all handled; a `## ` line
inside a fenced block is not an anchor.

44 fragment links across `docs/` and `userdocs/` — all currently resolve. `tests/test_docs_check.py`
is new (10 tests), including the historical break as a regression test.

---

## 2026-08-20 (`W-034` closed, both halves)

The crash originally reported was real and Brian fixed it on 2026-08-06 in `cb1ffd5`, which added
`parse_changelog`'s `header_line == FOOTER_HEADING` guard — the same day the item was filed,
which is why the 2026-08-18 re-check could not reproduce it. That was never recorded, so the row
stayed open on a "close if it stays quiet" clause for two weeks.

The second half is fixed here: `build_plan` returned `None` both when the file was under budget
and when it was over budget with nothing movable, and `main` printed the same reassuring line for
both. It now raises `NothingToMove`, naming the file, its size, its ceiling, and the two ways out.
`.docs_check_allowlist`'s stopgap note about rotation being blocked is removed, since it isn't.

---

## 2026-08-20 (`changelog_rotate.py` splits on dated headings, not on the `---` rule)

Brian: fix the parser rather than rely on the separators staying put. `parse_changelog` now
slices `docs/CHANGELOG.md` at its `## <YYYY-MM-DD>` headers. A `## ` line inside a fenced code
block is content, not a boundary, and the separator that slicing leaves attached to the end of
the preceding entry is dropped, since `render_changelog` writes one back. A file missing its
separators parses correctly and is written back out repaired. A header the tool cannot date
still raises rather than guessing, which is the one thing that should stay loud.

`tests/test_changelog_rotate.py` is new, and is the tool's first test coverage — the parser was
untested, which is why the failure was silent for weeks. Ten tests, including the exact
regression (a separator-less file parsing as one entry) and a byte-for-byte round trip against
the live changelog. Full suite: 981 passing.

No `BR` ID: `ai/tools/` is documentation-hygiene tooling, outside every requirement area.
`01-documentation-conventions.md`'s separator note is corrected in the same change, and `W-034`
records what remains — `build_plan` still reports "within budget" on every `None`, including the
`MIN_LIVE_ENTRIES` case.

---

## 2026-08-20 (changelog rotation was a silent no-op; separators restored)

Adding the two entries above put `docs/CHANGELOG.md` over its 6,500-word ceiling, and
`changelog_rotate.py` answered "within budget — nothing to rotate" while `docs_check.py` reported
`DOC002` on the same file.

Cause: `parse_changelog` splits entries on the `---` rule and nothing else. Those separators had
been dropping out of appended entries for some time, so all 23 entries parsed as one, and
`MIN_LIVE_ENTRIES` left nothing safe to archive. Restoring the separators (no content changed,
23 words added) made rotation work normally: 7 entries covering 2026-08-06 through 2026-08-18
moved to `docs/archive/CHANGELOG-2026-08-06-to-2026-08-18.md`, leaving 4,761 words live, and the
archive index, this file's footer, and `.docs_check_allowlist` updated mechanically.

The separator requirement is now stated in `01-documentation-conventions.md`, and `W-034` records
the root cause. This is not the crash `W-034` originally reported, which still has not
reproduced.

---

## 2026-08-20 (`userdocs/` navigation refactor deferred until the page catalog is known)

`26-userdocs-style.md` §2 forbids organizing top-level navigation around cairn's three roles,
and the shipped `userdocs/` tree does exactly that (`registry/`, `builder/`, `target/`). Brian
deferred the restructure until roughly 90% of the pages exist: the right grouping is easier and
more obvious to see once the full catalog of pages is known, rather than guessed at now.

Recorded as `W-039` (`deferred`) in `docs/open/OPEN_WORK.md`, and as a blockquote in §2 itself so
the rule is not read as an indictment of the current tree. The standing instruction until then:
write new pages in the new voice, place them where the current tree puts them, and do not move
navigation one page at a time.

---

## 2026-08-20 (`AGENTS.md` forks into two paths; `userdocs/` gains a style authority)

Brian: work on published user documentation follows a different set of rules than everything
else, and `AGENTS.md` now says so before it says anything else. **Path 1** is any file under
`userdocs/`; its authority is the new
[`docs/technical/26-userdocs-style.md`](technical/26-userdocs-style.md), promoted verbatim from
`docs/scratch/STYLE.md` with a status header and a paragraph placing it in the fork. **Path 2**
is everything else, governed by `AGENTS.md` unchanged. A change touching both trees is on both
paths, per file.

Brian confirmed Path 1 **layers on** rather than replaces: the style guide wins on how
documentation reads, while four invariants still bind on both paths (no internal identifiers in
user-visible text, no command or key documented without verifying it in `src/cairn/`, never
assume, and same-change `docs/CHANGELOG.md` entries). Path 1 alone does not require stating `BR`
IDs before writing.

`25-documentation-authority.md` and `ai/CURRENT_CONTEXT.md` route to the new document.

---

## 2026-08-20 (command-surface reference pages, one per binary)

`userdocs/reference/` gains **`cairn-build.md`** and **`cairn-adopt.md`** — every command and
every flag, sourced from each binary's actual `--help` output rather than from the code, so the
pages describe what a user's installed version prints. Closes the gap `reference/index.md` had
been openly deferring ("Command surface reference will land here later").

No third page was written for `cairn-registry`: `userdocs/registry/cli.md` already *is* that
page, and says so in its own first paragraph. Duplicating it would have created a second
authority for the same surface. `reference/index.md` now lists all three binaries and links the
registry entry across to where it already lives — the asymmetry is deliberate but was flagged to
Brian, since filing it under Reference for symmetry is a reasonable alternative he may prefer.

`reference/index.md` is restructured into "Command surface" and "File formats", and keeps the
rule the deferral paragraph already stated: where a page and `--help` disagree, **`--help`
wins**, because it ships with the installed version and the site does not.

**Fixed in passing:** `userdocs/registry/ghcr-setup.md` linked to
`ghcr-ownership-and-cost.md#what-it-costs`, an anchor that does not exist — the heading is "What
it costs — read this before you push several images", which python-markdown slugifies to the
full phrase. Found by an anchor-resolution sweep of the whole tree; it was the only genuine
break in 100-plus internal links. Note that `ai/tools/docs_check.py` verifies link *targets* but
not *fragments*, which is why this survived.

---

## 2026-08-20 (`ADR-076`: the primary branch is `version-16`, and there is no `main`)

Brian: cairn stays pinned to the ERPNext major it supports, so its primary branch is named for
that major — `version-16` today, `version-17` when support moves. `main` is deleted rather than
kept as a stale ancestor. Rationale and consequences in
[`docs/decisions/076-primary-branch-is-version-nn-tracking-the-erpnext-major.md`](decisions/076-primary-branch-is-version-nn-tracking-the-erpnext-major.md).

No requirement changed: `BR-DOCS-005` already said the site publishes on **the default branch**
and never named one. `.github/workflows/docs.yml` hardcoding `main` was drift from that
requirement, and is now corrected along with `mkdocs.yml`'s `edit_uri`, `pyproject.toml`'s
`Changelog` URL, and one `blob/main/` link in `userdocs/registry/index.md`.

Surfaced by a user-documentation review the same day, which found three weeks of `userdocs/`
work unpublished for exactly this reason — including `userdocs/target/operating.md`, a page
absent from the live site entirely.

**Also from that review:** `cairn-adopt prune` (`BR-CLI-028`, `BR-DEPLOY-006`) had shipped with
no user documentation at all, while the build- and registry-side prune verbs both had coverage.
`userdocs/target/operating.md` gains a "Reclaiming disk" section — the protected running image
(read from the container, not from recency, which is what makes it survive a rollback), the
volumes-and-containers exclusion, the colocated-builder image split, and why `--keep` is a grace
window rather than a rollback guarantee. No requirement changed; this documents behavior that
already matched its requirement.

**Stale verification trailers corrected.** Three pages still claimed to be written entirely
ahead of a live run, and `userdocs/index.md` still called Guides a placeholder months after a
real guide landed there. The trailers on `userdocs/target/index.md` and
`userdocs/target/operating.md` now name **which** verbs have been run against the client VPS
and which have not, rather than blanket-disclaiming the page — the split recorded in the
2026-08-19 field-verification entry above. `userdocs/index.md`'s status note is rewritten to
match and to stop overstating Reference, which covers the file formats but not the command
surface. Nothing here claims verification beyond what that entry records: `prune`, the held
state, `examine`, `setup`, and the reconcile timer all remain explicitly unproven in the
field.

---

## 2026-08-19 (field verification: inspection verbs done, the held state still open)

Brian verified `doctor`, `console`, `mariadb`, `shell`, `logs` and `restart` on the client VPS.

`BR-CLI-030`'s inspection verbs are now fully confirmed. That matters more than a checkmark:
the TTY handling (`execvp`, never `-T`) was the one thing unit tests could only approximate,
since the failure it prevents is the real MariaDB client silently entering batch mode. It
behaves as designed against the actual client.

`restart` proves more than itself. It exercises the deploy lock taken **once** across several
steps, `run_locked`, `compose stop`, and the reconcile pass that follows — so the self-deadlock
`ADR-073` predicted, and which the split into `run`/`run_locked` was written to prevent, is now
confirmed absent on real infrastructure rather than only under a test double.

What remains unverified is deliberately noted rather than rounded up: **the held state itself.**
`restart` cleared no hold because none existed, and `doctor` exercised only its OK path. Still
untested live are `stop` placing a hold, `reconcile` reporting *held* and converging nothing,
`doctor`'s WARN path, `restart` clearing a hold that genuinely exists, and a hold surviving a
reboot. That is precisely the half that can silently suspend deployments on a client host, so
it is the half worth exercising on purpose rather than encountering by accident.

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
