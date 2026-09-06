---
status: authoritative
owner: technical
purpose: Durable findings about github.com's treatment of unauthenticated git traffic, and how that failure presents to a build.
---

# Lessons: `github.com` and unauthenticated git

What turned out to be true about `github.com` as a remote cairn depends on. Illuminates
`BR-BUILD-016`, `BR-BUILD-019`, and `ADR-077`.

_Last updated: 2026-09-05._

## Rate limiting is keyed on the caller, not the repository

**Measured**, 2026-09-02, on a client's test VPS.

Public visibility governs *authorization*: may you read this. Rate limiting governs
*capacity*: how much will we serve you right now. They are independent, and conflating them
is what made this failure hard to read.

An unauthenticated request is attributed to the **IP address** it came from. An authenticated
one is attributed to the **account**. On a VPS the address may sit behind NAT with other
tenants, or have been recycled from a previous tenant, so the anonymous budget can be spent
by traffic the operator never generated and cannot see.

A token therefore does not grant access to a public repository. Access was never in question.
It moves the request into a different accounting bucket. This is the whole reason
`BR-BUILD-019` keeps the token optional but useful: nothing about a public build *requires*
credentials, and a busy build host still wants them.

## The refusal presents as `401`, not `429`

**Measured.** Captured with `GIT_CURL_VERBOSE=1` inside the failing image:

| Request | Response |
| --- | --- |
| `GET /frappe/frappe/info/refs?service=git-upload-pack` | `200`, valid ref advertisement |
| `POST /frappe/frappe/git-upload-pack` | `401`, `www-authenticate: Basic realm="GitHub"` |

For git-over-HTTPS, "I will not serve you anonymously" is expressed as a credential
challenge. From the server's side that is coherent. From the client's side it is
indistinguishable from "this repository is private."

Git then tries to obtain credentials, finds no terminal in a BuildKit sandbox, and reports
`could not read Username for 'https://github.com'`, followed by `expected flush after ref
listing`. Three translations away from the cause, each losing information. `BR-BUILD-019`
exists because of this chain, not because the message is merely terse.

## Protocol v2 splits the work, and only the expensive half is metered

**Measured**, and the reason the first round of diagnosis went the wrong way.

Git protocol v2 answers an `ls-remote` with a cacheable `GET` for the ref advertisement, then
a dynamic `POST` that negotiates objects. The `GET` was served from an edge PoP
(`x-github-edge-region: fra`) and returned `200`. The `POST` runs on origin infrastructure
and was refused.

A `curl` against `/info/refs` therefore returns `200` while the build is failing. That probe
was run early and read as "GitHub is fine, look at Docker networking," which cost roughly an
hour. **A reachability check that only exercises `/info/refs` proves nothing about whether a
clone will succeed.** This is also why `doctor`'s host-side probe (`ADR-067`) cannot detect
this class of failure, which `ADR-077` accepted rather than fixed.

## A credential helper authenticates on the retry, not the first request

**Reasoned** from git's documented credential flow, consistent with the observed exchange.

Git does not send credentials pre-emptively. It attempts the request anonymously, receives
the `401`, then consults the credential helper and retries. The cheap cached `GET` may still
go out anonymously. The metered `POST` is what gets retried under the account, which is the
request that was being refused.

## Why cairn meets this more often than a hand-run build

**Reasoned**, from `BR-BUILD-007`.

`CACHE_BUST` is derived from every resolved commit, so any input change forces a fresh
`bench init` rather than a cached layer. A cairn build host therefore performs full clones
of Frappe, ERPNext, and every app far more often than someone building by hand does.

## What could not be established

GitHub publishes limits for the REST API. Git-over-HTTPS is a separate bucket with no
published figures, so **no threshold in this document should be treated as known**. The
refusal was reproduced and its mechanism established; the specific allowance, and whether
this particular host tripped a rate limit as opposed to an abuse-detection block, were not.
Both present identically to the client.
