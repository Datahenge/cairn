---
status: authoritative
owner: technical
purpose: Index for cairn's implementation/configuration/operations documentation.
---

# Technical Documentation

Three kinds of document answer three different questions:

| Tree | Answers |
|---|---|
| `docs/requirements/` | WHAT the system must do (`BR-<AREA>-NNN`) |
| **`docs/technical/`** (this tree) | HOW it's built, configured, and operated |
| `docs/adr/`, `decisions/` | WHY a consequential or lightweight choice was made (`ADR-NNN`) |

## Contents

| # | Document | Covers |
|---|---|---|
| 00 | [00-coding-standards.md](00-coding-standards.md) | Naming, lint/format tooling, design patterns, libraries |
| 01 | [01-documentation-conventions.md](01-documentation-conventions.md) | Markdown headers, documentation levels, sprawl control |
| 02 | [02-dorwin-analysis-and-hardin-version.md](02-dorwin-analysis-and-hardin-version.md) | Prose-compression technique (optional, on request) |
| 04 | [04-lessons-learned.md](04-lessons-learned.md) | Index — durable technical findings about the tools cairn builds on, split by topic (04a/04b/04c) |
| 05 | [05-implementation-index.md](05-implementation-index.md) | Current implementation inventory: what's built, where, how tested |
| 25 | [25-documentation-authority.md](25-documentation-authority.md) | Which document owns which topic, and reading order |

Numbering has intentional gaps (00, 01, 02, 04, 05, 25) so future documents can be inserted
without renumbering.

## Reference material

Also in this tree, but reference rather than the numbered core above:

- [high-level-motivations-and-workflows.md](high-level-motivations-and-workflows.md) — the "why" document, no requirement numbers

Choosing a container registry and GHCR specifically are user-facing topics — migrated to
[`userdocs/registry/choosing-a-registry.md`](../../userdocs/registry/choosing-a-registry.md)
and [`userdocs/registry/ghcr-setup.md`](../../userdocs/registry/ghcr-setup.md) (`DOCS-01`).

Exploratory or informal write-ups belong in [../discussions/](../discussions/) instead of here.
