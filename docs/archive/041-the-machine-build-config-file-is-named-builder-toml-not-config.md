---
status: archived
owner: technical
purpose: ADR-041 — The machine build-config file is named `builder.toml`, not `config.toml`
---

# ADR-041 — The machine build-config file is named `builder.toml`, not `config.toml`

**Decided:** 2026-07-26

Brian, starting a real client install and writing it up in `CONFIGURATION.md`, noticed that
`~/.config/cairn/config.toml` and the manifest `cairn.toml` are one word apart — a reader can't
glean which is which from the name alone, only from which directory it sits in.

**Decision:** rename the file to `~/.config/cairn/builder.toml`. The manifest keeps its name
(idiomatic — a project manifest named after its tool, as with `Cargo.toml`) and already has a
recognizable sibling, `cairn.local.toml`; the machine file was the odd one out. `builder.toml`
instead names the **role** it serves: it's what a machine acting as **Builder** reads, mirroring
the Builder/Target split the README already teaches. `doctor` also reads it (it reports on
either role), but no `Target`-side code (`reconcile`, `adopt`, `systemd-units`) ever does — this
was true before the rename and constrains what the name is allowed to imply.

Considered and rejected: renaming the manifest instead (`cairn.toml` → `manifest.toml`) — higher
blast radius for the file every user interacts with most, and it forfeits the `Cargo.toml`-style
branding for no gain, since the manifest was never the ambiguous half. Also considered: doing
nothing, since the two files' directories (project root vs. `~/.config/cairn/`) already
disambiguate them in code — rejected because the ambiguity was never about the code path, only
about a reader's or writer's first encounter with the two names in prose or in a terminal
history, which the directory doesn't help with.

**No behavior changed** — same keys (`BR-CFG-008`'s `BUILD_CONFIG_KEYS`), same precedence
(`BR-CFG-012`), same access boundary (builder-side commands + `doctor`, never target-side). Filename
only, so pre-release timing made this cheap: nothing in production yet depends on the old path
existing.

**Confirmed, while renaming: no other override path exists for this file.** It cannot be
shadowed by a same-named file in the working directory (that slot is `cairn.local.toml`, a
different name, beside the manifest specifically — not a bare cwd lookup of `builder.toml`
itself), by an environment variable (none is read for any of its keys), or by a CLI flag (no
command exposes `--engine`/`--registry`/`--namespace`/`--image-base`; the one adjacent flag,
`--transcript <path>` on `cairn build`, replaces the transcript *destination* outright rather than
overriding the `transcript_dir` *setting*, and is scoped to that one invocation). Adding a cwd-shadow
lookup was considered and set aside: it would create a second "am I overridden right now" question
alongside `cairn.local.toml`'s existing one, for a file that's supposed to be genuinely
machine-wide rather than per-directory.

**Superseded the same day (`ADR-042`):** the directory moved again, from `~/.config/cairn/` to
`/etc/cairn/`, and `cairn.local.toml` was removed rather than kept as the override slot described
above — a home directory turned out to be the wrong model for a multi-operator VPS, which
`ADR-042` covers in full. The filename `builder.toml` and the reasoning for it are unaffected;
only the directory and the override mechanism changed again.
*(BR-CFG-008, BR-CFG-012, BR-CLI-014, BR-CLI-016, ADR-029, ADR-042)*
