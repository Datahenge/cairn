---
status: exploratory
owner: technical
purpose: ADR-071 — Whether cairn-build doctor's --all should extend beyond the build-timer check to every manifest-scoped check
---

# ADR-071 — Should `--all` extend to `config` and `github reachability` too?

Prompted by `ADR-070` (2026-08-06, Brian): `cairn-build doctor` gained `--all`, which walks
every manifest under `/srv/cairn/*/*.toml` for the new build-timer check. Brian asked, mid-design,
whether `--all` should broaden every manifest-scoped check — `config` and `github reachability`,
not just the timer — into a full "audit every manifest on this host" mode. Deliberately narrowed
to the timer check only for `ADR-070`, to ship a well-bounded change first; this file tracks the
broader question for later.

**What full scope would actually cost**, so the deferral is an informed one, not just inertia:

1. `check_config` today validates **one** manifest together with the host-level `builder.toml`/
   `BuildConfig` in a single call, returning both — under `--all` these split: `BuildConfig` is
   host-level and stays a single check, while manifest validity becomes a per-manifest loop,
   parallel to how the timer check now works.
2. `check_known_manifests` already enumerates every manifest under `/srv/cairn/` for its
   duplicate-declaration check, but silently swallows a manifest that fails to parse
   (`except CairnError: continue` in `doctor.py`) — it was never asked to report *that*, only
   collisions among the ones that parse. A full-scope `--all` surfacing "config" per manifest
   would need that swallow fixed so a malformed manifest is reported once, not silently absent
   from every enumeration.
3. `check_github_reachability(manifest)` takes one already-loaded `Manifest` and resolves its
   refs; extending it to `--all` means calling it once per manifest found (each with its own
   live network cost — real API calls per app per manifest — worth being deliberate about on a
   host with many client manifests before making it the default `--all` behavior).

None of this is hard, but it is more than the timer check alone, and touches a check
(`check_known_manifests`) with an existing silent-failure gap worth fixing carefully rather than
piggybacking on an unrelated change.

**Lean:** revisit once `ADR-070`'s narrower `--all` has shipped and been used for a while — if
the timer-only scope proves people still want a one-shot "is everything on this host okay"
sweep, do the `check_config` split and the `check_known_manifests` fix together, deliberately,
rather than as a side effect of this ticket. *(BR-CLI-007, BR-CLI-022, ADR-070)*
