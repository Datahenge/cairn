---
status: authoritative
owner: technical
purpose: ADR-027 — Build engine is pluggable (`docker` | `podman`); deploy engine stays Docker
---

# ADR-027 — Build engine is pluggable (`docker` | `podman`); deploy engine stays Docker

**Decided:** 2026-07-24
The build machine and the target are **different machines** (`ADR-018` already splits the
roles), and the artifact that crosses between them is an **OCI image in a registry** — not
a build engine. buildah produces OCI images; Docker 23+ consumes them. So the build engine
is a property of the build machine only.

**Decision:** `BUILD` may use `docker build` **or** `podman build`, auto-detected (prefer
`docker` when present, else `podman`) and overridable via `engine =` in **local build
config** (`ADR-015`, `BR-CFG-008`) — never in the portable `cairn.toml`, which must stay
free of build-machine settings. `DEPLOY` is **unchanged**: Docker + Docker Compose on the
target, per `ADR-002`. `BR-DEPLOY-005` already reads provenance over the **registry
manifest API** (HTTP), so introspection is engine-independent.

**Rationale:** the author's build machine runs rootless, daemonless podman. Installing
`dockerd` beside it puts a second engine on the host managing its own nftables chains
(`DOCKER`, `DOCKER-USER`, `DOCKER-FORWARD`) and rewriting the `FORWARD` policy — a real,
recurring cost on a machine that only *builds* and needs none of Docker's networking. The
client's TEST VPS ships Docker, and `DEPLOY` is untouched by this decision.

**Evidence (measured 2026-07-24, podman 5.4.2 / buildah 1.39.3):** the secret mount at
`Containerfile:128` works with `uid=`/`gid=` honoured (mode `0400`, owned `1000:1000`);
the secret leaks into neither the filesystem nor image history; `CACHE_BUST` keys the
layer cache in both directions. Full result in `04a-lessons-build-engines.md` §2.

**Engine floors:** Docker Engine **v23+** (BuildKit is the default builder from 23.0).
Podman **v4.0+** — the documented floor for `--mount=type=secret`; only 5.4.2 is measured,
so the floor is conservative-by-documentation rather than by test.

**Accepted risks, to confirm against a real registry:** buildah defaults to OCI manifest
format where Docker historically preferred v2s2 (`--format docker` is the fallback); and
provenance **labels** must read back identically via `docker inspect .Config.Labels`
regardless of which engine stamped them — load-bearing for `retag`/rollback. Also assumes
build-host architecture matches the target (both amd64 today).

**Amended 2026-07-25 — the engines are equivalent in *output*, not in *residue*.** This
decision rests on the artifact crossing between machines being an OCI image, which remains
true. But the two engines leave different things behind on the build machine, and one
behaviour cannot be written for both:

| | podman / buildah | docker / BuildKit |
| --- | --- | --- |
| Build cache lives as | **untagged images** in local storage | a separate cache store |
| Multi-stage `builder` stage | exists as an image (measured: 4.63 GB) | does not exist as an image |
| Naming it with `--target` | free — tags what is already there | **materializes** several GB |

So `BR-BUILD-015` (naming the cache stage so an administrator does not delete it) is
**podman-only** — not a preference but a correctness constraint: doing it under Docker would
create the very disk consumption it exists to protect. `BR-CLI-018`'s label-scoped prune is
unaffected and remains engine-neutral, because it works from cairn's own labels rather than
from anything the engine leaves behind.

The general rule this establishes: **behaviour that touches an engine's local storage must
be decided per engine; behaviour that touches the image must not.** *(BR-BUILD-015,
lessons §12)*
*(BR-CLI-007, BR-BUILD-006/011/012, BR-CFG-008/010; amends `ADR-003`)*
