# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-09-29 (v16 PDF generation: findings recorded, `W-040` filed)

New `docs/technical/04g-lessons-frappe-pdf-generation.md`, indexed from `04-lessons-learned.md`.
New `W-040` in `docs/open/OPEN_WORK.md`. No requirement or decision changed; no code changed.

Traced while answering whether v16 prefers `wkhtmltopdf` or `chrome`. It prefers `wkhtmltopdf` —
five defaults plus a patch that backfills existing rows — but `erpnext` ships nine print formats
that declare `chrome`, all of them financial statements and ledgers. v16 therefore needs both
generators, and dropping `wkhtmltopdf` to reach a newer Debian base would break documented ERPNext
behavior, not merely change PDF output.

The recipe's `INSTALL_CHROMIUM=true` does not satisfy the chrome half.
`find_or_download_chromium_executable()` never searches `PATH` — with no `chromium_path` key it
evaluates `shutil.which("")`, which is `None` — so `/usr/bin/chromium-headless-shell` is invisible
to Frappe, which instead downloads Chromium at request time into a directory that is not a volume.
The apt package is inert today.

Recorded rather than fixed. `W-040` carries two candidate shapes; **neither is chosen** — the
preference stated there is Claude's recommendation awaiting Brian's ruling, not a decision.

---

## 2026-09-29 (`nano` added to the image's base apt list)

Recipe change under `BR-VEND-001`. No requirement text changed; no new decision.

`images/Containerfile`'s base-stage `apt-get install` list now carries `nano` alongside `vim`.
Brian asked for it: editing a file inside a running container is a routine support act, and `vim`
alone is a needless obstacle when muscle memory says otherwise.

Cost, stated plainly rather than assumed negligible: this is a change to the `base` stage, so the
first build after it re-runs the whole apt/nvm/wkhtmltopdf layer for every target — the expensive
layer `ADR-059`'s staging exists to pay only once. `nano` itself is a small package; the rebuild
is the real cost, and it is paid once.

---

## 2026-09-29 (Frappe queue topology recorded as a lesson)

New `docs/technical/04f-lessons-frappe-queues.md`, indexed from `04-lessons-learned.md`. No
requirement or decision changed; no code changed.

Brian asked whether Frappe v16 had dropped the `default` queue, having noticed the recipe's
compose file names only `queue-short` and `queue-long`. It has not: `get_queues_timeout()` at
`version-16` still returns `short`/`default`/`long`. The recipe is also correct — `bench worker
--queue` takes a priority list and both worker services include `default`, so the queue is
covered by two containers under neither's name.

Recorded because the question is structurally repeatable: the service names are a lossy view of
the queue coverage, so the absence reads as a fault to anyone counting queues. The note also
captures that job timeout resolves from the queue at enqueue time, not from the worker that runs
the job — the natural follow-on wrong guess.

---

## 2026-09-28 (`gc` stops the registry instead of serving read-only)

New `ADR-078`, amending `BR-REG-009` and adding `BR-REG-009a`.

The first `cairn-registry gc` ever run against a live registry left that registry crash-looping.
`registry_compose()` expressed read-only maintenance mode as the flattened environment variable
`REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED`; distribution requires that key to be a map, and
`handlers.NewApp` panics on the flattened form before the HTTP server starts. Because `gc()` had
no `try`/`finally`, it never ran its return-to-read-write step, so the compose file kept the
variable and every later `cairn-registry start` reproduced the panic — recoverable only by
hand-editing a cairn-generated file.

`gc` now stops the registry, runs `garbage-collect` in a throwaway container against the same
`data_dir`, restarts the registry in a `finally`, and verifies it is serving before reporting
success. No `REGISTRY_*` maintenance variable is involved, so that fault class is gone; a stopped
registry is also a stronger write guarantee than read-only mode. `gc` no longer writes the compose
file at all, which removes `_write_compose`'s deliberate bypass of the overwrite protection every
other generated file gets.

**What this costs, recorded rather than glossed:** `BR-REG-009`'s promise that pulls continue
throughout the window is withdrawn — during gc the registry answers nothing. A `reconcile` tick
landing inside the window raises `ReconcileError`, deploys nothing, and succeeds on the next tick,
so a target is left alone rather than half-deployed.

The rejected alternative — keeping read-only mode and emitting
`REGISTRY_STORAGE_MAINTENANCE_READONLY: '{"enabled":true}'` so the value parses as a map — is
recorded in `ADR-078` with its reasoning: it preserves the pulls promise, but retains the twice-per-gc
recreate, a dependency on distribution's env-value parsing that cairn had already guessed wrong
about once, and `gc`'s ability to rewrite the compose file.

Two diagnostic gaps the incident exposed are closed alongside: `gc` verifies the registry is
serving before reporting success, and the operator-facing warning now says the registry is briefly
unavailable rather than that pushes are briefly refused.

---

## 2026-09-05 (github.com rate limiting documented; both paths)

Follow-up to `ADR-077`. The fix shipped, but nothing told an operator why they would want a
token for a build of entirely public repositories, which is the situation that produced the
incident.

**Path 2.** New `docs/technical/04e-lessons-github-rate-limits.md`, a durable finding indexed
from `04-lessons-learned.md`. Records what was measured (rate limits are keyed on the caller,
not the repository; the refusal arrives as a `401` credential challenge rather than a `429`;
protocol v2 meters only the `git-upload-pack` POST, so a `curl` against `/info/refs` returns
`200` while a clone fails) separately from what was reasoned (a credential helper
authenticates on the retry; `CACHE_BUST` makes cairn clone more often than a hand-run build).
It also records what could **not** be established: GitHub publishes no figures for
git-over-HTTPS, and a rate limit is indistinguishable from an abuse block at the client, so
no threshold in that document is stated as known.

The `/info/refs` finding is the one worth re-reading. That probe was run early in diagnosis,
returned `200`, and sent the investigation toward Docker networking for about an hour.

**Path 1.** `userdocs/reference/builder-config.md`'s "Private `github.com` apps" is retitled
"Authenticating to `github.com`" and gains a "Why a public build can still need a token"
subsection, since the old title told a reader with public apps that the section was not for
them. `userdocs/reference/manifest.md`'s pointer is reworded to match and its anchor updated.
`userdocs/builder/index.md` gains a note admonition beside the build command, which is where
a first-time builder meets this.

Terminal output on those pages is real, taken from the failing build and from the shipped
message strings, per the userdocs style rules. The site builds under `mkdocs --strict` and
both inbound anchors resolve.

`builder-config.md` carried 21 em dashes before this change and still does. They predate the
style guide, and restyling the whole page was out of scope here; only the added text follows
the current rules.

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
