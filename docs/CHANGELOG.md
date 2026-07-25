# Documentation Changelog

Per the Scribe Coding working agreement (`/CLAUDE.md`), this file records revisions to
the project's **living documentation** — requirements, decisions, and design records —
so conflicts can be reconciled against the docs rather than by interrupting the user.

Newest entries first. Dates are absolute. This tracks *documentation* changes; source
code changes live in git history.

---

## 2026-07-25 (night, deploy path)

Three gaps blocked the deploy verbs: `BR-DEPLOY-009` and `BR-DEPLOY-010` each settled what a
thing *is* without saying where it lives, and `BR-DEPLOY-001` required a systemd timer without
saying who writes it. All three are now decided, and Brian chose each.

- **`ADR-033` — the declared environment list is `[cairn.environments]` in `cairn.toml`**
  (environment name → registry tag). Chosen over a second file because the list is portable,
  shared, and belongs under review beside what it points at — and the manifest is already
  discovered with no flags (`BR-CFG-012`). It does **not** contradict `BR-BUILD-001`: that
  calls the *image* environment-agnostic, not the file, and no environment name reaches a
  build. Build config was rejected outright — a source of truth gating a production retag
  cannot live somewhere machine-local and uncommitted (`BR-CFG-008`). Recorded as
  `BR-DEPLOY-009a`; `BR-BUILD-002` now admits the optional fifth key.
- **`ADR-034` — the target descriptor is TOML at `/etc/cairn/environment.toml`, one
  environment per host.** Fixed path, because `reconcile` runs unattended: a flag is
  something nobody is present to pass, and a search path can silently find the wrong file.
  The file's presence doubles as the role signal `ADR-028` detects a target from. One
  environment per host follows `BR-DEPLOY-014` (one site per environment) and `ADR-002`
  (single-host VPS), and keeps `reconcile` argument-free with a single global lock; if
  multiple environments per host are ever needed, `/etc/cairn/<env>.toml` extends it and
  `reconcile` gains an argument. It is **host state, not deployment state** — never committed.
  Recorded as `BR-DEPLOY-010a`.
- **`ADR-035` — cairn emits systemd units and never installs them.** Writing to
  `/etc/systemd/system` and reloading the daemon needs root and changes the host outside
  cairn's stated boundary; `BR-DEPLOY-008` makes cairn a thin orchestrator *over* systemd, not
  an adopter of the host's init configuration. Ignoring the units was also rejected: the
  cadence, the single-flight expectation, and journald owning the log are cairn's knowledge,
  and a printed unit is documentation that cannot drift from the code. Recorded as
  `BR-CLI-019`.

**Field context that shaped the sequencing:** the VPS already runs a live site, so `cairn`
takes over the image pointer only — `BR-DEPLOY-007` keeps `bench new-site` the operator's job,
and none of this work creates sites, volumes, or databases.

Two further decisions the implementation forced:

- **`ADR-036` — cairn speaks the registry API directly** rather than shelling out, and this was
  decided by evidence rather than preference. `BR-DEPLOY-005` requires reading an image's
  provenance labels *remotely, without pulling*; the control machine has `podman` 5.4.2 and
  `buildah` 1.39.3 and **no podman or buildah subcommand can do that**. `docker buildx
  imagetools` and `skopeo` can, and neither is installed — so delegating would mean a new hard
  binary dependency to perform one manifest fetch. cairn now owns a small stdlib client: three
  GETs and a PUT, no third-party HTTP library. Credentials stay the engine's (`BR-CFG-010`):
  cairn reads the file `podman login` wrote, uses it for one command, and persists nothing;
  anonymous is tried first, so a public repository never opens it. **Flagged for Brian's
  review** — he chose the other three decisions, not this one.
- **`ADR-037` (open) — how an `install-app` opt-in reaches a target.** `BR-DEPLOY-003` permits
  it behind an opt-in directive and `BR-CLI-004` expresses that opt-in control-side, but the two
  halves of an environment are joined *only by the tag name*, which has no room for a payload.
  So `cairn reconcile` does not run `install-app` at all, which is the correct reading of
  `ADR-023`: absent a decided transport, installing would be the auto-install that decision
  forbids. Four options are recorded, including striking the clause — a genuine possibility,
  since adding an app to a live site is a rare and deliberate act. Trigger: the first time it is
  actually needed, note what was needed, then decide.

**On testing this before it touches production.** The deploy path is covered by 162 new tests,
and — as with the CLI work — the tests were checked for the failure they claim to detect. 22
mutations were applied to `registry.py`, `environments.py`, `reconcile.py`, `descriptor.py`, and
`cli.py` one at a time: a retag that re-serializes the manifest (which would change its digest),
a retag writing to the source tag, a pull-only token, credentials read before trying anonymous,
`new-tag` accepting a live pointer, production's confirmation skipped, a stopped stack counted as
converged, `migrate` skipped, compose overrides layered in reverse, a shared rather than
exclusive lock. **Every one was caught by a named test.** One real defect was found this way and
not in production: a root-owned `~/.docker/config.json` made `Path.is_file()` raise
`PermissionError`, which would have turned every registry command into a traceback where
anonymous access would have worked.

## 2026-07-25 (night)

- **`cairn prune` verified on the real machine.** Brian confirmed it worked as intended,
  closing the one item in `docs/plans/next-steps.md` §1 that no test could settle — the only
  new code that had never been executed against real images, and cairn's only destructive
  verb. `BR-CLI-018` is now implemented *and* exercised in the field.
- **The CLI layer is now tested.** `tests/test_cli.py` added (45 tests, Typer `CliRunner`),
  closing the one material coverage hole a suite review found the same day: `cli.py` was
  simultaneously the largest module and the only surface a user touches, and it had never
  been executed under test. `_run_in_project` — which *is* `BR-CLI-012`'s exit-code contract
  (0 success, 2 for an expected failure, 130 for interrupt, the action's own code otherwise)
  — was previously verified only by hand. `cli.py` and `__main__.py` go 0% → 100%; the
  package total is 94%.
- **The tests were checked for the failure they claim to detect.** 14 mutations were applied
  to `cli.py` one at a time — wrong exit codes, ignored flags, a silenced warning, a skipped
  confirmation, the registry check moved after the build — and every one was caught by a
  named test. This is the same discipline as
  `test_the_guard_actually_detects_a_violation` in `test_conventions.py`: a test that cannot
  fail is not protection. Notably, `transcript.wanted` and `prune.select` were already
  thoroughly tested at the module level while nothing verified the CLI passed them the right
  arguments — tested logic behind untested wiring.
- **Two tests repaired, not removed.** `test_build_args_do_not_affect_the_cache_bust` named a
  guarantee its body never exercised (`cache_bust` accepts only a resolution, so build args
  *cannot* be passed to it); it now pins the property actually worth holding — build args
  change the input hash but must not change the cache bust. `test_sizes_are_not_binary_units`
  was subsumed by the assertion above it and is folded into it, keeping the original bug in
  the docstring.
- **`pytest-cov` added to the `dev` extra**, and `.coverage` gitignored. No
  `--cov-fail-under` floor is set yet — that is a separate decision, since putting `--cov` in
  `addopts` makes every test run depend on the plugin being installed.

## 2026-07-25 (evening, later)

- **`ADR-021` gains a fork-pressure register.** Brian observed that each pitfall makes an
  eventual fork of `frappe_docker` feel nearer. The register exists so that judgement rests
  on evidence rather than accumulated feeling: it admits **only** constraints that are
  genuinely upstream's, and explicitly excludes cairn's own work (transcripts, timing,
  tagging, pruning, the short-circuit), none of which a fork would change.
- **Two entries recorded, both Brian's.** (1) *The atomic `bench init` layer* — sharpened
  considerably by his actual workflow: a client engagement pins one Frappe/ERPNext version
  and then iterates on custom apps for weeks, so the unchanged 95% is re-cloned and rebuilt
  on every custom-app commit. That makes the worst-handled case the **dominant** one, not an
  edge. Now the strongest argument on the list. (2) *Commit-level pinning is impossible
  through bench*, which matters more in this ecosystem than most because `version-15` /
  `version-16` move continuously under backporting. Consequence: an image cannot be rebuilt
  from its manifest once the branch has moved, so the stored image is the only durable copy.
- **Countervailing evidence recorded too**, to keep the register honest: the vendored recipe
  was measured working as designed on the same day.
- **Trigger set:** revisit when entry 1 is measured — time a rebuild after a single
  custom-app commit against a first build.
- **`docs/plans/next-steps.md` added** as a session-resumption point.

## 2026-07-25 (evening)

- **`BR-BUILD-015` added — name the build-cache stage.** Brian asked whether cairn should
  label the build cache so an admin running `podman image list` doesn't delete it. The
  mechanism had to change: `podman image list` prints repository, tag, id, age and size —
  **labels are never displayed**, only filterable, so a label helps nobody scanning a
  listing. A **tag** is what shows, and a tag is a pointer: free.
- **Measured before committing** (lessons §12): a `--target builder` pass against a warm
  cache took **0.762s**, every step a cache hit, `COMMIT` landing on the *existing* image
  id with `CREATED` unchanged. No new image, no new disk. It also proved from the engine's
  own cache resolution that the 4.63 GB untagged image **is** the `builder` stage.
- **Two constraints the measurement produced.** The pass is only cheap against a warm
  cache, so it runs solely after a build that *actually ran* — never after a
  `BR-BUILD-014` short-circuit, where the stage may have been pruned since and the same
  command would be a full `bench init`. And podman prefixes unqualified names with
  `localhost/`.
- **`ADR-027` amended — the engines are equivalent in *output*, not in *residue*.** Docker
  keeps build cache in a separate store rather than as images, so `--target` there would
  **materialize** several GB that otherwise never exist. `BR-BUILD-015` is podman-only as a
  correctness constraint, not a preference. General rule recorded: behaviour touching an
  engine's local storage is decided per engine; behaviour touching the image is not.
- **A claim of mine withdrawn before it reached code.** I had argued tagging would also let
  `cairn prune` reclaim *stale* cache stages. It does not: a moving `:builder` tag hands
  itself to each new stage, so superseded ones revert to untagged. Tagging per input hash
  would identify them but pin every 4.63 GB stage forever — worse. The design keeps one
  moving tag: the live cache is protected, stale stages correctly become collectable.

## 2026-07-25 (later still)

- **`BR-CLI-018` strengthened during implementation — never remove a tagged image.** The
  requirement said "keep the newest `<n>` per input hash (default: 1, the tagged one)",
  whose parenthetical merely *assumed* the newest is the tagged one. Writing the code made
  the gap visible: nothing forced it. Now stated as three concentric restrictions — cairn's
  own labels, then untagged only, then beyond keep-N — because a tag is a name something
  else may rely on, and removing a tagged image would require the engine's `--force`, the
  one flag that makes an accident possible. cairn never passes it.
- **Also required: say what is being left alone.** A 4.63 GB image absent from a prune
  report should read as a decision, not an oversight, so the count of non-cairn images is
  always stated along with why they are excluded.
- **Sizes corrected to decimal units** (`cairn images --local`). It reported 2.57 GB where
  `podman image list` reported 2.75 GB for the same image — binary arithmetic under a
  decimal label. A listing meant to be read beside the engine's own must agree with it.

## 2026-07-25 (later)

- **`ADR-032` closed — one image per input hash; prune only what cairn labelled.** Four
  consecutive builds of an unchanged manifest produced four image IDs, five nameless
  multi-gigabyte images, ~14 GB of orphans — and one unchanged primary tag. Diagnosis
  required separating **declared** inputs (`version-16`) from **resolved** inputs (the
  commit), which collapses the confusing cases: same declared/different resolved is a
  branch that moved; different declared/same resolved is a branch and a tag naming one
  commit. Image content is a function of resolved inputs alone — but the mapping is
  one-to-many the other way, since the image config carries a build-time clock.
- **`BR-BUILD-014` added — cairn will not rebuild an input hash it already holds.** An
  existing primary tag proves the inputs are unchanged; rebuilding can only mint a second
  digest, move the tag to it, and orphan the first. `--rebuild` overrides.
- **`BR-BUILD-008`: "immutable primary tag" corrected to "deterministic".** The original
  wording invited exactly the wrong inference and did so successfully. Three tiers of
  identity now stated inline — address (digest), deterministic name (cairn's tag,
  re-pointable), moving pointer (`latest`).
- **`BR-CLI-005` extended with `--local`**; **`BR-CLI-018` added for `cairn prune`.** An
  engine's image listing knows repository, tag, id, age, size — it cannot answer *why an
  image exists*. Everything needed is already stamped by `BR-BUILD-011`.
- **Prune scopes by label, never by danglingness — a cache-safety rule, not tidiness.**
  Brian observed that clearing dangling images made the next build enormously slower: on
  podman an untagged image may be a build-cache **stage**. cairn's labels land only at the
  final commit, so a label-scoped prune cannot reach the cache. Recorded as lessons §12.
  This retracts advice given earlier in the same conversation ("prune dangling, it's safe").
- **Left open deliberately:** whether the tag's `<legible>` half should keep deriving from
  the *declared* Frappe ref. It currently does, so one commit reached by a branch and by a
  tag yields two tag names for one image, and following `BR-BUILD-005`'s own advice to pin
  to tags renames every image for no change in content.

## 2026-07-25

- **`ADR-031` closed — three execution contexts; build transcript in attended CLI only.**
  `ADR-026` forbade custom log files outright, which `BR-DEPLOY-019` restated as an
  absolute. Brian's first real build exposed the cost: minutes of unscrollable engine
  output, lost to any stray `clear`. The initial proposal — "narrow it to the target
  side" — was rejected by Brian as too simplistic, since it ignores unattended **CI**
  builds where the filesystem is again the wrong place. The axis is not *where* but
  **who already owns and retains the record**: journald (daemon), the CI log viewer
  (unattended), nobody (attended). `ADR-026` amended, `BR-DEPLOY-019` scoped to name its
  one exception, new `BR-CLI-016` (transcript) and `BR-CLI-017` (timing), and
  `transcript_dir` added to `BR-CFG-008`.
- **Two findings folded into that decision.** Attended builds force plain engine progress
  — BuildKit's default TTY display redraws lines with ANSI escapes, which is what
  destroyed scrollback and would have made a teed file unreadable. And one `isatty()`
  check on stderr resolves all three contexts correctly, since neither journald nor a CI
  runner allocates a TTY: three contexts, two behaviors, one test.
- **`BR-CLI-016` corrected during implementation — transcript filename.** It first
  specified `<timestamp>--<image>-<primary-tag>.log`, which is unbuildable: the file has
  to be open *before* ref resolution, and resolution is what computes the tag. Named from
  the manifest's `image_name` instead, with the tag written inside the transcript. The
  `last-build.log` symlink means the filename is rarely typed anyway.
- **Timing is terminal + transcript only, never a provenance label** (`BR-CLI-017`).
  Duration is a property of a build *run* — cache state, machine, network — not of the
  image's inputs, which is what `BR-BUILD-013` makes guarantees about.
- **Multi-image staging analysed and parked** (`03-discussion-log.md`). After the first
  real `cairn build`, Brian proposed splitting the build into a sequence of
  content-addressed images so later steps could reuse earlier ones. Reading the vendored
  `images/custom/Containerfile` established two things: the expensive `base` stage is
  *already* cached across builds (`CACHE_BUST` is declared in `builder`, after every
  `base` instruction), and the app install is a **single atomic `RUN`** — Frappe clone,
  every app clone, pip installs and the asset build in one layer with one cache-bust
  knob. There is therefore no seam to split apps on without editing the vendored tree
  (`BR-VEND-004`, `ADR-001`) or forking (`ADR-021`). Four fork-free options recorded;
  the input-hash short-circuit is worth doing regardless. Decision deferred pending
  per-phase build timings — no requirements changed yet.

## 2026-07-24

- **The identifier rule made enforceable, after being violated twice.** Brian asked
  whether the rule was strong enough, having watched `BR` IDs reach user-facing output
  repeatedly. It wasn't — not because the wording was unclear, but because it sat in
  workflow step 6 (*"User documentation"*, a phase not yet begun), never named the
  channels that actually leak (`--help`, errors, warnings, progress), was absent from the
  binding *"For the AI (operating rules)"* section, and **had no enforcement**. Fixed on
  all four axes in `/CLAUDE.md`, the last via `tests/test_conventions.py`, which parses
  every non-docstring string literal in the package and fails on any `BR-`/`ADR-`
  identifier — including a test that plants a violation to prove the guard can fail.
  Recorded as lessons §11: prefer conventions that can fail a test; for a rule stated in
  prose, ask not "is the wording clear?" but "what would notice if I broke it?"
- **`BR-CLI-011` strengthened — "silence cuts both ways".** As written, the requirement
  listed only *destructive* examples (no auto-rollback, no auto-install, no data writes),
  and was implemented as "no silent destructive actions". That reading let `cairn build`
  run vendored-tree checks, three network round-trips, and a container build while
  printing **nothing** — reported by Brian as a build that "finished almost instantly"
  with no output at all. The requirement now also forbids a command *appearing to do
  nothing*, and requires verifying post-conditions instead of trusting an exit code: an
  engine that exits 0 without producing the image must be reported as a failure. A
  requirement ambiguous enough to produce the wrong implementation is a requirement
  defect, so it was fixed rather than only the code.
- **CLI help no longer leaks `BR` identifiers.** `/CLAUDE.md` requires internal docstrings
  to cite `BR` IDs while *external* descriptions omit them; because Typer renders a
  command's docstring as its `--help` text, every command was showing its `BR` ID to
  users. Commands now carry a user-facing `help=` on the decorator, leaving docstrings
  free to stay internal. Caught while reviewing `cairn --help` output, not by a test —
  worth a check before the Phase-6 user docs.
- **`ADR-030` records a rejected alternative: a per-deployment label namespace**
  (`com.microsoft.cairn.*` for a client Microsoft). Brian raised it and spotted the risk;
  the decisive objection is that **cairn reads these labels, not just writes them** — a
  target running `reconcile` holds an environment descriptor, not the build manifest, so
  it cannot know which prefix its own images used. The bootstrap never closes either:
  discovering a configured namespace still requires one fixed key to look it up under.
  Also recorded: a typo produces a perfectly valid label that fails silently, surfacing at
  rollback; and a namespace names *who defines the keys*, not who owns the image. The
  legitimate need underneath — recording whose image it is — belongs in
  `org.opencontainers.image.vendor`/`.title`/`.url`, which cairn could make settable later.
  Blast radius clarified: a wrong namespace does not make an image incompatible; it blinds
  cairn's own introspection, promotion, and rollback.
- **`ADR-030` — provenance label schema settled before the first push.** cairn-specific
  keys use **`com.datahenge.cairn.*`**, alongside standard `org.opencontainers.image.*`
  where one already fits. Reasoning was checked against the primary sources rather than
  convention-by-memory: the OCI image-spec only says keys **SHOULD** use reverse-DNS and
  is silent on both rationale and domain ownership, while **Docker's** documentation
  supplies both ("a domain **they own**"; "Don't use a domain … without the domain
  owner's permission"; the purpose being collision safety for automation). `io.cairn` /
  `dev.cairn` were **rejected as domains owned by others**; bare `cairn.*` was considered
  and rejected for forfeiting the collision protection cairn actually relies on, since it
  keys behavior off these labels. cairn deliberately does **not** set
  `org.opencontainers.image.vendor` — the distributing entity of a client's image is the
  client's to declare. Recorded in lessons §10 that a terse standard's operative guidance
  often lives in a dominant implementer's docs.
- **`BR-BUILD-008` clarified — a pin bump can change the tag with an unchanged manifest.**
  Affirmed by Brian as intended: the input hash covers *effective* build args
  (`BR-BUILD-010`), so a `frappe_docker` bump that moves a Containerfile default changes
  the image's inputs and therefore its tag. Stated explicitly because it will otherwise
  read as a defect to whoever meets it first; `BR-VEND-009` already makes pin bumps
  deliberate.
- **`BR-BUILD-007` revised — `CACHE_BUST` hashes *all* resolved commits, Frappe included.**
  As written it covered "the resolved app commits" only, which cannot satisfy its own goal
  ("a correct build MUST NOT require `--no-cache`"): `FRAPPE_BRANCH` enters the layer cache
  key by **name**, so a Frappe branch that *moves* keeps its name and would reuse a stale
  `bench init` layer. Brian approved including Frappe's commit, which also aligns the input
  set with `BR-BUILD-008`'s tag hash. Upstream's own recommended technique (an `apps.json`
  hash) has the same gap.
- **Two upstream corroborations recorded in `04-lessons-learned.md`.** The vendored
  `frappe_docker` docs turn out to state, in prose, two things this project had derived
  independently: **§1** — "BuildKit is the default builder starting with Docker Engine
  23.0" (`02-setup/02-build-setup.md:15`), confirming what was marked an inference about
  `BR-CLI-007`'s version floor; and **§2** — that `CACHE_BUST` exists precisely because
  secret contents are excluded from layer cache keys. **§4** gains a third: upstream
  documents `podman build` as a first-class equivalent with byte-identical flags,
  independent support for `ADR-027`. Reading the vendored docs earlier would have
  shortened that investigation.
- **`BR-CLI-007` revised — `git` added to the build-role preflight.** Implementing
  `resolve.py` surfaced that `git` is an unlisted build prerequisite: every manifest ref
  is resolved with `git ls-remote` (`BR-BUILD-005`), so a machine without git fails at
  resolution time rather than at preflight. Brian confirmed git is a prerequisite; the
  requirement now names it. No minimum version — `ls-remote` and its pattern matching
  predate every git a current distribution ships.
- **Lessons §9 — a pattern-filtered `git ls-remote` omits the peeled ref.** Found while
  implementing `resolve.py` (`BR-BUILD-005`): requesting `<ref>` alone returns an
  annotated tag's **tag object**, not the commit it peels to; `<ref>^{}` must be passed
  as a second pattern. Left uncorrected this would have recorded an object no clone ever
  checks out into provenance (`BR-BUILD-011`), the input hash (`BR-BUILD-008`), and
  `CACHE_BUST` (`BR-BUILD-007`) — well-formed and wrong. Unit tests passed throughout,
  because the stub returned what an *unfiltered* `ls-remote` returns; caught only by
  resolving against a real repository. No requirement changed.
- **`ADR-029` + `BR-CFG-012` — config discovery and precedence, finally documented.**
  `BR-CLI-014` promised "documented precedence" that was never written down; implementing
  `config.py` forced the gap. **Decided:** the manifest root and cairn's own project root
  are resolved by independent searches — `--manifest` if given, else the nearest
  `cairn.toml` walking up from the working directory, while the vendored tree stays
  anchored to cairn's root. They coincide in development and stop coinciding once cairn
  is `pip install`-ed, with no code change required. Build config layers
  `~/.config/cairn/config.toml` (machine-wide) under an optional `cairn.local.toml`
  **beside the manifest**, overriding key-by-key. `BR-CLI-014` now cites `BR-CFG-012`
  rather than promising documentation. `ADR-029` records one deferred gap: the wheel
  packages only `src/cairn`, so a pip-installed cairn has no vendored tree to build from
  — a `BUILD`-phase packaging concern.
- **Corrected `docs/plans/phase-1-build.md`**, whose illustrative manifest still showed
  the pre-approval `[cairn] name` and `[cairn.frappe] branch`. The approved
  `BR-BUILD-002` mandates `image_name` and `url`/`ref`; the plan is downstream of the
  requirements, so it was brought into line (and gained the `BR-BUILD-003` ordered-list
  comment that every shipped template must carry).
- **`ADR-027` — build engine is pluggable (`docker` | `podman`); deploy engine stays
  Docker.** Adopted after the measured buildah result. The unlock was recognizing that the
  build machine and the target are **different machines** whose only interchange is an OCI
  image in a registry, so `DEPLOY` needs no change at all — `BR-DEPLOY-005` already reads
  provenance over the (engine-independent) registry manifest API. Engine is auto-detected
  (prefer `docker`, else `podman`) and overridable via `engine =` in **local build config**,
  never in the portable `cairn.toml`. **Revised:** `BR-CLI-007` (role-aware preflight),
  `BR-BUILD-006` ("BuildKit secret" → "build secret"), `BR-BUILD-011` (engine's `--label`),
  `BR-BUILD-012` (exact build command), `BR-CFG-008` (engine is build config),
  `BR-CFG-010` (`docker login` / `podman login`); **amended** `ADR-003`. Engine floors:
  Docker v23+, podman v4+ (measured on 5.4.2). Carried risks: OCI-vs-v2s2 manifest format
  on push, and label readback across engines — both to confirm against a real registry.
  Rationale, evidence, and risks in `ADR-027`; motivation was avoiding a second engine
  managing nftables chains on a build-only laptop.
- **`ADR-028` — `cairn doctor` is role-aware, detected from context.** One package serves
  two roles (`ADR-018`), so a fixed preflight reports irrelevant failures. Build/control:
  build engine, vendored-tree integrity, config. Target: Docker + Compose, systemd,
  registry reachability. No flag in the common case (`BR-CLI-014`). The **target-role
  branch lands with `DEPLOY`**; doctor implements the build role today.
- **New document type — `docs/04-lessons-learned.md`.** Durable technical findings about
  the tools cairn builds on, kept separate from `BR` (what must be true), `ADR` (what we
  chose), and the discussion log (how we got there); each finding marked **measured** or
  **reasoned** and citing the IDs it illuminates. Added a row for it to `/CLAUDE.md`'s
  artifacts table. Seeded with seven findings from the Docker/podman investigation, the
  most consequential being **why `BR-BUILD-007` (`CACHE_BUST`) is a correctness
  requirement rather than an optimization**: a BuildKit secret's contents are excluded
  from the layer cache key by design, so editing `apps.json` alone will *not* invalidate
  the `bench init` layer. Also records that `Containerfile:144` strips app `.git`
  metadata — foreclosing image inspection as a provenance source and making
  `BR-BUILD-005`/`BR-BUILD-011` necessary rather than tidy.
- **Measured: buildah 1.39.3 / podman 5.4.2 satisfies the build side** (`BR-BUILD-006`,
  `BR-BUILD-007`) — secret mount honoured with `uid=`/`gid=`, no leak into layers or
  history, `CACHE_BUST` keying the cache in both directions. Retracts an earlier
  overstated claim that buildx has no podman equivalent. **No requirement changes**: the
  docs still name Docker (`BR-CLI-007`, `BR-BUILD-011`, `ADR-003`) and DEPLOY remains
  compose-shaped and untested against podman. Recorded so the question can be reopened
  cheaply if it ever is.
- **Phase 4 — second module (`cairn doctor`).** Implemented `src/cairn/doctor.py` (Docker
  Engine v23+ and buildx probes, plus the three vendored-tree preconditions) and
  `vendor.assert_build_inputs` — the first implementation of `BR-VEND-006`, deriving the
  required build inputs from the Containerfile's own context `COPY`s rather than a
  hardcoded list. Cites `BR-CLI-007/012/015`, `BR-VEND-005/006/007`. 20 unit tests
  (same `BR` IDs), ruff-clean; both the pass and fail paths verified end-to-end.
  **`BR-CLI-007` is landed partially by design:** its *"config valid"* leg awaits the
  config module and will be added when `config.py` lands (`BR-CLI-014`, `BR-CFG-008`,
  `BR-BUILD-002`). Decided then: a **missing** `cairn.toml` will WARN and keep exit 0
  (doctor is a machine preflight, legitimately run on a target host or before a manifest
  exists); a **malformed** one will FAIL. `--json` was deliberately not added — `BR-CLI-013`
  scopes it to `images`/status.
- **Phase 4 begins — first module (`VEND`).** Made the project a real Python package
  (hatchling, `src/` layout, `cairn` console script + `datahenge-cairn` alias, typer, ruff,
  pytest). Implemented `src/cairn/`: `project.py` (root discovery + vendor-source parsing),
  `vendor.py` (thin `ventwig` wrappers + drift/`.git` integrity checks), `cli.py` (Typer
  app with the `vendor status|sync` group). Cites `BR-VEND-003/005/007`, `BR-CLI-001/006/015`.
  9 unit tests (same `BR` IDs), ruff-clean; `cairn vendor status` verified end-to-end
  against the real vendored tree.

- **Non-requirement consistency sweep.** Aligned forward-looking docs with the approved
  requirements: project scope + overview reframed to **two pillars + a data-plane boundary**
  (was "three pillars"/"backup·restore·rollback"); `CLAUDE.md` `DATA` area updated; "DB
  snapshot" removed from the cairn metaphor. Added **supersession notes** to `ADR-012`
  (no pre-migrate snapshot) and `ADR-019` (cairn performs no restore), both pointing to
  `ADR-022`. Banner-marked the Phase-1 build plan as **superseded-in-part** (markers are
  labels not `.cairn/markers/`; no `cairn markers` command; `DATA` is a boundary). History
  docs (discussion log, this CHANGELOG) left as append-only record.
- **Requirements clarity audit.** Tightened all six requirement docs
  (`BR-VEND/BUILD/DEPLOY/DATA/CFG/CLI`) to crisp normative statements; migrated inline
  rationale/mechanism/verification into the cited ADRs and the discussion log. IDs and
  citations unchanged; approvals stand (clarity revision, not a design change).

- **`CLI` approved (`BR-CLI-001`…`015`). ALL SIX requirement areas now approved**
  (`VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`) — the Scribe Coding requirements phase
  is complete. Next: Phase 4 (modular code), one small module at a time.
- **`CLI` drafted (Pass 1)** — `docs/requirements/06-cli.md`, `BR-CLI-001`…`015`. Verb set:
  `build [--push]`, `push`, `new-tag`/`retag`/`retire` (create/move/decommission, with
  `--latest|--previous|--id|--from` selectors + typo-guards), `images`, `vendor`, `doctor`,
  `reconcile`. Conventions: `--dry-run`, prod-gate `--yes`, `--json` on reads,
  stdout/stderr logging + exit codes, config discovery. Sharpened `BR-DEPLOY-009` to a
  **declared environment list** (not bare convention).
- **Verified GHCR deletion is version-based** (no per-tag delete; deleting a version removes
  its image + all tags; public >5,000-download versions are undeletable). So `cairn retire`
  decommissions at cairn's layer only; the registry tag name lingers. Recorded in the
  deferred GHCR-cleanup note.
- **`DEPLOY` approved** (`BR-DEPLOY-001`…`020`) — all decisions resolved; only the deferred
  GHCR-side cleanup command remains (non-blocking). Five of six requirement areas approved.
- **Naming & packaging (`ADR-018` closed).** Single package/repo, name **`datahenge-cairn`**
  (`cairn` taken; `docker-cairn`/`frappe-cairn` falsely imply Docker/Frappe ownership;
  `datahenge-cairn` signals Datahenge + doubles the stone motif). Import package `cairn`;
  command **`cairn`** (+ `datahenge-cairn` alias). Split deferred behind an explicit
  trigger. Renamed the project **`docker-cairn` → `cairn`** throughout the docs (prose) and
  the local repo directory → `datahenge-cairn`; `pyproject` name → `datahenge-cairn`.
  Remote left untouched (new one to be created later). Also corrected the README pillars to
  match the current scope (two pillars + data-plane boundary; no DB backup/restore).
- **`DEPLOY` sequencing / health / failure / observability** (`BR-DEPLOY-016`…`020`).
  Single-flight reconcile; in-place recreate; `migrate` after every image enable (incl.
  rollback); health-gated success. **`ADR-025`**: deploy failure = **halt + report**, no
  auto-rollback (rollback stays manual). **`ADR-026`**: log to stdout/stderr only (host owns
  monitoring); optional best-effort **failure webhook** (transport-agnostic). Closed
  **`ADR-011`** (tagging settled by `BR-BUILD-008`).
- **`DEPLOY` secrets, single-site, prod gate** (`BR-DEPLOY-009`…`015`). Environment model:
  two halves joined by the tag; cairn **renders** the compose from the descriptor.
  **Closed `ADR-017`** (secret-agnostic: cairn references/wires but never handles secret
  values; registry pull via `docker login`; DB secrets via `compose.mariadb-secrets.yaml`
  recommended, `.env` supported). **Closed `ADR-016`** (single site per environment;
  multi-site deferred). Prod pointer moves require explicit confirmation; `install-app`
  to prod doubly explicit. Only sequencing/health remains open in DEPLOY.
- **`DEPLOY` opened, drafted (Pass 1, partial)** — `docs/requirements/03-deploy.md`,
  `BR-DEPLOY-001`…`008`: pull-based reconcile (target polls the env tag's digest);
  deploy/promote/rollback are one primitive (server-side retag, no rebuild); registry
  introspection reads provenance labels remotely; timer-driven GC keeps last N images and
  **never touches volumes**; cairn deploys to existing environments only.
- **Closed `ADR-010`** — desired-state pointer = the environment's moving registry tag
  (target polls; laptop advances by retag).
- **Added `ADR-024`** — reconcile is a thin orchestrator over docker/compose + registry
  API + systemd; Watchtower/Flux/ArgoCD evaluated and rejected (with reasons).
- **`DATA` approved** (`BR-DATA-001`…`008`) — the data-plane boundary area is settled.
- **Opt-in `bench install-app` (`ADR-023`).** A concrete case (deploying a 5-app image to
  a 2-app TEST site) showed `bench migrate` does *not* install newly-added apps. Decision:
  a default deploy is code-swap + `migrate` only (never changes a site's app set — least
  surprise); `bench install-app` is a second sanctioned Frappe command, **opt-in only**,
  delivered via the target's reconcile (no SSH). Added `BR-DATA-008`; amended `ADR-014`
  ("sole automatic" + install-app) and `ADR-022`.
- **Refined `BR-DATA-006` for accuracy:** cairn does not *itself* write to volumes, but the
  stack's own `configurator`/entrypoint reconcile the volume at every `compose up`
  (`ls -1 apps > sites/apps.txt`, `bench set-config -g …`, relink `sites/assets`) — Frappe's
  machinery, not cairn.
- **Established the data-plane boundary (`ADR-022`).** cairn ships code, not data: no SQL
  connection, no `bench execute`/`frappe` code, no DB movement; altering a target DB
  directly is impossible by construction. Sole exception: `bench migrate` after an image
  swap. Volumes/site-configs/`encryption_key` are aware-but-untouched.
- **Closed `ADR-014`** — `bench migrate` is the sole sanctioned (indirect) DB interaction;
  mandatory post-deploy, opaque, non-destructive. **Closed `ADR-013`** — backup / restore
  / DB-movement are out of scope.
- **Wrote `DATA` as a boundary area** (`docs/requirements/04-data.md`, `BR-DATA-001`…`007`,
  drafted). Reframed **Pillar 3** in the project scope; **revised approved `BR-CFG-005`/
  `006`** (no two-classes action; no volume seeding — `BR-DATA-006` supersedes); dropped
  "DB snapshot" from the cairn-marker concept.

## 2026-07-23

- **`CFG` fully approved** (build config signed off). `BR-CFG-010` refined: cairn may read
  a registry token from env / a local env file to perform a *transient* `docker login`,
  but still never stores credentials.
- **Closed `ADR-009`** — cairn is registry-agnostic; **GHCR is the recommended default**
  (ERPNext/GitHub ubiquity; fits the pull-only model). Follow-up: a GHCR setup runbook is
  needed (deferred to Phase-6 user docs).
- **`CFG` target config approved; build config drafted (Pass 1).** Added
  `docs/requirements/05-config.md`. Target (`BR-CFG-001`…`007`): env config lives on the
  sites volume and is never clobbered; opacity line (Frappe framework config understood,
  app config opaque); never overwrite Frappe-managed `site_config.json`; two config
  classes (data-bound `encryption_key` must travel vs env-authority must not);
  preserve-first + additive-seed provisioning. Build config (`BR-CFG-008`…`011`, drafted):
  build-time settings live in a local file separate from the portable `cairn.toml`;
  registry-agnostic; auth delegated to `docker login`; provenance labels ride with the
  pushed image (registry = image-and-metadata store).
- **Narrowed `ADR-009`** to "recommended default registry only" (cairn is now
  registry-agnostic via build config).

## 2026-07-21

- **`BUILD` requirements approved.** `BR-BUILD-008` tag composition settled as option (b)
  — human-legible slug + input-hash (`v16-a1b2c3d4`) + moving `latest`. Marked the
  `BUILD` row **approved**.
- **`BUILD` drafted (Pass 2).** `BR-BUILD-001`…`013` in `docs/requirements/02-build.md`.
  Verified bench pins by branch/tag only (no raw-SHA); adopted **Option A**
  (resolve-and-record commits, pin tags, warn on branch) — correcting the earlier
  "apps.json accepts commits" claim. Provenance is stamped as **OCI image labels**
  (not stored in the cairn tool repo); optional sidecar lives in the deployment dir.
  One item still open: `BR-BUILD-008` tag composition (pure hash vs. human-legible).
- **Closed `ADR-015`** (manifest `cairn.toml` schema + Option A app-pinning), moved to
  the closed register.
- **Added `ADR-021` (open)** — a deliberate fork of frappe_docker (MIT) as the sanctioned
  escape hatch for control unattainable while vendoring unmodified; deferred, not a
  default.
- **Manifest schema talk-through (pre-`BUILD`).** Settled: standalone `cairn.toml`
  (one file = one image, env-agnostic); `image_name`; special `[cairn.frappe]` section;
  **ordered** `[[cairn.apps]]` list = positional install order (no dependency solver);
  `[cairn.build]` knobs (`python_version`, `node_version`, `install_chromium`) +
  passthrough; no separate lockfile (marker is the record); input-deterministic (not
  hermetic) reproducibility bar. Redis/MariaDB versions are a DEPLOY concern (compose
  image tags), not image/manifest inputs. Documented the ordered-list rule prominently in
  `README.md` (required inline in every shipped template).
- **`VEND` requirements approved.** Brian signed off `BR-VEND-001`…`010` (hard-stop drift
  reasoning accepted; `ADR-020` parked open). Marked the `VEND` row **approved** in the
  requirements overview.
- **Began Phase 2 (requirements co-creation) with `VEND`.** Drafted `BR-VEND-001`…`010`
  in `docs/requirements/01-vendoring.md` (Pass 2): drift is a hard stop with no override;
  pin is immutable-intent and mechanism-agnostic; single vendored source.
- **Added `ADR-020` (open)** — strengthen upstream-pin immutability via a ventwig
  enhancement (SHA pinning and/or sync-time commit verification); non-blocking.
- **Adopted Scribe Coding** (Document-Driven AI Development) as the project methodology;
  added the ground-rules contract at `/CLAUDE.md`. Established the dual identifier
  system: `BR-<AREA>-NNN` (requirements) and `ADR-NNN` (decisions/ADRs).
- **Established the living-documentation infrastructure:** created
  `docs/requirements/` with `00-overview.md` (requirements root + ToC + conventions)
  and this `docs/CHANGELOG.md`.
- Requirements areas defined: `VEND`, `BUILD`, `DEPLOY`, `DATA`, `CFG`, `CLI`.
  Per-area requirement documents are pending Phase-2 co-creation.
- **Renamed the decision-record prefix `D-NNN` → `ADR-NNN`** across all docs
  (`ADR-001`…`ADR-018`), for an explicit, self-describing identifier that matches
  `cofferdam-app`'s ADR convention. No IDs or numbering changed — prefix only.
- **Set the build PoC target to Frappe v16 + ERPNext + BTU** (`Datahenge/btu@version-16`),
  superseding the earlier ERPNext-only PoC now that a suitable, non-contradictory custom
  app exists. Updated the Phase-1 plan's verification target and illustrative
  `cairn.toml` manifest (the actual `cairn.toml.example` file is deferred to BUILD
  implementation, after Phase-2 `BUILD` requirements exist).
- **Added `ADR-019` — strict decoupling from cofferdam** (cairn and cofferdam are
  mutually unaware). Reframed the Phase-1 plan's Pillar-3 note around a *generic*
  restore-scoping rule (never overwrite local env config on the sites volume) instead of
  cofferdam-specific enforcement; retracted the earlier `cofferdam validate` deploy
  invariant. Genericized the `CFG` area description in `CLAUDE.md` and the requirements
  overview (cofferdam now only a non-normative example).

### Predating this changelog (context)

The following were created before the changelog existed and are its baseline:
`docs/00-project-scope.md`; the decision register `docs/01-decisions-closed.md`
(`ADR-001`…`ADR-008`, `ADR-012`) and `docs/02-decisions-open.md`
(`ADR-009`…`ADR-011`, `ADR-013`…`ADR-018`); `docs/03-discussion-log.md`; and the Phase-1
build plan `docs/plans/phase-1-build.md`. Vendored upstream `frappe_docker` pinned to
`v3.2.1` via ventwig.
