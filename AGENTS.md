# cairn — Working Agreement (Scribe Coding)

This project follows **Scribe Coding** — Document-Driven AI Development:
<https://datahenge.com/blog/document-driven-ai-development/>

Documentation is a living contract that **precedes and governs** code. These are the
ground rules for how the human and the AI collaborate here. They bind the AI.

## The One Rule

Docs precede code. If a behavior is not described in `docs/`, it is not implemented. If a
requirement is ambiguous, check `open/OPEN_QUESTIONS.md` and `open/OPEN_DECISIONS.md` — do not
infer behavior from an unstated preference. If the question is new, add it there and ask Brian
before writing code.

## Before Any Task

1. Read `CURRENT_CONTEXT.md` first — it routes to the smallest relevant document.
2. Consult `docs/technical/25-documentation-authority.md` to find which document owns the topic
   in scope.
3. Load only the document(s) the index points to. Do not scan the full `docs/` tree by default.
4. For non-trivial changes, state which `BR-<AREA>-NNN` requirement IDs the change implements
   before writing code.

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
  The rationale/architecture record, split by weight into `docs/adr/` (consequential) and
  `decisions/` (lightweight). Requirements cite the decisions that shaped them.

Both systems are kept (as in `cofferdam-app`, which uses `BR-API-001` alongside ADRs).

**BR areas:** `VEND` vendoring · `BUILD` image build · `DEPLOY` reconcile/lifecycle ·
`DATA` data-plane boundary (off-limits; sole DB touch is `bench migrate` / opt-in
`install-app`) · `CFG` environment-specific config on the sites volume (site config,
local secrets, local policy files — e.g. a cofferdam policy file) · `CLI` command surface ·
`DOCS` published documentation · `REG` registry lifecycle (provisioning, retention, garbage
collection for the `cairn-registry` role, `ADR-048`).

> cairn is **cofferdam-unaware** (`ADR-019`). cofferdam is only ever a
> non-normative example of a local config file; the tool never depends on or special-
> cases it.

## Coding Standards

Naming conventions, lint/format tooling, design patterns, and library choices live in
`docs/technical/00-coding-standards.md`, not here. This section only covers requirement
traceability.

- Cite `BR-<AREA>-NNN` identifiers in docstrings and test names for every non-trivial rule.
- Requirement IDs are internal — see the "IDs never reach a user" rule below for where they
  may and may not appear.
- Update the relevant requirement, technical, or decision document in the same change that
  alters behavior, scope, or design.
- Record consequential decisions in `docs/adr/`; lighter, easily-reversible decisions in
  `decisions/`.
- Record completion judgments in `docs/technical/05-implementation-index.md`'s `Completion
  Judgment` column the moment they're reached, including sessions with no code change.

## Artifacts and where they live

| Path | Purpose | IDs |
| --- | --- | --- |
| `CURRENT_CONTEXT.md` | Session router; read first in a fresh session | — |
| `docs/00-project-scope.md` | Purpose, pillars, what it is/isn't, principles | — |
| `docs/requirements/` | Numbered requirement docs + ToC (`00-overview.md`, then per-area) | `BR-<AREA>-NNN` |
| `docs/technical/` | Coding standards, doc conventions, lessons learned, implementation index, documentation-authority map, plus ad-hoc reference docs (`ABOUT_GHCR.md`, `ABOUT_REGISTRIES.md`) | — |
| `docs/adr/` | Consequential decisions, one file per `ADR-NNN` | `ADR-NNN` |
| `decisions/` | Lightweight dated decisions, one file per `ADR-NNN` | `ADR-NNN` |
| `docs/archive/` | Fully-retired ADRs/decisions, with a forwarding stub left at the original path | — |
| `docs/discussions/discussion-log.md` | Narrative design record | — |
| `open/OPEN_QUESTIONS.md`, `open/OPEN_DECISIONS.md`, `open/OPEN_WORK.md` | Live queues: unresolved questions, pending/deferred decisions, outstanding work | — |
| `scratch/` | Temporary working notes; promote or delete | — |
| `docs/CHANGELOG.md` | Living-documentation revisions (requirements + decisions + discussion) | — |
| `CHANGELOG.md` (root) | Software release history | — |
| `docs/plans/` | Narrative implementation plans, downstream of requirements | — |
| `userdocs/` | Published end-user documentation (mkdocs-material → GitHub Pages, `ADR-045`) — the only tree a user ever sees | — |
| `src/cairn/vendored/frappe_docker/` | Vendored upstream, **read-only** (ventwig, `ADR-001`) — never edit | — |

## Workflow (Scribe Coding phases)

1. **Ground rules** — this file.
2. **Requirements co-creation** — via dialogue; assign `BR` IDs; multiple passes for
   gaps, duplication, and contradiction.
3. **Living documentation** — record revisions in `docs/CHANGELOG.md`; reconcile
   conflicts against the docs rather than interrupting the user.
4. **Modular code** — only once requirements are solid; one small module at a time;
   each module cites the `BR` IDs it implements.
5. **Testing** — tests reference the same `BR` IDs as the code.
6. **User documentation** — `README.md` / `userdocs/` last. See the identifier rule below;
   it applies from the first line of code, not from this phase.

## When Something Is Ambiguous

1. Check `open/OPEN_QUESTIONS.md` and `open/OPEN_DECISIONS.md` — the question may already be
   tracked.
2. If unresolved, add it and ask Brian. Do not implement speculative behavior while waiting
   for an answer.

## Documentation Hygiene

Follow `docs/technical/01-documentation-conventions.md` for status headers and sprawl control
before creating a new Markdown document. Use `scratch/` for notes that aren't yet worth
keeping. Run `tools/docs_check.py` before considering a documentation change complete.

If Brian asks for a "Dorwin Analysis," see
`docs/technical/02-dorwin-analysis-and-hardin-version.md` and produce a Hardin Version.

## For the AI (operating rules)

- State the `BR` IDs a change implements **before** writing the code.
- Ask when requirements conflict, are ambiguous, or are missing — do not guess.
- When a design changes, update the affected requirements **and** `docs/CHANGELOG.md`
  in the same change.
- Do **not** begin code for a pillar whose requirements are not yet solid.
- Never edit the vendored `src/cairn/vendored/frappe_docker/` tree; manage it only via
  `cairn vendor sync` (which wraps ventwig).
- **`BR`/`ADR` IDs are internal — they never reach a user.** They belong in docstrings,
  comments, tests, commit messages, and `docs/`. They MUST NOT appear in **anything a
  user can see**: CLI `--help` text, error messages, warnings, progress output,
  `README.md`, `userdocs/`. This binds from the first line of code, not from Phase 6.
  When tempted to cite an ID in a message, state the *reason* instead — "each app must
  appear exactly once — the list is an ordered install sequence" tells the user something;
  "(BR-BUILD-003)" tells them nothing.
  `tests/test_conventions.py` enforces this by parsing every non-docstring string in the
  package. If it fails, the **message** is wrong, not the test.

## Mutable Methodology

Scribe Coding is a working baseline, not a fixed template. Refine it when repeated friction
reveals a better pattern; note the change in `docs/CHANGELOG.md`.
