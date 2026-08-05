---
status: exploratory
owner: technical
purpose: ADR-044 — Local git mirror for private-app reachability (not a revival of Option C)
---

# ADR-044 — Local git mirror for private-app reachability (not a revival of Option C)

Prompted by `BR-BUILD-016` (2026-07-27, Brian): a token has to reach two places — the
host-side `git ls-remote` and the actual clone inside the isolated BuildKit sandbox — and
only the second one is the hard problem, since the sandbox has no SSH access and no
credential store of its own. `BR-BUILD-016` solved it with a single operator PAT
(`$CAIRN_GITHUB_TOKEN`) embedded in the `apps.json` secret, scoped to `github.com` only and
redacted from every output that might echo it back. It ships and closes today's concrete
need: Brian's clients don't own the token-issuing decision for a repo he doesn't own,
so a client-issued fine-grained PAT is the only credential type that fits.

**The idea, sized honestly:** cairn could instead mirror a private app locally — using the
SSH deploy key Brian already has working host-side (`git clone --mirror`/`git fetch`,
outside the sandbox, no new credential type) — and serve that mirror to the build over an
address the BuildKit sandbox can reach without any credential at all (`docker build
--network=host`, or host-gateway addressing; either is a flag on the build invocation cairn
already constructs, not a change to the recipe's Containerfile). If it works, it doesn't
just avoid a second credential type — it eliminates `github_auth.py`'s entire reason to
exist: no token, nothing to scope to `github.com`, nothing to redact.

**This is not the `ADR-015` Option C being revived, even though both are "a git mirror."**
Option C existed to *fake commit-SHA pinning* — synthesizing a ref that resolves to an
exact commit, since `bench` accepts only a branch or tag — and was rejected as too heavy
for that job; cairn adopted Option A (resolve-and-record) instead, and nothing here
proposes reopening that. This mirror would touch none of Option A's pinning semantics —
refs stay branches/tags exactly as today. Its only job is making a private repo reachable
from an isolated sandbox without a credential. The "too heavy" objection is worth weighing
again on its own terms for *this* job, not inherited from the old one.

**What it would actually cost**, parallel to `stage_registry` (`cairn-provision` already
runs one long-lived local service, so this isn't a new category of thing to operate):
1. A new builder-only provisioning stage: mirror each private app via the existing deploy
   key, no new credential plumbing.
2. A freshness mechanism — a fetch before `resolve.py` runs, so ref resolution never sees a
   stale mirror. Open question: every build, or a timer, or on-demand.
3. `apps.json`'s URL rewritten to the local mirror for any app configured to use one — the
   same one-seam shape `github_auth.authenticated()` already established, just without a
   secret to guard.
4. Binding/reachability: almost certainly `127.0.0.1`-equivalent, same posture as the
   registry; `--network=host` needs `--allow-insecure-entitlement network.host` if cairn
   ever runs against a `docker-container` buildx driver rather than the default local one —
   untested, not yet confirmed to be transparent in practice.

**Lean:** deferred, not a default. `BR-BUILD-016` already meets the concrete need with
work already spent, tested, and documented. This is a strong replacement candidate — worth
revisiting if PAT-based auth proves insufficient (a client that will not issue *any*
token, or per-app/per-org credential sprawl the "one token" simplification can't absorb) —
but is new operable infrastructure, not a small change, and nothing today forces the
question. *(BR-BUILD-016, ADR-015, ADR-021)*
