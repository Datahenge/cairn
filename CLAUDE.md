# cairn — Working Agreement (Scribe Coding)

This project follows **Scribe Coding** — Document-Driven AI Development:
<https://datahenge.com/blog/document-driven-ai-development/>

Documentation is a living contract that **precedes and governs** code. These are the
ground rules for how the human and the AI collaborate here. They bind the AI.

## Core tenets

- **Documentation-first.** Before writing or changing any code, read the relevant
  requirements and state which `BR` IDs the change implements.
- **Single source of truth.** Requirements documents are authoritative. When a design
  changes, update the docs *in the same change* so they remain authoritative.
- **Never Assume.** If a requirement is not documented, **ask the user before
  implementing**. Do not invent behavior to fill a gap.
- **Bounded scope.** ERPNext / DevOps / data tooling — a domain the author knows well.
  Not an exploratory project.
- **Small modules.** Only once the docs are solid does coding begin — one small module
  at a time, with close human review.

## Dual identifier system

- **`BR-<AREA>-NNN` = requirements** — "the system MUST…". The authoritative statement
  of *what* the system does. Referenced by code docstrings and tests.
- **`ADR-NNN` = decisions** (Architecture Decision Records) — "we chose X because…".
  The rationale/architecture record. Requirements cite the decisions that shaped them.

Both systems are kept (as in `cofferdam-app`, which uses `BR-API-001` alongside ADRs).

**BR areas:** `VEND` vendoring · `BUILD` image build · `DEPLOY` reconcile/lifecycle ·
`DATA` data-plane boundary (off-limits; sole DB touch is `bench migrate` / opt-in
`install-app`) · `CFG` environment-specific config on the sites volume (site config,
local secrets, local policy files — e.g. a cofferdam policy file) · `CLI` command surface.

> cairn is **cofferdam-unaware** (`ADR-019`). cofferdam is only ever a
> non-normative example of a local config file; the tool never depends on or special-
> cases it.

## Artifacts and where they live

| Path | Purpose | IDs |
| --- | --- | --- |
| `docs/requirements/` | Numbered requirement docs + ToC (`00-overview.md`, then per-area) | `BR-<AREA>-NNN` |
| `docs/01-decisions-closed.md`, `docs/02-decisions-open.md` | Decision register (ADRs) | `ADR-NNN` |
| `docs/03-discussion-log.md` | Narrative design record | — |
| `docs/04-lessons-learned.md` | Durable technical findings about the tools we build on; each marked *measured* or *reasoned* | — |
| `docs/CHANGELOG.md` | Living-documentation revisions | — |
| `docs/plans/` | Implementation plans, downstream of requirements | — |
| `frappe_docker/` | Vendored upstream, **read-only** (ventwig, `ADR-007`) — never edit | — |

## Workflow (Scribe Coding phases)

1. **Ground rules** — this file.
2. **Requirements co-creation** — via dialogue; assign `BR` IDs; multiple passes for
   gaps, duplication, and contradiction.
3. **Living documentation** — record revisions in `docs/CHANGELOG.md`; reconcile
   conflicts against the docs rather than interrupting the user.
4. **Modular code** — only once requirements are solid; one small module at a time;
   each module cites the `BR` IDs it implements.
5. **Testing** — tests reference the same `BR` IDs as the code.
6. **User documentation** — `README.md` / `USAGE.md` last. Internal docstrings cite
   `BR` IDs; external/API descriptions omit internal identifiers.

## For the AI (operating rules)

- State the `BR` IDs a change implements **before** writing the code.
- Ask when requirements conflict, are ambiguous, or are missing — do not guess.
- When a design changes, update the affected requirements **and** `docs/CHANGELOG.md`
  in the same change.
- Do **not** begin code for a pillar whose requirements are not yet solid.
- Never edit the vendored `frappe_docker/` tree; manage it only via ventwig.
