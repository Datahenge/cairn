---
status: authoritative
owner: technical
purpose: ADR-018 — One package `datahenge-cairn`; command `cairn`; split deferred
---

# ADR-018 — One package `datahenge-cairn`; command `cairn`; split deferred

**Decided:** 2026-07-24
**Single package, one repo.** cairn's two roles (build/control on the laptop; reconcile on
targets) are modes of one cohesive tool that shares config models, registry logic, and
compose rendering — not two programs. The role separation is enforced by **credentials** (a
target holds only a read-only pull token, so even the full CLI there cannot build/push/
retag), not by splitting code or dependencies (the Python footprint is tiny and identical;
build heaviness lives in external `docker`/`buildx` binaries).

**Names:**
- **PyPI distribution:** `datahenge-cairn`. `cairn` is taken; `docker-cairn` /
  `frappe-cairn` would falsely imply Docker/Frappe ownership. `datahenge-cairn` truthfully
  signals Datahenge and doubles the stone motif (Datahenge = stone circle, cairn = stacked
  stones).
- **Import package:** `cairn`. **Console command:** `cairn` (primary) + a `datahenge-cairn`
  alias as a collision fallback.

**Verified 2026-07-25**, since both halves rested on an unchecked assumption: `cairn` on PyPI
**is** taken — `cairn` 0.2.3, an unrelated project-versioning tool — and `datahenge-cairn` **is**
available. The premise holds.

**Amended 2026-07-25 — the repository is `Datahenge/cairn`, not `datahenge-cairn`.** The prefix
was adopted for one reason: PyPI is a flat global namespace and the good name was gone. GitHub
namespaces by owner, so that reason does not transfer — and `Datahenge/datahenge-cairn` stutters.
`Datahenge/cofferdam` and `Datahenge/btu` already establish the plain-name convention for this
org (`brian-pond/ventwig` does the same on the personal account). The distribution name and the
repository name are allowed to differ; they answer to different namespaces. Owner is `Datahenge`
rather than the personal account because cairn is ERPNext-domain tooling, like cofferdam and btu,
where ventwig is a general-purpose utility.

**Distribution:** a pip-installable wheel; on a target, `cairn reconcile` runs under a
systemd service + timer (`BR-DEPLOY-001`).

**Split deferred (trigger recorded):** revisit a separate minimal agent only if a genuinely
heavy *build-only* dependency appears, or a hard requirement emerges that target code be
*physically incapable* of build/push logic (beyond credential-gating). Neither holds today.
*(BR-DEPLOY-001)*

**Superseded 2026-08-03 (`ADR-046`):** the single unified `cairn` command is retired in favor
of two console-script entry points, `cairn-build` and `cairn-adopt`, into the same one
package. The package/dependency question this ADR answered is unchanged — still one
distribution, no split — but its command-surface answer ("invoked as `cairn`... with
subcommands") no longer holds. See `ADR-046` for the full record.

---

**Re-examined 2026-07-25, at Brian's request, with the deploy path now written.** He observed that
cairn increasingly reads as a *toolkit of two tools* — a **builder** that waits for triggers, builds,
stores and serves images, and a **consumer** that polls for images and relaunches its stack — and
asked whether one repo and one PyPI distribution still serves both, or whether it wants
`[build]`/`[consume]` extras, or two applications.

**Measured before answering.** The consumer's dependency graph is a **closed island of five
modules** — `errors`, `registry`, `descriptor`, `reconcile`, `systemd` — with **zero** imports from
`config`, `build`, `vendor`, `project`, or `images`. The builder half is the opposite: `build`
reaches into seven modules, `images` borrows `LABEL_NAMESPACE` from `build`, and `environments`
pulls `config` + `images` + `registry`.

**Decision: the split stays deferred, and the cleanliness is the reason.** A seam this sharp remains
cheap to cut whenever a concrete need appears. Nothing is eroding it — `reconcile` was deliberately
built to require no manifest and no project root, and the descriptor's presence is the role signal
(`ADR-028`, `ADR-034`). Splitting pre-emptively buys a version-compatibility matrix between builder
and agent and nothing else. Had the halves been entangled, the answer would be the reverse: separate
now, before it worsens.

**`[build]` / `[consume]` extras are rejected on mechanism, not on taste.** Extras gate
**dependencies**. Both roles need exactly one — `typer`. An empty extra advertises a separation the
wheel does not contain, which is worse than having none. The differences that *are* real — a
container engine with buildx, `git`, ~30 GB of disk, the vendored tree — cannot be expressed as pip
extras. They belong in `doctor`'s role detection and the installer's `--role`.

**How "one package" actually works in the field**, since that was the substance of the question:
installation is *identical* on both machines, and the role is decided by which configuration exists
and which timer is enabled — not by what was installed.

| | Builder | Target |
| --- | --- | --- |
| Install | one distribution | the same distribution |
| Config present | `cairn.toml` + vendored tree | `/etc/cairn/environment.toml` |
| Timer enabled | build | reconcile |
| Registry credential | push | **pull-only** |

A target therefore carries build code it never invokes, and its pull-only credential means it could
not push or retag if asked — which is `ADR-018`'s original argument, still holding.

**Sharper split trigger, replacing the vaguer one above:** split when a target must run somewhere the
builder's code *cannot* (a minimal or immutable OS), or when a security requirement demands the
target be physically incapable of push/retag rather than merely uncredentialed. Conceptual tidiness
is explicitly **not** a trigger.

**Resolved 2026-07-25 — all three reasons closed by moving the vendored tree inside the
package.** This section originally recorded three independent reasons `pip install
datahenge-cairn && cairn build` could not work: the wheel excluded the vendored tree
(`packages = ["src/cairn"]`, `frappe_docker/` at the repo root); `project.find_project_root()`
locates a project by searching upward for a `pyproject.toml`, which does not exist in
`site-packages`; and `vendor.assert_clean()` ran on every build and required the `ventwig`
CLI, a dev-only dependency.

Brian's framing, revisited while resolving this for a PyPI publish: vendoring is a fetch
mechanism, not an ongoing relationship. Once `frappe_docker` is fetched it is part of cairn
the same way any other committed source file is — it belongs in cairn's own git history and
in anything cairn ships, PyPI included. `ventwig` should never be thought about again after
the fetch.

That reframing dissolves all three reasons at once, rather than requiring three separate
fixes: the vendored tree moved to `src/cairn/vendored/frappe_docker` — *inside* the `cairn`
package — so `packages = ["src/cairn"]` ships it in the wheel automatically (closes 1).
Every vendor-tree lookup (`vendor.build_context`, `vendor.containerfile_path`, the `assert_*`
preconditions) resolves package-relatively from cairn's own `__file__`, never by searching
the filesystem for a project root — so it works identically in a checkout and an installed
wheel, and `find_project_root()` is needed only by `cairn vendor status`/`sync` themselves,
the two commands that actually shell out to `ventwig` (closes 2). `cairn vendor sync` now
also writes a companion `src/cairn/vendored/frappe_docker.pin.toml` (ref, commit, tree hash)
from ventwig's own `.ventwig.lock`, and `assert_clean()` verifies against *that* — recomputing
the same git tree-hash ventwig computes, using only the `git` binary cairn already requires,
never `ventwig` itself (closes 3). Verified 2026-07-25: a wheel built from the new layout,
installed into a clean venv with no checkout and no `[dev]` extra, ran `cairn doctor` and
`cairn build --dry-run` through to build-engine invocation with no project-root or vendoring
error of any kind.

One consequence worth naming: the builder role no longer *requires* a checkout — a bare
`pip install datahenge-cairn` now carries everything `cairn build` needs. The installer
(`ADR-040`) still provisions a builder from a checkout by default, since that is also how an
operator gets `ventwig`/`ruff`/`pytest` for local development — but that is now a choice, not
a hard requirement imposed by packaging.
*(BR-VEND-002/003/005, ADR-007, ADR-028, ADR-029, ADR-034, ADR-040)*
