---
status: authoritative
owner: technical
purpose: Coding standards, naming conventions, lint/format tooling, and chosen design patterns for cairn.
---

# Coding Standards

This document owns HOW code is written and enforced. Requirement-ID citation discipline (how
code links back to `BR-<AREA>-NNN` requirements) is owned by `AGENTS.md` — do not duplicate it
here.

## Language / Runtime

- Python ≥ 3.11 (`requires-python = ">=3.11"` in `pyproject.toml`).
- The owned `src/cairn/recipe/frappe_docker/` tree (renamed from `vendored/`, `ADR-059`) is a
  Docker build recipe — Containerfile and shell, not Python — and is not linted to this
  document's Python standard. It is otherwise ordinary cairn source: freely edited, reviewed
  like any other change.

## Naming Conventions

- Modules: `snake_case`, one concern per module (`registry.py`, `descriptor.py`, `reconcile.py`,
  `systemd.py`, `vendor.py`, `images.py`, `provision.py`, ...).
- CLI console scripts: `cairn-build` and `cairn-adopt` (`ADR-046`) — hyphenated, matching PyPI/
  console-script convention, not the importable package name (`cairn`).
- Tests: `test_<module>.py`, mirroring the module under test; `tests/test_conventions.py`
  tests project *conventions*, not behavior, and is named accordingly.

## Formatting & Linting

| Tool | Purpose | Command |
|---|---|---|
| `ruff format` | Formatting | `ruff format .` |
| `ruff check` | Linting (`E`, `F`, `I`, `UP`, `B`, `SIM`, `RUF` rule sets; line length 100) | `ruff check .` |
| `pytest` (+ `pytest-cov`) | Test suite and coverage | `pytest` |

These must pass before a change is considered done — see `open/OPEN_WORK.md`'s `done` status
definition. No `mypy` or other type checker is wired in yet.

## Requirement-ID Leakage Guard

The "IDs never in user-facing text" rule (`AGENTS.md`) lives only in prose until something
enforces it — and prose-only rules get violated silently until a human happens to spot the
output. cairn already has this guard: `tests/test_conventions.py` parses every Python file under
`src/cairn/` with `ast`, collects every string-literal node that is **not** a module/class/
function docstring, and regex-matches `\b(?:BR-[A-Z]+-\d+|ADR-\d+)` against the rest. It exists
because the rule was broken twice in practice — first in Typer `--help` output, then in a
runtime error message — and both times a human caught it, not a test.

## Design Patterns

- Thin orchestration over external tools (`docker`/`buildx`/`podman`/`compose`/`bench`/`git`) —
  cairn shells out or speaks a documented API; it does not reimplement what those tools do
  (`ADR-024`, `ADR-036`).
- Provenance-as-labels: every build stamps OCI/`com.datahenge.cairn.*` labels read back later by
  `images`/`retag`/rollback, rather than a separate state file (`ADR-030`, `ADR-032`).

## Libraries & Packages

| Library | Purpose | Rationale |
|---|---|---|
| `typer` | CLI framework for both `cairn-build` and `cairn-adopt` | `ADR-003` |
| `ruff` | Lint + format | Single fast tool, no separate formatter needed |
| `pytest` / `pytest-cov` | Test runner + coverage | Standard choice |

No third-party HTTP client for the registry — a small `urllib`-based client was chosen
deliberately over adding a hard binary dependency (`ADR-036`).

## Engineering Rules

- Never store, generate, or log secret values — reference and wire only (`ADR-017`).
- Never touch the data plane — no SQL client, no `bench execute`, no data movement, no code path
  that could (`ADR-022`). This is a correctness invariant, not a style preference.
- Log to stdout/stderr only in unattended contexts; a build transcript is the sole exception, and
  only when attended at a terminal (`ADR-031`).
