---
status: authoritative
owner: technical
purpose: ADR-058 — the target descriptor's registry_host is required; docker.io names Docker Hub
---

# ADR-058 — `registry_host` is required; `"docker.io"` names Docker Hub

**Decided:** 2026-08-04
**Supersedes:** `ADR-057` (the same day, hours earlier), which made `registry_host` optional.

**Problem.** `ADR-057` reasoned that requiring `registry_host` would force a fabricated value
onto a descriptor describing a Docker-Hub-hosted image, since Docker Hub has no host name of its
own in a bare reference (`frappe/erpnext`). Brian asked the natural follow-up: is there actually
a value that means "Docker Hub" — and if there is, that reasoning doesn't hold.

**There is.** `registry.py` already recognized this, unrelated to this decision:
`_DOCKER_HUB_NAMES = frozenset({"docker.io", "index.docker.io"})` — `docker.io` is the
canonical, modern name, and precisely what `docker` itself normalizes a hostless reference to
internally (`docker pull nginx` and `docker pull docker.io/library/nginx` are the same pull).
Nothing about it is invented; it was already load-bearing in this codebase's own registry client,
just never surfaced as something an operator would write.

**Decision:** `Descriptor.registry_host` changes from `str | None = None` to `str` — required,
same as `image`/`tag`/`site`. `registry.split_host()`'s hostless fallback changes from `return
None, base` to `return "docker.io", base`: a running container's own reference with no host is
recorded as `"docker.io"`, not left unstated. `examine`'s `render()` prints `registry_host`
unconditionally rather than only when present.

**Why this is better than `ADR-057`'s optional design, not just different.** Optionality existed
to avoid a false choice — asserting a host where none was truly known. That concern doesn't
survive contact with the fact that Docker Hub *has* a truly-known name. Making the field required
now means a descriptor is never silently incomplete about which registry it watches, for any
image, without giving up the "never fabricate a fact" principle `ADR-057` was protecting in the
first place — `docker.io` is exactly as much a fact as `ghcr.io` is when the reference names it.

**Consequences.** Not backward compatible in the strict sense — a descriptor missing
`registry_host` now fails to load, where `ADR-057`'s version accepted it. No live client has
installed a descriptor yet (`docs/open/OPEN_WORK.md`), so nothing is actually broken by this; it is
still a clean schema addition, not a migration of installed state.

**Scope.** `src/cairn/descriptor.py`, `src/cairn/registry.py` (`split_host`), `src/cairn/adopt.py`
(`descriptor_for`'s validation, `render`). Same `BR-DEPLOY-010`/`BR-DEPLOY-010a` scope as
`ADR-057` — field-level shape lives in `userdocs/reference/target-descriptor.md`, not in `BR`
wording.
