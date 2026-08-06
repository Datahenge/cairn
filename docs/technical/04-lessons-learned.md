---
status: authoritative
owner: technical
purpose: Index for durable technical findings about the tools cairn builds on; routes to the topic file that owns each finding.
---

# Lessons Learned

Durable technical findings — mechanisms understood, claims measured, mistakes worth not
repeating. Distinct from the neighbouring documents by *kind*, not topic:

| Document | Answers |
| --- | --- |
| `docs/requirements/` | What the system must do (`BR-<AREA>-NNN`) |
| `docs/adr/`, `docs/decisions/` | What we chose, and why (`ADR-NNN`) |
| `docs/discussions/discussion-log.md` | How the design conversation unfolded, chronologically |
| **this set** | What turned out to be **true** about the tools we build on |

Findings are written to survive a change of direction: they hold whether or not the
decision that prompted them stands. Each cites the `BR`/`ADR` IDs it illuminates, and
marks whether it was **measured** or **reasoned**.

Split by topic (2026-08-03) once the single file grew past the point of being loadable for
a narrow task. Add new findings to the topic file they belong to; add a new topic file here
only when a finding doesn't fit any existing one.

_Last updated: 2026-08-06_

## Topics

| File | Covers |
| --- | --- |
| [04a-lessons-build-engines.md](04a-lessons-build-engines.md) | BuildKit, buildx, buildah — what each is and how they relate |
| [04b-lessons-caching-and-provenance.md](04b-lessons-caching-and-provenance.md) | Cache invalidation (`CACHE_BUST`), provenance capture, image labelling, dangling/stage images |
| [04c-lessons-process-notes.md](04c-lessons-process-notes.md) | Method and process — sandbox constraints, convention enforcement, corrections worth remembering |
| [04d-lessons-docker-and-host-storage.md](04d-lessons-docker-and-host-storage.md) | Docker Engine vs. containerd storage, host disk layout, diagnosing a live VPS disk-space incident |
