# Open Decisions

Unresolved questions, each with current lean/recommendation where one exists.
IDs continue the `ADR-00N` sequence; when closed, a decision moves to
`01-decisions-closed.md` keeping its ID.

_Last updated: 2026-07-25_

---

### ADR-020 — Strengthen upstream-pin immutability (ventwig enhancement)
The vendored pin currently uses a release **tag** (ventwig 0.2.0 clones via
`git clone --depth 1 --branch <ref>`, which cannot take a raw SHA). Tags are mutable
upstream — they can be force-moved or deleted. Our committed tree + `.ventwig.lock`
already makes *builds* immutable regardless (`ADR-007`), but a *re-sync* could silently
pull a moved tag. Options:
- **(a)** status quo — tag pin + committed-tree/lock anchor;
- **(b)** teach ventwig to pin by immutable commit **SHA**;
- **(c)** teach ventwig to verify, on `sync`, that `ref` still resolves to the commit
  recorded in `.ventwig.lock`, and refuse on mismatch;
- **(b)+(c)**.

**Lean:** at minimum (c) — cheap, high-value guard against ref movement whether pinning
by tag or SHA — ideally (b)+(c). This is a ventwig enhancement (Brian owns ventwig),
tracked here; **not a cairn blocker**. `BR-VEND-002` is written pin-mechanism-
agnostic so nothing here changes when this lands. _Open._

---

### ADR-021 — Deliberate fork of frappe_docker as the sanctioned escape hatch
frappe_docker is **MIT-licensed** and adds *no capability* to Frappe/ERPNext — it merely
codifies the documented manual install into a repeatable recipe. So forking it into our
own spinoff is legally permitted (retain the notice) and defensible by transparency
(publish the Dockerfile + build commands).

**Stance:** a fork is the **sanctioned escape hatch** for control we cannot get while
vendoring unmodified (`ADR-001`) — e.g. hard commit-pinning (see `ADR-020`, and the
build immutability model in `docs/requirements/02-build.md`), which is impossible via
bench's `git clone --branch` without editing the vendored tree. If such a need becomes
essential, the honest move is a *deliberate, eyes-open fork recorded as its own decision*
— not silent local edits (which `BR-VEND-004` forbids) nor Option C's build-time git-
mirror machinery.

**Cost to weigh when the time comes:** a fork transfers frappe_docker's real value — the
*continuous maintenance* of a correct recipe as Python/Node/wkhtmltopdf/Debian/Frappe
churn — onto us, and forfeits the deliberate drift-checked sync we built with ventwig
(`ADR-007`). Therefore: **deferred, not a default.** Revisit only against a concrete,
essential need. _Open._

---

#### Fork pressure register

"Concrete, essential need" is easy to assert and hard to evidence. Accumulated friction is
*not* evidence — most of what cairn does (transcripts, timing, tagging, pruning, the
input-hash short-circuit) is cairn's own and a fork would change none of it. Only the
constraints below are genuinely upstream's, and only these count. Dated as encountered, so
the eventual decision rests on a list rather than a feeling.

**1. The atomic `bench init` layer — no per-app cache seam.** *(2026-07-25, Brian)*

The vendored Containerfile installs Frappe **and every app** in a single `RUN` guarded by
one `CACHE_BUST` (`frappe_docker/images/custom/Containerfile`, builder stage). There is no
seam between Frappe and the apps, or between one app and the next, so changing any one app
commit re-clones everything and rebuilds all assets.

Why this is more than an inefficiency, in Brian's own workflow: a client engagement pins
**one** Frappe/ERPNext version and then spends *weeks or months* iterating on custom apps
without ever bumping it. The unchanged 95% is re-fetched and re-built on every custom-app
commit — which is not an occasional cost but the **dominant** one, paid several times a
week for the life of an engagement. The one case the current design handles worst is the
case that actually recurs.

Mitigations short of a fork, and their ceilings: `BR-BUILD-014`'s short-circuit removes
*redundant* rebuilds but not *legitimate* ones; registry-backed cache helps cold machines,
not this. Neither reaches the seam. **This is the strongest single argument on the list.**

**A second cost, found 2026-07-25 while documenting GHCR.** The argument above was made
entirely in build minutes. There is a money cost too, and it compounds the same way. Because
the atomic step produces one multi-gigabyte layer rather than a small one, a single-line
change to a custom app yields a **new ~2.75 GB layer** — so layer sharing, which is exactly
what should make an incremental push and pull cheap, buys almost nothing here. Every
custom-app commit that reaches an environment therefore costs close to a full image in
private-registry **storage** (multiplied by the versions retained for rollback headroom) and
close to a full image in **outbound transfer** on every target that converges. At the
allowances bundled with GitHub's personal and small-team plans, one image can exceed the
entire included storage. A per-app seam would make the common case a small layer, which is
the same fix for both costs. Recorded because the register is supposed to accumulate
evidence: this is a second, independent consequence of one upstream constraint, not a second
argument.

**2. Commit-level pinning is impossible through bench.** *(2026-07-25, Brian)*

`bench init --frappe-branch` / `bench get-app` take a branch or tag, never a raw SHA
(`BR-BUILD-005` records the constraint; `ADR-020` the analogous one for our own vendored
pin). Brian's point sharpens why that matters in this ecosystem specifically: `version-15`
and `version-16` are **fast-moving targets**, not stable lines — Frappe maintainers backport
continuously, so a branch materially changes underneath you within days.

The consequence is narrow but real. cairn resolves-and-records, so *what was built* is
always known. But an image cannot be **rebuilt** from its manifest once the branch has
moved: the recorded commit is a fact about the past that the manifest can no longer express.
Rollback therefore depends on the stored image being retained (`ADR-012`, `ADR-025`), and
the registry is the only durable copy of a given build. That is a coherent model, not a
defect — but it is strictly weaker than commit-pinning, and the gap is upstream's.

**3. Upstream changes the recipe in a way that breaks us and won't take a patch.**
*Not yet encountered.* Recorded here so it is looked for rather than rationalised.

**Countervailing evidence, recorded to keep the register honest.** On 2026-07-25 the
vendored recipe was measured working exactly as designed: the `base` stage cached across
builds, the `builder` stage reused in 0.762s, `CACHE_BUST` keying the cache in both
directions. The 4.63 GB stage that prompted the day's investigation is a *correct, current*
recipe — Python 3.14, Node 24.13, wkhtmltopdf, Chromium, weasyprint dependencies, non-root
nginx — and maintaining it is precisely the burden a fork assumes.

**Trigger:** revisit when item 1 is *measured* (time a rebuild after a single custom-app
commit, against a first build) and the cost is shown to be structural rather than tolerable.
Until then this remains deferred.

---

### ADR-044 — Local git mirror for private-app reachability (not a revival of Option C)
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
already constructs, not a change to the vendored Containerfile). If it works, it doesn't
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
