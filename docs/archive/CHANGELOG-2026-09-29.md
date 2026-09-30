---
status: archived
owner: technical
purpose: Archived tail of docs/CHANGELOG.md — entries from 2026-09-29 (6 entries).
---

# Changelog archive — 2026-09-29

Relocated from `docs/CHANGELOG.md` on 2026-09-29 to keep that file under its word-count
budget (`.docs_check_allowlist`), by `tools/changelog_rotate.py`. Content only — nothing
rewritten, nothing summarized. `docs/CHANGELOG.md` carries current entries; this file is
historical-only per `docs/archive/README.md`.

## Index

- 2026-09-29 (`changelog_rotate.py` refuses an out-of-order file)
- 2026-09-29 (`ADR-079`: the client is stamped on the image, the environment is not)
- 2026-09-29 (build-machine retention: decisions taken, `W-041`/`W-042` filed)
- 2026-09-29 (v16 PDF generation: findings recorded, `W-040` filed)
- 2026-09-29 (`nano` added to the image's base apt list)
- 2026-09-29 (Frappe queue topology recorded as a lesson)

---

## 2026-09-29 (`changelog_rotate.py` refuses an out-of-order file)

Tooling calibration — no requirement, decision, or `BR` ID (`01-documentation-conventions.md`'s
process/product rule). `ai/tools/changelog_rotate.py` gains `ordering_objection` and an
`OutOfOrder` refusal; `tests/test_changelog_rotate.py` gains five tests.

Rotation selects entries **positionally**, off the end of the file, which is the oldest material
only while the file is genuinely newest-first. It had never checked that against the dates it
already parses, so one out-of-order insertion would have silently archived recent work — the
same class of quiet wrong answer as the 2026-08-20 no-op. Brian pointed at the Foundation
project's `tools/changelog_archive.py`, whose equivalent guard exists because that premise
actually broke there. Entries sharing a date are not an objection: position is the legitimate
tiebreak, and the live file routinely carries several per day.

---

## 2026-09-29 (`ADR-079`: the client is stamped on the image, the environment is not)

New `docs/adr/079-the-client-is-stamped-on-the-image-the-environment-is-not.md`, indexed in
`docs/adr/README.md`. `BR-BUILD-011` amended; `ADR-030`'s schema gains
`com.datahenge.cairn.client`. `OQ-004` resolved; `W-042` and the implementation index updated.
**No code changed** — the requirement is deliberately ahead of it, and the Build row now records
that `build.provenance_labels` does not yet emit the label.

Resolves the collision in the entry below. Brian ruled that neither side gives: `BR-DEPLOY-009a`
and `BR-BUILD-001` stand unamended, retention groups by `(client, image_name)` rather than
`ADR-052`'s full triple, and the shared pool that follows is accepted. Rationale, rejected
alternatives, and the accepted residual risk live in `ADR-079`.

Two corrections that changed the work: the client was **not** already on the image (only
`image_name` is), so a new label is required rather than free; and the namespace in a tag is a
`[cairn.registry]` coordinate, not the client.

---

## 2026-09-29 (build-machine retention: decisions taken, `W-041`/`W-042` filed)

New `OQ-004`-`OQ-006` in `docs/open/OPEN_QUESTIONS.md`; new `W-041`, `W-042` in
`docs/open/OPEN_WORK.md`; `W-020` narrowed to its schedule half. No code changed.

Brian asked why 11 pushed images were lingering on the Life Scientific test VPS. Not an error:
`prune.select` keeps the newest `--keep` **per input hash**, and with 11 distinct hashes every
image is the newest of its group. There is no retention on any other axis, `--keep` has `min=1`,
and nothing in `src/` invokes an engine-level prune, so growth is monotonic.

**Settled by Brian**, recorded on `W-042`: `[retention]` in the existing `/etc/cairn/builder.toml`
rather than a new `build.toml`; the axis is the manifest, not `series`; per-manifest `keep_last`
coexists with per-input-hash `--keep`, both applying; `require_pushed` is a knob, leaving
`ADR-072` intact; `[registry.retention]`'s vocabulary and `enabled = false` default are mirrored.
Brian's argument for count over age exposed the same defect in the shipped registry role — `W-041`.

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
