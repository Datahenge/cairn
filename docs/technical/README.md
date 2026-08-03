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
| 04 | [04-lessons-learned.md](04-lessons-learned.md) | Durable technical findings about the tools cairn builds on |
| 05 | [05-implementation-index.md](05-implementation-index.md) | Current implementation inventory: what's built, where, how tested |
| 25 | [25-documentation-authority.md](25-documentation-authority.md) | Which document owns which topic, and reading order |

Numbering has intentional gaps (00, 01, 02, 04, 05, 25) so future documents can be inserted
without renumbering.

## Reference material

Also in this tree, but reference rather than the numbered core above:

- [CONFIGURATION.md](CONFIGURATION.md) — full manifest and build-config reference
- [ABOUT_REGISTRIES.md](ABOUT_REGISTRIES.md) — choosing a container registry
- [ABOUT_GHCR.md](ABOUT_GHCR.md) — GHCR specifically
- [high-level-motivations-and-workflows.md](high-level-motivations-and-workflows.md) — the "why" document, no requirement numbers

Exploratory or informal write-ups belong in [../discussions/](../discussions/) instead of here.
