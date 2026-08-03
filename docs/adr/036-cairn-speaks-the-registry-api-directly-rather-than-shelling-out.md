---
status: authoritative
owner: technical
purpose: ADR-036 — cairn speaks the registry API directly, rather than shelling out
---

# ADR-036 — cairn speaks the registry API directly, rather than shelling out

**Decided:** 2026-07-25 · **Decided during implementation — flagged for review**
Everywhere else cairn delegates to the container engine, so the registry work was expected to
as well. It cannot, and the reason is measurable rather than aesthetic.

**`BR-DEPLOY-005` requires reading an image's provenance labels *remotely, without pulling*.**
Checking what is actually available on the control machine (2026-07-25): `podman` 5.4.2 and
`buildah` 1.39.3 are present; `docker`, `docker buildx`, `skopeo`, `crane`, and `regctl` are
all absent. **No podman or buildah subcommand reads a remote image's labels.** The two tools
that can are a Docker plugin (`docker buildx imagetools`) and a separate binary (`skopeo`) —
so satisfying the requirement by shelling out would mean adding a hard binary dependency that
this machine does not have, in order to perform one manifest fetch and one blob fetch.

**Decision:** a small stdlib client (`urllib`) implementing exactly what cairn needs — three
GETs and a PUT. No third-party HTTP library, no new binary on the host.

**Credentials remain the engine's** (`BR-CFG-010`, `BR-DEPLOY-012`). cairn provisions nothing,
prompts for nothing, and persists nothing. It *reads* the credential file `podman login` or
`docker login` already wrote, uses it for one command, and forgets it. An unauthenticated
request is tried first, so a public repository needs no login and the credential file is not
even opened. This is delegation of *provisioning*, which is what the requirement protects;
performing the transport was never the engine's exclusive claim — cairn already resolves refs
with `git ls-remote` rather than asking an engine to do it.

**The retag is genuinely server-side** (`BR-DEPLOY-004`). Within one repository the blobs a
manifest references already exist, so pointing a new tag at an existing image is a single
manifest write: one GET, one PUT, no layer transferred in either direction. The manifest bytes
are written back **verbatim** — re-serializing them would change the digest and so mint a
second image out of what must be the same one. That property is the most important line in the
module and is pinned by a test that fails if the bytes are touched.

**What this costs.** cairn now owns a little HTTP: bearer-token negotiation from a
`WWW-Authenticate` challenge, and the media-type `Accept` set. Both are stable, versioned
parts of the OCI distribution spec. The alternative — requiring `skopeo` — remains available
behind the same module boundary if the maintenance ever proves unwelcome.

**One defect this surfaced immediately**, worth recording because it was found by a test
rather than in production: a root-owned `~/.docker/config.json` (present on this very machine)
made `Path.is_file()` raise `PermissionError`, which would have turned *every* registry command
into a traceback where anonymous access would have worked. Absent, unreadable, and malformed
are now all the same answer — this file has no credential for us.
*(BR-DEPLOY-004, BR-DEPLOY-005, BR-CFG-009, BR-CFG-010, BR-DEPLOY-012, ADR-027)*
