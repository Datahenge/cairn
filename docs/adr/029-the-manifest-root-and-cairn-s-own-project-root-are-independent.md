---
status: authoritative
owner: technical
purpose: ADR-029 — The manifest root and cairn's own project root are independent
---

# ADR-029 — The manifest root and cairn's own project root are independent

**Decided:** 2026-07-24
`cairn.toml` describes a **deployment**; cairn's project root (the `pyproject.toml`
carrying `[tool.ventwig]`, and the vendored `frappe_docker/` beside it) describes the
**tool**. `BR-BUILD-011` already separates them — markers may go to the "deployment
working directory" but never into cairn's "own installation or source tree".

**Decision:** the two are resolved by independent searches. The manifest is `--manifest`
if given, else the nearest `cairn.toml` walking **up from the working directory**. The
vendored tree stays anchored to cairn's own root. They coincide today (development from
the repo) and stop coinciding the moment cairn is `pip install`-ed and run against a
deployment directory elsewhere — which requires no code change under this decision.

**Build config layers** in the same spirit: `~/.config/cairn/builder.toml` (renamed from
`config.toml`, `ADR-041`) holds machine-wide defaults (e.g. `engine`, `ADR-027`), and an
optional `cairn.local.toml` **beside the manifest** overrides it key-by-key, so
per-deployment settings travel with the deployment while the portable `cairn.toml` stays
free of them (`BR-CFG-008`).

**Closed 2026-07-25:** the vendored tree now lives at `src/cairn/vendored/frappe_docker` —
inside `src/cairn` — so the wheel carries it without any special packaging step (`ADR-007`,
`ADR-018`). A `pip install`-ed cairn has a vendored tree to build from.
*(BR-CFG-012, BR-CLI-014, BR-BUILD-011)*
