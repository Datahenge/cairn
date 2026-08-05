---
status: archived
owner: technical
purpose: ADR-021 — Deliberate fork of frappe_docker as the sanctioned escape hatch
---

# ADR-021 — Deliberate fork of frappe_docker as the sanctioned escape hatch

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

**4. Two incompatible compose shapes, no path between them, and nothing that warns you
which one you're on.** *(2026-08-05, Brian — live on a client VPS, adopting a pre-existing
deployment)*

`cairn-adopt reconcile` ran clean against a real target — pulled the built image, brought the
stack up, ran `bench migrate`, verified health, reported `Converged to sha256:...`. Confirmed
directly afterward (`docker inspect erpnext-backend-1 --format '{{.Image}}'` against the
built image's own digest) that nothing had actually changed: `backend`, and every other
erpnext-app service, was still running the old public image. `reconcile`'s convergence
check was fooled, not lying — see the mitigation below.

Root cause, found by diffing the vendored tree against the client's compose file: frappe_docker
ships **two structurally different compose files for the same site**, and nothing distinguishes
which one a given deployment is running on short of reading it line by line.

- `compose.yaml` — the production file cairn's own deploy model (`BR-DEPLOY-003`,
  `CUSTOM_IMAGE`/`CUSTOM_TAG`) is built against — correctly parameterizes the image via a YAML
  anchor merged into every relevant service: `x-customizable-image: &customizable_image` →
  `image: ${CUSTOM_IMAGE:-frappe/erpnext}:${CUSTOM_TAG:-$ERPNEXT_VERSION}`.
- `pwd.yml` — frappe_docker's **one-line quick-start**, the very first thing a new adopter
  meets in its own docs — hardcodes `image: frappe/erpnext:<version>` literally, once per
  service, roughly nine times, with no substitution mechanism of any kind.

The client's site was deployed from something structurally identical to `pwd.yml`: the same
count and shape of hardcoded `image:` lines, no anchors, no `${CUSTOM_IMAGE}` anywhere in the
file. `compose.yaml`'s mechanism is the *correct* answer and cairn is built against it
correctly — the gap is entirely upstream's: frappe_docker offers no detection, no conversion
path, and no warning that the file most new adopters reach for first is a dead end for the
exact custom-image migration `cairn-adopt` exists to perform. An operator — or a tool adopting
their site — only discovers it by diffing two files by hand, as happened here.

**Mitigation, cairn-side, partial:** `reconcile`'s own convergence check (`running_digest()`)
verifies that a local image with the right tag+digest *exists*, not that any container is
*running* it — the same gap that let this report success falsely. Comparing the `backend`
container's actual running image ID against the desired digest post-convergence would turn
this into a loud, immediate failure instead of a silent no-op that looks like success. That
closes the "false convergence report," not the underlying compose incompatibility — the
operator still has to hand-edit `pwd.yml`-shaped files before adopting them.

**Why this counts, not just friction:** every adoption of a pre-existing, hand-deployed site —
`cairn-adopt`'s primary scenario — carries this risk, silently, for any site whose compose file
traces back to `pwd.yml` rather than `compose.yaml`. That is plausibly the common case, not the
edge case, since `pwd.yml` is the fastest path to a working site and the one frappe_docker's
own docs lead with. Asking every public `datahenge-cairn` user to hand-diff and patch whatever
frappe_docker generated for them, before `cairn-adopt` can be trusted, is not a one-off cost —
it recurs per adopter.

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

**Retired 2026-08-05, superseded by `ADR-059`.** The fork-vs-no-fork question this ADR posed
is moot: cairn now owns its Docker build recipe outright rather than vendoring
`frappe_docker` at all, which grants everything a fork would (per-app cache seam, commit-level
pinning, one canonical compose shape) without forking anything. Items 1, 2, and 4 above
dissolve under ownership; item 3 was never encountered and retires with the rest of the
register.
