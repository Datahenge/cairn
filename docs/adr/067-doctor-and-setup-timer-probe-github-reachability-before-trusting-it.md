---
status: authoritative
owner: technical
purpose: ADR-067 — `cairn-build doctor` and `setup-timer` probe github.com reachability live, reusing resolve.resolve_manifest, instead of only naming the token file as a possibility
---

# ADR-067 — `doctor` and `setup-timer` probe `github.com` reachability before trusting it

**Decided:** 2026-08-06 (Brian, reviewing `ADR-065`'s `EnvironmentFile=-` path — it wires a
missing token, it never detects one).

**Amends:** `BR-CLI-007`, `BR-CLI-023`. **Relates to:** `ADR-065`, `BR-BUILD-016`.

## The gap

`ADR-065` gave the build timer a path to a per-client token
(`/etc/cairn/<client>/github-token.env`), but never a way to know whether that path needed
anything in it. Two consequences, found by inspection rather than incident:

1. **`cairn-build doctor` has no check at all.** `run_build_checks()` covers config, engine,
   buildx, disk, memory, git, build inputs, shared config dir, and known manifests — never
   a manifest's `github.com` reachability.
2. **`setup-timer` prints an unconditional warning, not a check.** `stage_timers_build()`
   always appended the same line naming the expected file — regardless of whether the
   manifest has a private app, and regardless of whether the file already exists and is
   correct. An operator who already did everything right sees the identical warning as one
   who forgot the file entirely.

The eventual failure is not silent — `resolve.py`'s `RefResolutionError` already names
`$CAIRN_GITHUB_TOKEN` as a candidate fix (`BR-BUILD-016` point 5) — but it is not
*proactive*: nothing surfaces it before the timer is enabled, or before it fires unattended
for the first time.

## Why this wasn't caught by design

Cairn has no static signal for "this app is private" — the manifest schema deliberately
carries none (`ADR-065`: portable, secret-free). The only place that ever finds out is a
live `git ls-remote`, which today only runs inside an actual build.

## Decision

Reuse that same live check as a preflight, in two places, at two different fidelities:

**`cairn-build doctor`** gains a check that calls `resolve.resolve_manifest(manifest)` —
the exact function `build` itself calls — under a try/except, reporting FAIL with the
`RefResolutionError` message (already actionable, per `BR-BUILD-016` point 5) on failure.
This runs with whatever `$CAIRN_GITHUB_TOKEN` the invoking shell has exported, mirroring
`cairn-build build`'s own interactive path (`ADR-065`: "a manual build is unaffected").
Skipped when no manifest is found, consistent with `check_config`'s existing "missing
manifest warns, doesn't fail" rule. This is a genuine, if incidental, expansion: it also
catches a moved or deleted ref for *any* app, not just an auth failure — a manifest-wide
"will this actually resolve" preflight, the same shape as `cairn-adopt doctor`'s existing
`check_registry_reachable()`.

**`cairn-build setup-timer`** gains a gate, run before any file is written (`BR-DEPLOY-021`
point 5, "gates before acting," already binding on `setup-timer`). It must answer a
different question than doctor's: not "does my current shell have a token," but "will
*this unit*, using only what its `EnvironmentFile=` supplies, resolve every ref." So the
check simulates that narrower environment — the parsed contents of
`github_token_env_file(client)` if that file exists, otherwise no token — and deliberately
does **not** fall back to the operator's own exported `$CAIRN_GITHUB_TOKEN`, since a
systemd unit never inherits it either (the exact mismatch `ADR-065` fixed for the token's
*path*; this closes it for the token's *presence*). On failure, `setup-timer` refuses —
writes and enables nothing — and reports the same actionable message doctor would,
naming the expected file. On success, the old unconditional warning is dropped entirely:
a passing check already proves whichever is true (no private app, or the file is already
right), so there is nothing left to warn about.

`github_auth.py`, `resolve.py`, and `build.py` are unchanged — same as `ADR-065`, the fix
is reuse and orchestration, not a token-resolution redesign.

## Consequences

- `cairn-build doctor` now requires network reachability to every manifest app's remote,
  not only `github.com` ones — a new cost, accepted the same way `cairn-adopt doctor`
  already accepts it for registry reachability. A manifest-less `doctor` run (legitimately,
  before one exists) is unaffected, since the check only runs when a manifest was found.
- `setup-timer` becomes network-dependent and can refuse on a transient outage even when
  the manifest and token file are both correct. Accepted: the operator re-runs once
  connectivity returns, the same recourse `setup`'s own gate-before-acting checks already
  assume elsewhere.
- `doctor.check_config()`'s return signature gains the parsed `Manifest` alongside the
  existing `BuildConfig`, so the new check can reuse it without a second parse.
- `BR-CLI-007` and `BR-CLI-023` (`docs/requirements/`) rewritten to describe the check and
  the gate.
- A new `docs/open/OPEN_QUESTIONS.md` entry records this, resolved, pointing here.

*(BR-CLI-007, BR-CLI-023, BR-BUILD-016, BR-DEPLOY-021, ADR-065)*
