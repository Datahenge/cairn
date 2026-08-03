---
status: authoritative
owner: technical
purpose: ADR-031 — Three execution contexts; a build transcript only when nobody else owns the record
---

# ADR-031 — Three execution contexts; a build transcript only when nobody else owns the record

**Decided:** 2026-07-25
`ADR-026` forbade custom log files outright. Brian's first real `cairn build` showed the
cost: minutes of engine output in a terminal emulator, unscrollable, and gone forever on
a stray `clear` unless he had thought to `tee` it. The fix is not to weaken the rule but
to notice that "target vs. not" was the wrong axis. There are **three** contexts, and the
question that separates them is **does something else already own and retain the record?**

| Context | Owner of the record | Behavior |
| --- | --- | --- |
| Target daemon (systemd unit/timer) | journald | stdout/stderr only |
| Unattended CLI (CI — e.g. GitHub Actions) | the CI system's log viewer | stdout/stderr only |
| **Attended CLI** (human at a terminal) | **nobody** | terminal **and** a transcript file |

The CI row is the one that proves the principle. A GitHub Actions runner *does* have a
writable filesystem, so "we cannot write" would be a false rationale. The real reason is
that the runner is ephemeral — a file evaporates at job end unless explicitly uploaded —
while Actions already provides search, permalinks and retention over the captured stream.
A transcript there is redundant at best, and an uncollected file at worst.

Consequences:
- **One test resolves all three.** Neither journald nor a CI runner allocates a TTY, so a
  single `isatty()` check on stderr lands correctly in every context. Explicit
  `--transcript <path>` / `--no-transcript` remain, for when the proxy is wrong (a piped
  attended run, `script`, or a CI job that genuinely wants an artifact to upload).
- **Attended builds force `--progress=plain`.** BuildKit's default TTY display redraws
  lines in place with ANSI escapes — which is *why* scrollback was useless, and would
  make a teed file unreadable. Plain progress is append-only. Nothing changes in the
  other two contexts: BuildKit already defaults to plain with no TTY.
- **Transcripts are disposable diagnostics, not project artifacts.** They default under
  `/tmp/cairn-<uid>/` — self-cleaning, and outside any source tree, consistent with
  `BR-BUILD-011`'s refusal to write markers into cairn's own tree. A `last-build.log`
  symlink and printing the path at **both** start and end solve discoverability without
  requiring anyone to memorise a path; printing at the start also means the path survives
  a Ctrl-C or a lost terminal. `transcript_dir` in build config (`BR-CFG-008`) buys
  durability for anyone who wants history beyond a reboot.

*(BR-CLI-016, BR-CLI-017, BR-CFG-008, BR-DEPLOY-019, amends ADR-026)*
