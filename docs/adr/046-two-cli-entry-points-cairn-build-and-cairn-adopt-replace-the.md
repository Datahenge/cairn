---
status: authoritative
owner: technical
purpose: ADR-046 — Two CLI entry points, `cairn-build` and `cairn-adopt`, replace the unified `cairn` binary and `cairn-provision`
---

# ADR-046 — Two CLI entry points, `cairn-build` and `cairn-adopt`, replace the unified `cairn` binary and `cairn-provision`

**Decided:** 2026-08-03
**Supersedes:** `ADR-018`. **Amends:** `ADR-028`, `ADR-035`, `ADR-040`, `ADR-043`.

Raised while writing the published Get Started guide (`BR-DOCS`): a single onboarding
narrative for a tool with two roles kept forcing an assumption about which reader was
reading — "install, then adopt" versus "install, then build" are genuinely different
stories, and one linear page couldn't tell both without picking one. Separately, a real
naming collision surfaced: "reconciler" as a role-noun reads, to anyone who knows the
ERPNext domain, like the name of an *accounting* feature (Bank Reconciliation Tool,
Payment Reconciliation) — not a deploy agent. Both problems trace back to the same root:
one binary trying to be two things.

**Decision.** Still **one package**, `datahenge-cairn` — no dependency split, no
multi-distribution workspace, nothing changes about `pip install`. What changes is the
**console-script surface**: two entry points, each its own Typer app, in place of the
single `cairn` command:

- **`cairn-build`** — the build/control role.
- **`cairn-adopt`** — the target role.

There is no unified `cairn` command and no `datahenge-cairn` alias. The alias's only
reason to exist (`ADR-018`) was a PyPI-namespace collision fallback for the plain name
`cairn`; neither new entry point is named `cairn`, so the collision it guarded against no
longer applies.

**Command allocation:**

| `cairn-build` | `cairn-adopt` |
| --- | --- |
| `build`, `push` | `examine` |
| `new-tag`, `retag`, `retire` | `reconcile` |
| `images` | `systemd-units` |
| `vendor status` / `sync` | |
| `prune` | |
| `doctor` (build/control checks only) | `doctor` (target checks only) |
| `setup` (privileged) | `setup` (privileged) |

**`adopt` the verb is renamed `examine`.** `cairn-adopt adopt` read as a stutter, and
worse, invited the wrong inference — "adopt" implies a change is being made, where the
command is a strict read-and-print survey (`BR-CLI-020`, unchanged in substance). "examine"
is unambiguously read-only and pairs with the diagnostic register `doctor` already
established (a doctor examines a patient). The CLI's own name keeps "adopt" — it still
correctly frames the tool's purpose, bringing an existing hand-built deployment under
cairn's care — the collision was only ever between the program name and one of its own
subcommands, not with the word itself.

**Role detection is retired.** `ADR-028` taught `cairn doctor` to sniff its context and
pick a check set; that mechanism is no longer needed; each binary now runs exactly one
role's checks, unconditionally, because the binary invoked already answers the question.

**`cairn-provision` is retired as a separate program.** Its work becomes `setup`, a
subcommand nested in each of the two CLIs (`cairn-build setup`, `cairn-adopt setup`),
eliminating the `--role` flag entirely — each CLI's `setup` only ever provisions what
that role needs, because there is no third, generic installer trying to serve both.
`setup` performs its own privilege check and exits if unprivileged, exactly as
`cairn-provision` did. This is a conscious partial reversal of `ADR-035` ("cairn emits
systemd units; it never installs them") and `ADR-040` ("provisioning is an installer
beside the CLI, never a verb inside it") — but the property those decisions actually
protected survives intact: privileged host mutation is still never a **silent** side
effect of an ordinary command. `build`, `push`, `reconcile`, `examine`, and every other
plain subcommand still touch nothing privileged; only the explicitly-named,
explicitly-invoked, privilege-gated `setup` does. The seven-point installer contract
(`BR-DEPLOY-021`) and `ADR-043`'s `/etc/cairn` group-sharing stage carry over onto `setup`
unchanged — only their home moved. One implementation simplification falls out for free:
`cairn-provision`'s prior need to locate and shell out to a sibling `cairn` binary (`ADR-040`'s
amendment) disappears, since `setup` now runs in-process within whichever CLI hosts it.

**`install` was considered and rejected** as the subcommand name. Cairn already draws a
hard, repeated line — "cairn never installs a Frappe App" (`BR-DEPLOY-003a`) — and reusing
"install" for cairn's own host bootstrapping would echo a term cairn has deliberately
spent effort disclaiming. `setup` says the same thing without the echo.

**No workspace tooling needed.** Because both entry points remain modules inside the one
existing `cairn` package — sharing its config, registry, descriptor, and compose-rendering
code internally, exactly as `ADR-018`'s "closed island of five modules" measurement
already showed was cheap — there is no multi-package workspace to manage (`uv` workspace
or otherwise). That question, raised earlier in this same discussion, is moot: `cairn-core`
was never going to be a separately-installed distribution.

**The split-trigger `ADR-018` recorded stays the real bar for going further** — extracting
the shared code into a genuinely separate installable library remains warranted only if a
heavy build-only dependency appears, or a hard requirement emerges that target code be
physically incapable of build/push logic. Nothing here forces that; today's change is
entirely at the entry-point/command-surface layer.
*(BR-CLI-001, BR-CLI-007, BR-CLI-008, BR-CLI-019, BR-CLI-020, BR-CLI-021, BR-DEPLOY-021,
BR-DEPLOY-022, ADR-018, ADR-028, ADR-035, ADR-040, ADR-043)*
