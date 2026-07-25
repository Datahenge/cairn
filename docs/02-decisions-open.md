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

### ADR-037 — How an `install-app` opt-in reaches a target
**Raised:** 2026-07-25 · **Open — blocks nothing currently shipped**

`BR-DEPLOY-003` permits `bench install-app` during a reconcile, but **only if an opt-in
directive is present**, and `ADR-023` forbids auto-install outright. `BR-CLI-004` says the
opt-in is expressed control-side, as `--install-app <apps>` on `new-tag`/`retag`.

Nothing carries it across. The two halves of an environment are joined only by the tag name
(`BR-DEPLOY-009`), and a tag name has no room for a payload. So a directive named on the
laptop cannot presently be seen by the box.

**`cairn reconcile` therefore does not run `install-app` at all**, and says so in its own
docstring. That is the correct behaviour under `ADR-023`: absent a decided transport,
installing an app would be exactly the auto-install the decision forbids. A new app is
installed by the operator, once, with `bench install-app` — which `BR-DEPLOY-007` already makes
their responsibility for site creation.

**Options, none yet chosen:**

- **(a) An image label.** The control side already writes provenance labels
  (`BR-BUILD-011`) and the target already reads them remotely (`BR-DEPLOY-005`), so the
  channel exists and costs nothing new. But a label is a property of the *image*, and "install
  this app" is a property of a *deployment event* — the same image promoted to a second
  environment would carry an instruction that was meant for the first, and would re-run there.
- **(b) A field in the target descriptor.** Honest about locality — the operator states what
  this host should have installed. But it moves the opt-in from the person doing the deploy to
  a file on the box, which is not what `BR-CLI-004` describes, and it drifts: the field stays
  true-looking long after the install happened.
- **(c) A separate control-side artifact** the target reads alongside the tag (a second small
  manifest in the registry). Keeps the deployment event separate from the image, at the cost of
  the second source of truth `ADR-033` and `ADR-034` both worked to avoid.
- **(d) Leave it out.** `install-app` stays an operator action forever, and `BR-DEPLOY-003`'s
  clause is struck rather than implemented. The cheapest option, and the one currently in
  force by default.

**A question that should be answered first:** how often does this actually happen? Adding an
app to an existing site is a rare, deliberate act, usually accompanied by other manual steps.
If it is rare enough, **(d)** is not a compromise but the right answer, and the clause in
`BR-DEPLOY-003` is the thing that is wrong.

**Trigger:** the first time an app must be added to a live environment. Note what was actually
needed at that moment, then decide.
*(BR-DEPLOY-003, BR-CLI-004, BR-DEPLOY-009, ADR-023, ADR-033, ADR-034)*
