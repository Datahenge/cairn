---
status: exploratory
owner: technical
purpose: ADR-073 — Whether cairn-adopt should own target-stack lifecycle (stop/start) and a maintenance state reconcile respects
---

# ADR-073 — Target-stack lifecycle and an "intentionally down" state

Prompted 2026-08-18 (Brian): with cairn managing a client's cloud VPS, he made a
configuration change to the Compose YAML and asked how to shut the containers down and bring
them back up. cairn has no answer — `start`/`stop`/`restart` exist only for
`cairn-registry` (`BR-REG-003`/`BR-REG-004`, `ADR-048`); the target stack has no lifecycle
surface at all. The procedure that actually works today is: stop `cairn-reconcile.timer`,
read `/etc/cairn/adopt.toml`, hand-assemble a `docker compose` invocation from its
`[compose]` block, act, restart the timer, then run `cairn-adopt reconcile`. Brian's
assessment: "extremely awkward and impractical."

## What makes it impractical, and who caused each part

**1. Multi-file override layering — inherited, not ours.** An operator on a stock
`frappe_docker` host types the same long `-f` chain. Upstream's usual workaround is to render
once (`docker compose config > docker-compose.yml`) and operate the rendered file;
`BR-DEPLOY-010` deliberately declines that, rendering at invocation and storing nothing so
no generated file can drift from the descriptor. A defensible trade, but it does forgo the
upstream ergonomic escape hatch.

**2. The compose variables left the disk — ours.** `_compose_environment` injects
`CUSTOM_IMAGE`/`CUSTOM_TAG`/`PULL_POLICY`/`SITES` per invocation. cairn never writes,
rewrites, or removes `.env`; `examine` only reads it to record an optional `env_file` path.
So `.env` survives adoption carrying whatever the operator originally put there, and a manual
`docker compose up -d` **succeeds** — starting whatever `.env` names, which after any
convergence or descriptor repoint is the previous image. Not impossible; silently wrong,
with no error and no signal. cairn's own code already treats this drift as a known fact:
`_survey_image` reads the running container "rather than from `.env`, because the two
disagree the moment somebody edits one without recreating the other," and `stage_reconnoitre`
captures `.env`'s `CUSTOM_*` values into a revert note precisely because cairn is about to
diverge from them.

**2a. Verified on a live host, 2026-08-18 — the fallback is another vendor's image.** Life
Scientific's test VPS was inspected to check factor 2 against reality. Its descriptor names
`directory = /opt/vps-setup/gitops`, `file = erpnext.yaml`, `overrides = []`, and **no**
`env_file` — `examine` probes only `<directory>/.env` and found none. The compose file is
*not* the rendered single-file `gitops` artifact its directory name suggests; it still
interpolates, and `CUSTOM_IMAGE`/`CUSTOM_TAG` are the only two variables in it, both written
with upstream defaults:

    image: ${CUSTOM_IMAGE:-frappe/erpnext}:${CUSTOM_TAG:-v16.26.1}

An `.env` does exist one directory up, at `/opt/vps-setup/.env`, but Compose never reads it:
auto-loading is scoped to the **project directory**, which `reconcile` sets to
`/opt/vps-setup/gitops` (`--project-directory`, `reconcile.py:392`). It carries no
`CUSTOM_IMAGE` or `CUSTOM_TAG` in any case — its keys feed the client's own provisioning and
restic backup tooling. `examine` recording no `env_file` is therefore correct, not a miss.

History confirmed by Brian 2026-08-18: the client stood this VPS up themselves from
`frappe_docker`, which reached for **`pwd.yml`** — the disposable, explicitly non-production
demo file — and the site originally ran stock `frappe/erpnext`. cairn adopted the host later
and took over. `/opt/vps-setup/` and its `gitops/` directory are surviving client tooling that
cairn superseded without displacing; the `:-frappe/erpnext` / `:-v16.26.1` defaults encode the
host's genuine pre-cairn state. A hand-run `up -d` therefore does not merely start a wrong
image — it reverts the host to before cairn, which is precisely what `stage_reconnoitre`
captures as a revert note at setup time (`provision.py:575-585`). This is also the live
instance of **`W-033`** (`ADR-068`'s take-ownership path): cairn is orchestrating a file it
does not own, authored for a demo, and reading it indefinitely.

So nothing on that host supplies those variables except cairn, at the instant `reconcile`
runs. A hand-run `docker compose up -d` starts stock `frappe/erpnext:v16.26.1` — not a stale
custom image, but a **different vendor's image that has never had the client's apps
installed** — against the live site, with no warning at all, because a `:-` default suppresses
Compose's unset-variable message. Factor 2 is therefore more severe than first written, not
less. (`bench migrate` was confirmed not looping on this host: zero converge passes in 24h.)

**2b. cairn's own recipe reproduces the hazard.** Not a client-only problem:
`src/cairn/recipe/compose.yaml:5` and `overrides/compose.migrator.yaml:9` both carry
`image: ${CUSTOM_IMAGE:-frappe/erpnext}:${CUSTOM_TAG:-$ERPNEXT_VERSION}`, inherited byte-for-byte
when `ADR-059` bootstrapped the copy — and `ADR-059` made cairn that file's owner, so the
default is cairn's responsibility now, not upstream's. `example.env` ships
`ERPNEXT_VERSION=v16.26.2`, so on any host following it an unset `CUSTOM_IMAGE` resolves
silently to stock `frappe/erpnext:v16.26.2`. `W-032` (provision a new environment from cairn's
owned stack) would propagate this to every future host. Tracked as `W-036` — **resolved 2026-08-18** by `BR-VEND-006`: Brian chose to drop the default so a missing value fails loudly. Factors 1, 2 and 3 remain open; this closed only cairn's own contribution to 2b.

**3. No way to express "intentionally down" — ours, and the actual blocker.** `State.is_converged`
requires `stack_up`, correctly refusing to call a stopped stack converged (that check exists
so a timer cannot hide an outage). But it makes planned maintenance indistinguishable from a
dead host: the timer pulls, `up -d`, and runs `bench migrate` within the poll interval. `cairn-reconcile.timer` was confirmed active and firing on the live host 2026-08-18, so this is an operating condition, not a hypothetical one. Even
a perfectly accurate `.env` does not fix this. cairn's state model has two values, converged
and broken, and maintenance is neither.

## Scope

**Brian ruled 2026-08-18 that this is in scope** — an operator has no practical alternative
route, so cairn cannot decline to provide one. This resolves the scope question, not the
design; `ADR-068` had already moved cairn beyond pure reconcile toward provisioning, so
lifecycle is not a new category of responsibility.

## Candidate designs — both open, neither chosen

**(a) Write-through `.env`.** `reconcile` updates `.env` on disk to match what it just
deployed. Drift disappears, a plain `docker compose up -d` becomes correct again, and
operators keep the tool they already know — no new verbs. Costs: it directly contradicts
`BR-DEPLOY-010`'s render-never-store rationale, and `.env` may hold `DB_PASSWORD` under
`BR-DEPLOY-013`, so cairn would be editing a secret-bearing file. It would not be *writing* a
secret, but `BR-DEPLOY-011` draws that boundary tightly enough to need an explicit ruling.
It also does nothing about factor 3.

*Reassessed 2026-08-18 after the live inspection above:* on a host shaped like Life
Scientific's, (a) is both cheaper and safer than first judged. The `BR-DEPLOY-011` collision
largely evaporates — that compose file interpolates **no** secret-bearing variable, so the
`.env` cairn would write holds only `CUSTOM_IMAGE`/`CUSTOM_TAG`, and creating it removes a
live footgun outright rather than merely reducing drift. The collision returns only for
deployments that do interpolate `DB_PASSWORD`, which cairn cannot know in advance without
inspecting the file. An earlier draft of this record speculated that (a) might be
*inapplicable* to a rendered `gitops`-style file; that speculation rested on a mistaken
reading of this host and is withdrawn.

**(b) Owned lifecycle commands plus a hold state.** A maintenance marker `reconcile` checks
and reports as *held* rather than converging, surfaced by `cairn-adopt doctor` so a forgotten
hold cannot hide; `stop`/`start`/`restart` that set and clear it as part of the operation, so
the safe sequence is one command rather than five. Optionally a `cairn-adopt compose -- <args>`
passthrough that execs the correctly-rendered invocation with the right environment — which
would fix factors 1 and 2 for *every* ad-hoc operation (`logs`, `ps`, `exec`, a one-off
`bench` command), not just stop/start. Costs: new surface area, and cairn-specific verbs for
an operator who already knows Compose.

Not mutually exclusive: (a) addresses correctness of ad-hoc operation, (b) addresses the
timer. (a) is an amendment to a standing requirement and therefore the heavier decision.

## Sequencing against `W-033` (Claude's observation, not a decision)

Candidate (a) writes `.env` into the Compose **project directory**. On the one live host, that
is `/opt/vps-setup/gitops/` — client-authored territory that `W-033` exists to retire. Building
(a) therefore means investing in a location the take-ownership path is meant to make obsolete,
and once cairn owns the compose file it could drop the `${CUSTOM_IMAGE}` indirection entirely
rather than feed it from a file. That does not kill (a) — it remains the only fix for hosts
cairn has adopted but not yet taken ownership of, which is every host today — but it reframes
it as a **bridge** with a foreseeable end, not a permanent mechanism. Worth Brian's attention
when ordering (a) against `W-033`.

## Narrowed by `ADR-074` (2026-08-18)

`ADR-074` settles who owns the compose file and where it lives, but **does not** settle this
record's fork. A draft of `ADR-074` claimed it did — asserting that retaining `${CUSTOM_IMAGE}`
makes an on-disk `.env` permanent architecture — and that claim was an AI inference, withdrawn
the same day. cairn needs no `.env`; the live host has none and converges correctly.

What actually changed here: candidate (a) is no longer framed as a bridge to be weighed against
`W-033`, because it is not a bridge and not obviously needed at all. It applies only if
hand-running `docker compose` is a capability worth supporting, which has not been asked
(`W-037`). Candidate (b)'s `compose --` passthrough is an alternative answer to that same
question, and avoids writing into a group-shared directory.

Factor 3 is untouched by any of this: no amount of file ownership lets cairn express
"intentionally down", so the hold state (`W-035`) remains the open design question this record
exists for.

## Open sub-questions, both needing Brian

- **Does a hold survive reboot?** `/run` (like the existing reconcile lock at
  `LOCK_PATH`) means a reboot resumes automatic convergence — safe against a forgotten hold,
  but a host rebooting mid-maintenance comes back up unexpectedly. `/etc/cairn` makes the
  hold durable and honest, but a forgotten one silently freezes deploys.
- **Are the verbs `up`/`down` or `start`/`stop`?** `cairn-registry` already ships
  `start`/`stop`/`restart`. Whether the target role should match it, or use the compose-`down`
  semantics a config change actually needs, is unsettled.
- **Does cairn writing `.env` collide with `BR-DEPLOY-011`?** Moot if (a) is rejected.

**Lean (Claude's recommendation, not agreed):** take (b), and treat the hold state as the
primary deliverable rather than the commands — a `stop` that loses a race with the timer is
worse than no `stop` at all, because it appears to have worked. Add the `compose --`
passthrough in the same pass if it stays cheap. **Revised 2026-08-18:** no longer defer (a)
— the live inspection shows it is not a drift-reduction nicety but the removal of a silent
wrong-image hazard, and on a host shaped like this one it is nearly free. Suggested ordering:
(b) first because it unblocks the operator, (a) close behind. Separately, and independently of
cairn: recommend cairn's **own** recipe drop its `:-frappe/erpnext` fallback (`W-036`), so a
missing variable fails loudly instead of silently substituting another vendor's image — the
client's file has the same defect, but cairn shipping it is the part cairn controls. *(BR-DEPLOY-003, BR-DEPLOY-010, BR-DEPLOY-011, BR-DEPLOY-013, BR-CLI-008, ADR-024, ADR-068)*
