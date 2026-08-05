---
status: authoritative
owner: technical
purpose: ADR-059 — cairn owns its Docker build recipe; frappe_docker vendoring is retired
---

# ADR-059 — cairn owns its Docker build recipe; frappe_docker vendoring is retired

**Decided:** 2026-08-05
**Supersedes:** `ADR-001` (wrap `frappe_docker`, never modify it), `ADR-007` (vendoring via
`ventwig`, committed + drift-checked). **Resolves:** `ADR-020` (strengthen upstream-pin
immutability — moot, there is no more pin), `ADR-021` (deliberate fork of `frappe_docker` as
the sanctioned escape hatch — superseded; ownership already grants everything a fork would,
without forking anything). **Relates to:** `ADR-004`, `ADR-008`, `BR-VEND-*` (redefined by this
decision, see `docs/requirements/01-vendoring.md`).

## Raised

Working through `ADR-021`'s deferred "fork `frappe_docker`" question (Brian, prompted by a live
adoption incident on a client VPS — see `ADR-021`'s fork-pressure register item 4, a target
whose compose file didn't parameterize the image). The conversation moved through several
positions before landing here:

- **Forking the vendored tree** — considered, then rejected: a fork changes cairn's own vendored
  *copy*, but `cairn-adopt reconcile` never composes against that copy at deploy time — it reads
  a directory and filename off the *target's* descriptor (`descriptor.py`'s `Compose.directory`/
  `Compose.file`, "a hand-built stack may use anything... read from the actual project"). The
  file that actually caused the incident was already deployed on the client's host, put there
  before cairn ever ran. Forking the vendored tree would not have touched it.
- **Munging the target's on-disk compose file during `cairn-adopt`** — a real, additive
  capability worth having regardless (target-side normalization, same category as the `.env`/
  descriptor writes cairn already does), but it doesn't answer the underlying question: cairn
  will *always* face a pre-existing compose file, because `BR-DEPLOY-007` already scopes cairn to
  existing environments only — `bench new-site` and initial provisioning are the operator's
  responsibility, never cairn's. Given that, the vendored `compose.yaml` inside cairn's own repo
  is causally disconnected from every real `reconcile` invocation that will ever run. It serves
  no purpose there.
- **Replacing `frappe_docker` outright** — the position that held. If cairn deploys against a
  pre-existing compose file on every real target regardless, and if cairn's own recipe is small
  enough to own outright, there is no reason to keep the formal vendor-pin-drift machinery at
  all.

## Decision

**Cairn owns its Docker build recipe (`Containerfile`) and compose YAML permanently, as
ordinary source it may edit directly.** The tree that was vendored read-only at
`src/cairn/vendored/frappe_docker/` moves to `src/cairn/recipe/frappe_docker/`, bootstrapped as
a byte-for-byte copy of the tree as of this decision — zero rewrite risk on day one. `ventwig`,
`.ventwig.lock`, `frappe_docker.pin.toml`, the tree-hash drift check, and the "never modify"
restriction are all retired. There is no pin, no sync obligation, and no cadence commitment.
Cairn's posture toward upstream `frappe_docker` becomes informal: read it whenever convenient,
borrow whatever's useful, on no schedule.

**Grounds, checked against the actual code and recipe rather than assumed:**

- **`reconcile` never used the vendored copy at deploy time.** `Compose.directory`/`Compose.file`
  are read off the target's own descriptor, never assumed to be the vendored default
  (`descriptor.py:60-73`). Ownership costs nothing at deploy time that wasn't already true.
- **The recipe itself is small and legible.** `images/custom/Containerfile` is ~130 lines: one
  Debian base (`bookworm`), six version `ARG`s (`PYTHON_VERSION`, `DEBIAN_BASE`,
  `WKHTMLTOPDF_VERSION`, `WKHTMLTOPDF_DISTRO`, `NODE_VERSION`, `FRAPPE_BRANCH`), a bounded
  `apt-get install` list, and two lines of `uname -m` arch detection for the `wkhtmltopdf`
  download — not the sprawling, high-churn surface an early pass through this decision assumed.
  Read in full this session, not taken on faith.
- **Propagation to a real target was never automatic under vendoring either.**
  `BR-VEND-009` already forbade automatic re-sync — upgrades were always a deliberate act (bump
  `ref` → `ventwig sync` → review → commit → rebuild → reconcile). Ownership doesn't make
  delivery to a client VPS any slower than it already was; it only changes who authors the diff
  before it ships — cairn itself, instead of waiting on and then re-vendoring frappe_docker's own
  fix.
- **The bus-factor/support risk this decision might seem to add already exists.** Cairn's build/
  registry/reconcile logic is already 100% bespoke, un-warrantied, single-maintainer code. Owning
  the recipe doesn't introduce a new category of risk to a tool that already carries it in full.
- **Three of `ADR-021`'s four fork-pressure register items dissolve at once, without a fork:**
  no per-app cache seam (item 1) becomes fixable directly, in cairn's own layering; no
  commit-level pinning (item 2) becomes moot — an owned file can pin anything, including a raw
  commit; the two incompatible compose shapes (item 4) stop being upstream's problem to solve,
  since cairn's owned compose is the only shape cairn ever ships. (Item 3, "upstream changes the
  recipe in a way that breaks us and won't take a patch," was never encountered and is retired
  with the rest of the register — there is no longer an upstream relationship for it to describe.)

**Cost accepted, named plainly.** Cairn now authors 100% of its own future recipe changes —
version bumps, CVE-driven base-image patches, toolchain fixes — rather than inheriting them from
frappe_docker's maintainers on sync. This is a real, permanent transfer of authorship, not a
one-time migration cost. It is accepted deliberately, on the evidence above that the recipe is
small enough for one person to own end-to-end, and consistent with this project's existing
posture toward its own bespoke code: free and open source, offered without warranty of continued
maintenance.

**Naming and scope, confirmed the same session:**

- New location: `src/cairn/recipe/frappe_docker/` (renamed from `src/cairn/vendored/`).
- CLI: `cairn-build vendor status|sync` is retired outright. No replacement "diff against
  upstream" command ships — checking `frappe_docker` for ideas is a manual `git clone`/diff Brian
  does by hand, at will, exactly as informal as the sync posture above.
- The `VEND` requirement area (`AGENTS.md`'s BR-area glossary) is kept, redefined from
  "vendoring" to "the owned Docker build recipe cairn authors and maintains directly." No BR-ID
  renumbering.

## Consequences

- `docs/requirements/01-vendoring.md`'s ten `BR-VEND-001..010` (ventwig mechanism, tag pin, lock
  anchor, read-only, drift hard-stop, build-input completeness, no upstream `.git`, no package
  markers, deliberate-upgrades-only, git working tree) are replaced by a smaller ownership-era
  set — direct-edit is now permitted; there is no pin, lock, or drift concept left to require.
  Build-input completeness (`images/custom/Containerfile` + the `resources/` it references exist)
  survives as an ordinary sanity check, no longer framed as a vendoring precondition.
- `BR-BUILD-011`'s provenance labels currently stamp `cairn.frappe-docker.ref`/`.commit` from
  `frappe_docker.pin.toml`. There is no longer a separate upstream pin to read. Provenance under
  ownership should instead reflect cairn's own recipe history (its own git commit/version) —
  tracked as a design point in `docs/requirements/02-build.md`, not silently dropped.
- `src/cairn/vendor.py`'s ventwig-wrapping functions (`status`, `sync`, `_refresh_pin_file`,
  `read_pin`, the drift check inside `assert_clean`, `_tree_hash`), `src/cairn/project.py`
  entirely, the `vendor` Typer sub-app in `src/cairn/cli_build.py`, and `pyproject.toml`'s
  `[tool.ventwig]` section and `ventwig` dev dependency are all dead code once the migration
  lands. **Not touched by this decision** — queued as separate, later `open/OPEN_WORK.md` items,
  reviewed on their own once the documentation cascade this ADR triggers has settled, per this
  project's own "documentation precedes code" discipline.
- `userdocs/builder/index.md` cites `(ADR-001)` directly in user-facing text — already a standing
  violation of "IDs never reach a user" independent of this decision, and one that must not
  survive `ADR-001` moving to `docs/archive/`. Fixed as part of the same deferred code-migration
  pass, since the user-facing description depends on the CLI surface actually changing first.
*(BR-VEND-001 … BR-VEND-010 — redefined, see `docs/requirements/01-vendoring.md`; BR-BUILD-009,
BR-BUILD-011, BR-BUILD-013, BR-CLI-006, BR-CLI-013, BR-DEPLOY-007, ADR-001, ADR-004, ADR-007,
ADR-008, ADR-020, ADR-021)*
