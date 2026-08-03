---
status: authoritative
owner: technical
purpose: ADR-040 — Provisioning is an installer beside the CLI, never a verb inside it
---

# ADR-040 — Provisioning is an installer beside the CLI, never a verb inside it

**Decided:** 2026-07-25
Standing up a builder VPS is a dozen steps: gate the host, capture what is already running, back up
the site, install cairn, generate a TLS certificate, run a registry, write a descriptor, install
timers. Brian rejected documenting that as a runbook — a procedure he pastes command-by-command is
not idempotent, not testable, and does not get cheaper for builder VPS #2 and #3, which for a
multi-client practice is the case that matters. His framing: "If it's worth doing for safety/checks,
it's worth building it as a reusable installer."

The obvious home was a `cairn bootstrap` subcommand. **That would breach two decisions made
deliberately days earlier:**

- `ADR-035` — cairn **emits** systemd units and never installs them, because writing to
  `/etc/systemd/system` needs root and changes the host outside cairn's stated boundary.
- `ADR-022` / `BR-DATA-006` — cairn performs **no writes to data-plane volumes**. A pre-install
  `bench backup` writes a dump into the sites volume. Useful, and not cairn's to do.

**Decision:** the installer is a **separate program**, run with `sudo` by the operator. It *calls*
cairn for the read-only and print-only work (`doctor`, `adopt`, `systemd-units`) and performs the
privileged writes itself. cairn's boundary is untouched: the CLI still writes nothing to `/etc`,
nothing to systemd, and nothing to a volume.

This is not a loophole. The operator invoking an installer *is* the operator doing it; `ADR-035`'s
objection was to cairn taking that act on itself, silently, as a side effect of some other command.
A separate program, named as an installer, run with explicit privilege, is the honest expression of
the same boundary.

**The invariant this establishes, now true across the whole CLI:**

> **cairn prints host configuration. The operator installs it.**

`systemd-units` prints units. `adopt` (`BR-CLI-020`) prints a descriptor. Neither writes. The
installer is what turns printed configuration into installed configuration, and it can be replaced by
hand at any point — which `BR-DEPLOY-021` requires.

**Amended 2026-07-25 — the installer moved inside the package (`src/cairn/provision.py`), with its
own entry point, `cairn-provision`.** The original reason for a stdlib-only *separate program* was
that it ran before cairn's virtualenv existed and could not import cairn — forced, not chosen. That
premise is gone: once the PyPI-install blockers closed (see the `ADR-018` resolution above), the
same `pip install datahenge-cairn` that gives you `cairn` also gives you `cairn-provision` — they are
never installed apart. What does **not** change: `cairn-provision` still stays out of the `cairn`
command tree, for the same two reasons as before (`ADR-035`, `ADR-022`) — those are about what
`cairn` itself is allowed to do, not about how the installer is distributed. It still writes
systemd units, TLS material, and runs `bench backup` directly, guarded by the same seven-point
contract (`BR-DEPLOY-021`) — `--dry-run`, idempotent, never-silently-overwrite — rather than
printing instructions for the operator to type by hand; comparable tools (`certbot`, `mkcert`,
`k3s`'s installer) lean on the same dry-run-plus-idempotency safety net rather than requiring manual
transcription, and requiring it here would have added a transcription-error opportunity without a
matching safety gain, given the operator already granted root to run it.

**Consequence for how it locates `cairn`.** With no checkout to anchor to, `cairn-provision`
resolves `cairn` as its own sibling in the same install (`Path(sys.argv[0]).parent / "cairn"`),
falling back to a `PATH` lookup — never a `--source` checkout directory, which no longer exists as a
concept for provisioning. The stage that used to create a fresh virtualenv and `pip install` cairn
into it (`stage_cairn`) is gone entirely: there is nothing left to install by the time
`cairn-provision` runs, since it's already part of the same distribution.

**Recommended install for anything a client depends on**: `sudo pipx install --global
datahenge-cairn`, not a personal `pip install`/`pipx install`. `pipx --global` installs to a shared
system location (`/opt/pipx` by default) rather than under an individual operator's home directory —
which matters specifically because the people running this tool are frequently consultants, and a
consultant's own account is not something a client's production systemd timers should depend on
being able to execute. A personal install still works and is fine for a builder one operator solely
uses; it stops being fine the moment someone else's infrastructure depends on it outliving that
operator's account.

**Why Python rather than bash.** This code runs as root on client infrastructure and therefore has
to be **testable**, which is the same argument that produced this project's suite everywhere else.
Bash would have been marginally easier to audit line-by-line and impossible to test.

**Consequence for `BR-DEPLOY-007`.** That requirement makes initial site/volume/database creation the
operator's responsibility. The installer does not change it — it provisions the *build and deploy
plumbing*, never a site. `bench new-site` remains outside every tool cairn ships.
*(BR-DEPLOY-021, BR-CLI-020, BR-DEPLOY-007, ADR-022, ADR-035, ADR-018)*

**Superseded 2026-08-03 (`ADR-046`):** `cairn-provision` as a **separate program** is retired.
Its work — the same seven-point contract, the same privileged writes — becomes `setup`, a
subcommand nested inside each of the two role-specific CLIs (`cairn-build setup`,
`cairn-adopt setup`), which also retires the `--role` flag: each CLI's `setup` only ever
provisions what that CLI's own role needs. The reasons this ADR gave for keeping installation
*out of the ordinary command* still hold — `setup` still checks its own privilege and exits if
unprivileged, and no other subcommand performs a privileged write — the reversal is only that
the installer is no longer a *structurally separate binary*. See `ADR-046`.
