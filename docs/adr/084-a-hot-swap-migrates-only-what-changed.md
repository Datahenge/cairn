---
status: exploratory
owner: technical
purpose: ADR-084 — a hot swap compares schema files one by one, and skips migrate, syncs content, or migrates accordingly
---

# ADR-084 — A hot swap migrates only what changed

**Proposed:** 2026-11-24 (Life Scientific, contributed as a pull request; awaiting Brian).

**Adds:** `BR-DEPLOY-028`. **Amends:** `BR-DEPLOY-016` ("`bench migrate` runs after every image
enable" no longer holds for a hot swap whose schema files did not change). **Relates to:**
`ADR-014`, `ADR-081`, `ADR-082`, `ADR-083`.

## Context

Two things happened after `ADR-081` that it does not describe.

1. **Life Scientific's fork already skips an unneeded migrate.** Commit `7af9888` hashes the
   schema files in each app package of both images. When the hashes match, the hot swap skips
   `bench migrate` and clears the cache instead. That skip is in the code that runs on Life
   Scientific's staging target, and no document here mentions it.
2. **A one-line print format change still costs a full migrate.** The hash covers every JSON
   file, so a Print Format, a Report or a Workspace counts as schema. In Life Scientific's last
   300 staging merges, about 35 changed only files of that kind. Each paid for a full migrate,
   and a full migrate is what interrupts users on that target (`ADR-082`'s records will say by
   how much). Those files are content: Frappe imports each one by itself with
   `import_file_by_path`, and nothing about the tables changes.

There is also an ordering problem. A migrate runs before the swap, while the old code serves.
A new print format often calls a Jinja helper that only the new code has, so loading it early
breaks printing on the old code until the swap finishes.

## Decision

**Compare the two images file by file.** The fingerprint script keeps its file set (JSON,
YAML, CSV, `patches.txt`, `hooks.py`, inside each app's package) but prints one `sha256  path`
line per file instead of a single hash of them all. It is the same `docker run` against each
image as before; nothing is added to the image.

**Three outcomes.**

- **No file differs:** no migrate, clear the cache. This is `7af9888`'s behavior, now written
  down.
- **Every changed or added file matches `[deploy] content_paths`, and none was deleted:** no
  migrate. After the old backend retires, run the operator's `[deploy] content_sync` method
  with `bench execute`, passing the changed paths (relative to `apps/`) as `paths`. The new code
  is serving by then, so content that needs new code finds it. If the method fails, run
  `bench migrate` in the new backend instead, so the content is never left unloaded: by the
  next pass the stack is converged and nothing would try again.
- **Anything else** (a DocType, a fixture, `patches.txt`, `hooks.py`, a deleted file, or an
  image whose files cannot be read): migrate before the swap, as `ADR-081` decided.

**Opt-in, and the operator says what content is.** Both keys default to nothing, and without
them the content outcome never happens. cairn knows nothing about any app's layout; the
operator names the patterns (`fnmatch`, where `*` also matches `/`) and the method that loads
them. A method name is a dotted Python path run by `bench execute`, exactly as cairn already
runs `frappe.publish_realtime`.

**The record says which.** The deploy record (`ADR-082`) reports `"migrate": {"ran": false,
"content_files": N}` for a content sync, and `"content_failed": true` when it fell back.

## What it does not do

- **No partial migrate.** A change outside `content_paths` runs the whole `bench migrate`.
- **Recreate is unchanged.** It migrates after every enable.
- **cairn does not check that a pattern is content.** An operator who lists a DocType folder in
  `content_paths` gets that DocType imported without a migrate's table changes. The descriptor
  reference says so.

## Rejected alternatives

- **Bake a manifest into the image at build time.** Equivalent answer, more moving parts: the
  build would have to write it for both full and thin builds, and an image built before the
  change would have none.
- **Run the content sync before the swap,** like migrate. That is the ordering problem above.
- **Let cairn choose the import per file type.** That puts Frappe app knowledge into cairn; the
  operator's method already has it.

## Open for Brian

1. Is running an operator-named method with `bench execute` acceptable as a second data-plane
   touch, beside `bench migrate` (`ADR-022`)? It is narrower than migrate, but it is new.
2. Should the fallback to `bench migrate` after a failed content sync run in the new backend
   (as here) or halt and report?

*(BR-DATA-005, BR-DEPLOY-016, BR-DEPLOY-025, BR-DEPLOY-026, BR-DEPLOY-028)*
