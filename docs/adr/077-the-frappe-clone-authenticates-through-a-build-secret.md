---
status: authoritative
owner: technical
purpose: ADR-077 — the builder stage's frappe clone authenticates through a build secret, reversing BR-BUILD-016's frappe exclusion
---

# ADR-077 — The frappe clone authenticates through a build secret

**Decided:** 2026-09-02 (Brian, after a build on the Life Scientific test VPS failed on an
anonymous `github.com` refusal).

**Amends:** `BR-BUILD-016`. **Adds:** `BR-BUILD-019`. **Relates to:** `ADR-059`, `ADR-065`, `ADR-067`, `BR-BUILD-004`,
`BR-BUILD-006`, `BR-BUILD-011`, `BR-VEND-001`.

## The incident

A `cairn-build build` on the Life Scientific test VPS (cairn `0.4.12`, manifest `erpnext-v16`)
failed in the builder stage, at `bench init`, with git's `could not read Username for
'https://github.com'` followed by `expected flush after ref listing`. No cairn change, no
manifest change, and no change to the frappe ref preceded it.

`GIT_CURL_VERBOSE=1` inside the same image showed the cause precisely. Git protocol v2 splits
`ls-remote` into two requests:

| Request | Result |
| --- | --- |
| `GET /frappe/frappe/info/refs?service=git-upload-pack` | `HTTP/2 200`, valid ref advertisement |
| `POST /frappe/frappe/git-upload-pack` | `HTTP/2 401`, `www-authenticate: Basic realm="GitHub"` |

GitHub was refusing *unauthenticated* git operations from that host's IP — a rate limit,
surfaced as a 401 on the metered POST rather than a 429. In the same minute, in the same
image, the same `ls-remote` with `$CAIRN_GITHUB_TOKEN` embedded returned the commit and
exited 0.

The failure is not about a private repository. `frappe/frappe` is public. Anonymous access is
simply not guaranteed, and a build host that builds often — or sits behind a shared or
recycled cloud IP — will spend its anonymous budget and start failing.

## The gap

`BR-BUILD-016` closes with:

> Frappe itself is out of scope: it is supplied via the `FRAPPE_PATH` build-arg
> (`BR-BUILD-004`), which is permanently readable via image history (`BR-BUILD-006`'s own
> reasoning) — a token has no safe channel to reach it, and none is attempted.

Two things are wrong with that reasoning, and the incident exposed both.

**1. It conflates the URL with the credential.** `BR-BUILD-004` requires frappe's *URL and
ref* to travel as build-args, and that is correct and should not change — provenance
(`BR-BUILD-011`) depends on those values being visible. But a credential needs no build-arg at
all. `apps.json` already demonstrates the safe channel `BR-BUILD-016` says does not exist: a
`--mount=type=secret` that lives only for the duration of one `RUN`, never enters a layer, and
never reaches image history (`BR-BUILD-006`). Nothing about that channel is specific to
`apps.json`.

**2. The exclusion is already only half-observed.** `BR-BUILD-016` requires the token in "both
places cairn talks to a `github.com` remote: ref resolution and the `apps.json` build secret."
Ref resolution *includes frappe* — `resolve.resolve_manifest()` calls the same `resolve_ref()`
→ `_ls_remote()` → `github_auth.authenticated()` path for `manifest.frappe` as for every app
(`src/cairn/resolve.py:96`). So frappe's resolution is tokenized today and has been all along.
Only the in-container clone is anonymous. The exclusion paragraph describes a boundary the code
does not actually draw.

The practical consequence: in a cairn build, `bench init`'s frappe clone is the **single**
unauthenticated `github.com` access. Every app clone carries the token via `apps.json`, and the
host-side resolution carries it in memory. That is why this one step, and only this step,
failed — and why the same rate limit was invisible everywhere else.

## Why this wasn't caught by design

The exclusion was reasoned from a threat model ("a token would leak through image history")
without a matching availability model ("anonymous access may simply be refused"). Anonymous
`github.com` access was treated as a reliable floor. It is not, and nothing in cairn's
preflight surface tests it: `doctor`'s reachability probe (`ADR-067`) resolves refs from the
*host*, with the operator's token, so it passes cleanly while the containerised clone is
failing.

## Decision

Reverse the frappe exclusion. Where a token is configured, cairn authenticates **three**
places, not two: ref resolution, the `apps.json` secret, and the builder stage's frappe clone.

The frappe clone's token reaches the builder as a second build secret, mounted for the single
`RUN` that invokes `bench init`. `FRAPPE_PATH` and `FRAPPE_BRANCH` stay exactly as they are —
plain, build-arg-borne, and recorded in provenance untouched (`BR-BUILD-016` point 3).

### Rejected alternatives

**Wait out the rate limit.** Zero change, and it works — until it recurs. It leaves every build
on a busy or shared-IP host dependent on an allowance cairn neither controls nor measures, and
turns an ordinary build into an intermittent failure with a misleading error. Rejected as a
fix; it remains the correct *immediate* unblock.

**Put a credentialed URL in `FRAPPE_PATH`.** The obvious simple thing, and the one a future
reader will ask about. It writes the token into build-args, image history, the
`com.datahenge.cairn.build-args` label, and cairn's own provenance — violating `BR-BUILD-016`
points 2 and 3 simultaneously. This is precisely the leak the original exclusion was right to
fear; the exclusion's error was concluding that no other channel existed, not that this channel
was unsafe.

**Pre-clone frappe on the build host and `COPY` it into the builder.** Uses the host's already
working authenticated path and needs no new secret. Rejected as disproportionate: it changes
`bench init`'s contract (`BR-BUILD-004`, the frappe_docker interface `ADR-059` retains), pushes
a full frappe checkout through the build context, and duplicates work the builder already does
— a large structural change to solve a credential-delivery problem.

## Consequences

- `BR-BUILD-016`'s closing paragraph is replaced; its "both places" clause becomes three.
  Proposed replacement text is quoted below for approval.
- `src/cairn/recipe/images/Containerfile` gains a second secret mount on the builder `RUN`.
  A `VEND` change to the owned recipe (`BR-VEND-001`, `ADR-059`) — freely made, no pin, no
  drift check.
- `src/cairn/build.py` passes a second `--secret` when, and only when, a token is configured.
  A public frappe on an unthrottled host MUST still build with no token at all.
- The token MUST NOT persist into any layer. It exists only under the mount for that one
  `RUN`; any git configuration referencing it must be written and removed within the same
  `RUN`, or reference a path that ceases to exist when the mount goes away.
- Provenance and `--dry-run` output are unchanged. The token must not appear in either, and
  `github_auth.redacted()` continues to cover tool output that might echo it.
- `doctor`'s `github.com` probe (`ADR-067`) remains host-side and therefore still cannot
  detect this class of failure. Whether it should is left open below.

## Proposed replacement for `BR-BUILD-016`'s closing paragraph

> Frappe is **not** exempt. Its URL and ref stay in the `FRAPPE_*` build-args
> (`BR-BUILD-004`) and stay plain — provenance depends on their being readable. Its
> *credential* does not travel that way: where a token is configured, cairn MUST supply it to
> the builder stage's frappe clone as a **build secret**, on the same terms as `apps.json`
> (`BR-BUILD-006`) — mounted for a single `RUN`, absent from every layer, absent from image
> history, absent from provenance. Anonymous `github.com` access is not a guaranteed floor:
> GitHub rate-limits unauthenticated git operations per IP and refuses them with a `401` on
> the `git-upload-pack` POST, so a public frappe on a busy or shared-IP build host fails
> exactly as a private one would (`ADR-077`).

## Settled at decision time

**The token stays optional.** With none configured the build proceeds anonymously, warning
once. Requiring one would fail every build that has no private app anywhere in its manifest —
stock public ERPNext on a lightly-used host — and would break every timer provisioned without
`/etc/cairn/<client>/github-token.env`, which `ADR-065` permits by design via
`EnvironmentFile=-`. The optionality of the token is load-bearing across `build.py`,
`github_auth.py`, and `provision.py`; this ADR does not disturb it.

**The mechanism is a `credential.helper`, not a `url.<...>.insteadOf` rewrite.** Both work.
`insteadOf` writes the literal token into a gitconfig file, which must then be deleted inside
the same `RUN` or it persists in the builder layer and therefore in the build host's local
cache. The helper writes only a *path* into gitconfig and reads the mount on demand: no secret
in any file cairn writes, nothing to clean up, and no cleanup step that a future edit can
silently drop. Neither form reaches the shipped image — the final stage copies only
`frappe-bench` — so the distinction is entirely about the builder layer and the build cache.

**Git's error message is not passed through.** `BR-BUILD-019` requires cairn to recognise an
anonymous refusal and name `$CAIRN_GITHUB_TOKEN`. Git reports this failure as `could not read
Username for 'https://github.com'`, which names a terminal prompt that was never the problem;
the incident above cost roughly an hour of diagnosis largely because of it.

**`doctor` gains nothing here.** Detecting this before a build would mean `doctor` shelling out
to a throwaway container to test egress from inside one — materially heavier than `ADR-067`
contemplated, and not what `doctor` is for. `doctor` is a host-side tool; it stays one. The
host-side probe will continue to pass while a containerised clone fails, and that is accepted.
