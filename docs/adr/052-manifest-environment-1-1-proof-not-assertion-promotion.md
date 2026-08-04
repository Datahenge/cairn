---
status: authoritative
owner: technical
purpose: ADR-052 — Manifest:environment is 1:1; promotion is proof, not assertion
---

# ADR-052 — Manifest:environment is 1:1; promotion is proof, not assertion

**Decided:** 2026-08-04
**Supersedes:** `ADR-033` (the `[cairn.environments]`/`[cairn.declared_environments]` table),
`ADR-050` (the `new-tag`/`retag` → `assign-tag` merge, itself only hours old). **Relates to:**
`ADR-010`, `ADR-047`, `ADR-049`, `ADR-051`.

## Raised

Working through what "automatic CI/CD" actually means for cairn (Brian, testing against a real
client VPS): several independent environments (`test`/`staging`/`prod`), each tracking its own
git branch, each converging within minutes of a push with no SSH, no manual CLI, no GitHub
Actions dependency, no reliance on the client's git-merge discipline. Several designs were tried
and rejected in the same conversation before this one held:

- **GitHub Actions as the trigger** — rejected. Requires an internet-facing registry (a cloud
  runner has to reach it to push) and requires trusting the client's merge conventions
  (`on: pull_request: closed, merged: true` only means what it's supposed to mean if merges
  happen the way the workflow assumes).
- **`assign-tag --from <other-env>`, an explicit "promote" command** (this session's own
  `ADR-050`) — rejected once stress-tested. From git's own perspective there is no such thing as
  "promotion," only a ref being repointed to a different commit; a human or a script *asserting*
  "this is a promotion" is exactly the kind of ambiguous command a merge-commit (vs. a
  fast-forward) can silently invalidate. An assertion is not proof.
- **Auto-resolving a bare environment name to its owning manifest** — rejected once the
  uniqueness key settled on (client, image_name, environment) rather than environment alone: the
  same name can legitimately repeat across different `image_name`s within one client (mirroring
  the registry's own tag scoping — a tag lives inside one repository,
  `<registry>/<namespace>/<image_name>`, and different image_names are different repositories
  with independent tag lists), so a bare name is ambiguous without also knowing which
  `image_name` it belongs to.

## Decision

**An environment is a fact about one manifest, not a name in a shared table.**
`[cairn.declared_environments]` (a table, any cardinality, `ADR-033`/`ADR-049`) is replaced by a
single optional scalar: `[cairn] environment = "production"`, sibling to `image_name`/`series`.
A manifest declares at most one environment. The environment's name *is* its registry tag —
`ADR-033`'s name≠tag flexibility is dropped as unneeded complexity now that a manifest only ever
serves one environment.

**Uniqueness is (client, image_name, environment), not environment alone.** This is not an
arbitrary choice — it mirrors the registry's own scoping exactly, since an environment name is
nothing but a tag, and a tag's uniqueness is already scoped to one repository
(`<image_name>`) within one client's namespace.

**No command takes an `--environment` argument, ever.** Every environment-targeting command
takes `--manifest <path>` and reads the environment from the file. There is never a second place
for the name to be typed, and therefore never a way for two arguments to silently disagree.

**Promotion is proof, not assertion.** `assign-tag` becomes a cheap, no-build command:

1. Take `--manifest <path>`.
2. Resolve that manifest's refs to their *current* commits (`resolve.py`, the same resolution
   `build` already performs).
3. Compute the deterministic primary tag from those resolved inputs (`tagging.primary_tag()` —
   a pure hash of resolved commits + effective build args, `BR-BUILD-008`).
4. Ask the registry whether an image already exists under that exact tag.
5. **Found:** retag this manifest's declared environment onto that digest — an atomic pointer
   reassignment (`registry.retag()`, unchanged); a tag is a single mutable pointer per
   repository, so moving it inherently stops it resolving to whatever it pointed at before.
   Nothing to build here.
6. **Not found:** report that, and do nothing. `assign-tag` never triggers a build.

This is what makes "`staging` merged into `prod`" safe without inferring anything from *how* the
merge happened: `prod`'s own manifest resolves its own current refs, and either an image already
exists matching that exact resolved state (because `staging` already built it) — in which case
`prod` gets it, proven, byte-for-byte — or it doesn't, in which case there is nothing to promote
and `prod` needs its own build. The same mechanism gives rollback for free: reset the tracked
branch to an earlier commit, run `assign-tag` — if that commit's image still exists in the
registry (not yet GC'd), it retags instantly, no rebuild. No `--previous`/`--id`/`--from`
selectors are needed to express any of this; `ADR-050`'s selector menu is retired along with it.

**`build` gains an optional, argument-free `--assign-tag` flag** — after a successful `--push`
(or a no-op short-circuit), it performs the same retag step, reusing the digest `build` already
resolved rather than re-running `assign-tag`'s resolve-and-check from scratch. This is what lets
`setup-timer`'s generated script collapse to two lines instead of gluing two commands with shell:

```bash
cairn-build build --manifest "$MANIFEST" --push --assign-tag --yes
cairn-build prune --keep 1 --yes
```

**`build` also gains a registry-side fallback for "already built?"** `build.existing_image()`
today only checks the local engine (`docker image inspect`) — a build machine with a cold local
cache, or a second/replacement build machine, would rebuild something the registry already has,
even though the primary tag is fully deterministic and therefore trivially checkable remotely.
Checked whenever a registry is configured, not gated on `--push`.

**`setup --client` gains `--environment` and scaffolds one distinctly-named manifest per call**
— `cairn-build setup --client acmecorp --environment test` scaffolds `cairn_test.toml`; run
again with `--environment staging` for `cairn_staging.toml`. A client directory holding several
environments now holds several files, not one shared table.

**`doctor` gains a duplicate-declaration check**, extending its existing (informational) known-
manifests listing: enumerate every `.toml` under a client directory, read each one's
`image_name` + `environment`, and flag any (image_name, environment) pair that repeats within
that client. This is validation only — nothing resolves a bare name to a manifest; every command
still takes `--manifest` per the rule above.

**`retire` takes `--manifest <path>`** instead of a positional `<env>`, for the same reason as
`assign-tag`.

## Consequences

- `environments.py` loses most of its surface: `declared()`, `require()`, `Selector`, and
  `plan_move`'s `--from`/`--previous`/`--id` branches all go. What survives is the
  resolve→check→retag-if-found sequence above.
- `EnvironmentExistsError` (already dead after `ADR-050`) stays dead;
  `UnknownEnvironmentError` is reviewed for whether anything still raises it under a
  `--manifest`-only model.
- No live client deployment has used any of `new-tag`/`retag`/`assign-tag`'s selector interface
  yet (`open/OPEN_WORK.md`'s `W-001` is still open) — this is a clean cut, not a deprecation
  shim, consistent with every other pre-1.0 change this session.
*(BR-BUILD-001, BR-BUILD-002, BR-BUILD-008, BR-CLI-004, BR-CLI-009, BR-CLI-010, BR-CLI-022,
BR-CLI-023, BR-DEPLOY-004, BR-DEPLOY-009, BR-DEPLOY-009a, ADR-010, ADR-033, ADR-047, ADR-049,
ADR-050, ADR-051)*
