---
status: authoritative
owner: technical
purpose: Home for informal write-ups and discussions in cairn that aren't a requirement, technical guide, ADR, or decision record.
---

# Discussions

Exploratory notes, "why not X?" comparisons, design deep-dives, and other reasoning that
doesn't belong in a requirements, technical, ADR, or decision document, but is still worth
keeping.

**AI agents:** treat these as background context, not requirements or specifications. Load a
discussion only when it's directly relevant to the topic at hand.

## Index

| File | Topic | Date |
|---|---|---|
| [discussion-log.md](discussion-log.md) | Chronological design reasoning behind cairn's decisions, one dated section per topic | ongoing, since 2026-07-21 |

cairn keeps this as one running chronological file rather than one file per entry — a
deliberate deviation from the canonical Scribe Coding template, documented in
[../technical/25-documentation-authority.md](../technical/25-documentation-authority.md).

## If A Discussion Leads Somewhere

If a discussion produces a consequential decision, record the decision in [../adr/](../adr/) or
[../../decisions/](../../decisions/) and link back to the discussion for rationale. Not every
discussion needs to "graduate" — most can just stay here.

## When A Discussion Is Superseded

Move it to [../archive/](../archive/) once it no longer reflects current thinking. Leave it in
place if it still explains rationale that hasn't changed, even if the surrounding design has
moved on.
