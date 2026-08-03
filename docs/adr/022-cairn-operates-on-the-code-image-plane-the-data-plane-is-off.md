---
status: authoritative
owner: technical
purpose: ADR-022 — cairn operates on the code/image plane; the data plane is off-limits
---

# ADR-022 — cairn operates on the code/image plane; the data plane is off-limits

**Decided:** 2026-07-24
cairn's responsibility is **shipping code** — building immutable images (apps + commits)
and deploying them to environments. The **data plane is off-limits**: cairn MUST NOT
connect to any SQL database, MUST NOT run `bench execute` or any `frappe` library code,
and MUST NOT export, import, restore, or move SQL data between environments. **Moving a
database between environments is out of scope** — that is cofferdam's / the operator's
domain, not cairn's.

**Prime Directive:** cairn MUST NOT *directly* alter any target database, and this must be
**impossible by construction** — no code path, no SQL client, no data-manipulation
capability exists in cairn. This holds for **all** environments; Production is not
special-cased because the capability simply does not exist.

**The sanctioned exceptions** are invoking Frappe's own `bench migrate` (automatic,
`ADR-014`) and, **opt-in only**, `bench install-app` (`ADR-023`) — cairn is a *caller*,
not a mutator: "cairn doesn't alter SQL; Frappe does."

**Feature 3 corollary — volumes/configs untouched:** cairn is *aware* that persistent
Docker volumes, `site_config.json`, and `encryption_key` exist, solely so it **never
touches them**. It MUST NOT read, write, seed, provision, or migrate them; an image swap
leaves the data-plane volume entirely intact.

**Rationale:** the safest data-handling code is no data-handling code. A tool that
*cannot* touch data can't be misused, social-engineered, or bugged into touching it —
defense by architecture, not by prompt. This also sharpens cairn's identity (a build +
deploy tool) and is `ADR-019` taken to its logical end (the whole data domain is
cofferdam's/the operator's).

Requirements: `docs/requirements/04-data.md`.
