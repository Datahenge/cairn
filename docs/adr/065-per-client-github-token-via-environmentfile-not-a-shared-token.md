---
status: authoritative
owner: technical
purpose: ADR-065 — the build timer authenticates private github.com apps via a per-client EnvironmentFile, not a single shared CAIRN_GITHUB_TOKEN
---

# ADR-065 — the build timer authenticates private `github.com` apps via a per-client `EnvironmentFile`, not a single shared token

**Decided:** 2026-08-05 (Brian, in two parts: first flagging that the unattended timer had no
path to a GitHub PAT at all, then — overnight — that a single shared token wouldn't have
worked anyway on a multi-client build host).
**Amends:** `BR-BUILD-016` point 4, `BR-CLI-023`. **Relates to:** `ADR-017`, `ADR-062`,
`ADR-064`.

## Two problems, discovered in sequence

**First: the timer had no token at all.** `github_auth.github_token()` reads
`CAIRN_GITHUB_TOKEN` purely from the process environment (`src/cairn/github_auth.py`),
deliberately never stored anywhere on disk (`ADR-017`: cairn is secret-agnostic, it only
references and wires secrets the operator provisions). That works when an operator runs
`cairn-build build` by hand from a shell that already exports the token — it does not work
under `setup-timer`'s generated `.service`, since a systemd unit never inherits an operator's
interactive shell environment, and nothing in `provision.build_service()` set
`Environment=`/`EnvironmentFile=`.

**Second: one token wouldn't have been enough anyway.** `BR-BUILD-016` point 4 explicitly
scoped this as "one token… per-app or per-org credentials are an explicit non-goal, deferred
until a concrete need arises." A single build host can serve more than one client
(`BR-CLI-022`, `/srv/cairn/<client>/`) — that's not a hypothetical, it's already load-bearing
architecture (`ADR-047`'s whole reason `/srv/cairn/<client>/` is namespaced by client at all).
Different clients' private repos are not guaranteed reachable by the same PAT — a single
environment-wide `CAIRN_GITHUB_TOKEN` assumes one client's credential set covers every
client's private apps, which has no reason to be true and every reason not to be (separate
clients, separate trust boundaries). The "concrete need" `BR-BUILD-016` deferred against has
arrived.

## Options weighed

1. **Redesign `github_auth.py` around a per-client env-var naming scheme** —
   `CAIRN_GITHUB_TOKEN_<CLIENT>`, with `github_token()` gaining a `client` parameter threaded
   through every caller (`resolve.py`, `build.py`). Rejected: real code churn across the
   module's whole call chain, and client-name sanitization becomes cairn's problem to get
   right — `"acme-corp"` and `"acme_corp"` both sanitizing to `CAIRN_GITHUB_TOKEN_ACME_CORP`
   is a silent collision cairn would own.
2. **A per-client `EnvironmentFile=` on the generated systemd unit** — `github_auth.py` is
   untouched; it still just reads one `CAIRN_GITHUB_TOKEN` from `os.environ`, exactly as
   before. The "per-client" dispatch happens entirely at the systemd/OS level: each
   generated `.service` is already 1:1 with one manifest and therefore one client
   (`ADR-062`), so it only ever needs to load *one* client's token — which file gets loaded
   is the only thing that varies. **Chosen.**

## Decision

`provision.build_service()` adds one line:

```
EnvironmentFile=-/etc/cairn/<client>/github-token.env
```

The leading `-` makes it optional — a client with no private apps needs no file there, and
the unit still starts. `client` is the same value `build_unit_name()` already derives from
the manifest's canonical `/srv/cairn/<client>/` home (`ADR-062`), so this can never disagree
with which client the unit actually builds for.

**Cairn never creates or writes this file.** Same rule as every other secret `ADR-017`
covers: the operator creates `/etc/cairn/<client>/github-token.env` themselves, mode `0600`,
root-owned, containing one line, `CAIRN_GITHUB_TOKEN=<token>`, only if that client has a
private app. `setup-timer`'s printed output names the expected path so the operator isn't
left to guess it, mirroring how it already reports every other host-specific value it
assumed (`BR-CLI-019`'s existing pattern for the reconcile timer).

**A manual (non-timer) build is unaffected.** An operator running `cairn-build build
--manifest .../acme/cairn_prod.toml` by hand still just exports `CAIRN_GITHUB_TOKEN`
themselves before running it, exactly as today — nothing about the interactive path changes.

**`github_auth.py`'s "one token" model stays exactly as it was**, and correctly so: within a
single build, one token still covers every private app that one manifest references
(`BR-BUILD-016` point 4's "not per-app/per-org" half is unchanged and still the right call).
What's corrected is the assumption that *host-wide* meant *client-wide* — it doesn't, and the
fix lives entirely outside `github_auth.py`.

## Consequences

- `provision.build_service()` gains the `EnvironmentFile=-` line; `stage_timers_build`'s
  warnings gain a line naming the expected path.
- `BR-BUILD-016` point 4 and `BR-CLI-023` (`docs/requirements/`) rewritten to describe the
  corrected model.
- `github_auth.py`, `resolve.py`, `build.py` — **no changes**. This is the whole point: the
  fix is systemd wiring, not a token-resolution redesign.
- `open/OPEN_QUESTIONS.md`'s `OQ-002` resolved.

*(BR-BUILD-016, BR-CLI-022, BR-CLI-023, ADR-017, ADR-047, ADR-062)*
