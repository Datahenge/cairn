---
status: authoritative
owner: technical
purpose: Durable findings about BuildKit, buildx, and buildah — the engines cairn's build step drives.
---

# Lessons Learned — Build Engines

Part of the [lessons-learned](04-lessons-learned.md) set. See that file for what this
document type is for and how findings are marked (**measured** vs **reasoned**).

_Last updated: 2026-08-03_

---

## 1. BuildKit, buildx, and buildah are three different things

*Reasoned, from documentation. Illuminates `BR-CLI-007`, `ADR-003`._

Conflating these produces bad requirements. The accurate split:

| Layer | Docker | Podman |
| --- | --- | --- |
| Front-end CLI | `docker` + the **buildx** plugin | `podman` |
| Build **engine** | **BuildKit** | **buildah** |
| Builder instances / drivers | buildx's job | not applicable — daemonless |
| Registry cache format | BuildKit cache manifests | intermediate cache images |

**BuildKit** is the engine that executes a build: it compiles the Containerfile into a
graph of operations, runs independent branches in parallel, content-addresses results, and
supplies the mount types (`cache`, `secret`, `ssh`, `bind`) the original builder had no
concept of. **buildx** is only the CLI front-end that drives it. **buildah** is a third,
independent implementation from the CRI-O lineage — not a BuildKit port — that converged
on the same Containerfile syntax from a different direction.

Practical consequence: the engines are separate programs with incompatible cache formats
and different parallelism defaults (BuildKit parallelizes the graph; buildah is sequential
unless given `--jobs N`). They agree on *syntax*. So "can toolchain X build our file?" is
a question about syntax support, not architecture.

**Why `BR-CLI-007` says v23+:** Docker Engine 23.0 is where `docker build` stopped being
the legacy builder and became a front for buildx/BuildKit by default; before that it
needed `DOCKER_BUILDKIT=1`. Originally inferred here; **since confirmed by the vendored
upstream** at `frappe_docker/docs/02-setup/02-build-setup.md:15` — "BuildKit is the
default builder starting with Docker Engine 23.0 — older releases will fail or silently
fall back to the legacy builder, which does not support secret mounts."

## 2. Buildah handles everything this Containerfile needs — measured, 2026-07-24

*Measured. Illuminates `BR-BUILD-006`, `BR-BUILD-007`; scopes a possible podman ADR._

Prompted by this workstation having podman and no Docker. Test: busybox image, `USER` at
uid 1000, `/opt/frappe` deliberately not pre-created, mount options copied verbatim from
`Containerfile:128`. Environment: **podman 5.4.2, buildah 1.39.3, Debian 13**.

| Question | Result |
| --- | --- |
| Secret mounted, non-empty, readable as uid 1000? | **Yes** — mode `0400`, owned `1000:1000`; `uid=`/`gid=` options honoured |
| Secret absent from the final image? | **Yes** — token in neither the filesystem nor `podman history --no-trunc` |
| `CACHE_BUST` unchanged → cache reused? | **Yes** |
| `CACHE_BUST` changed → layer re-executed? | **Yes** |

Read-only `0400` is correct, not a limitation: `bench init` only reads the file.

**Scope of this result.** It settles the **build** side only. `DEPLOY` — `ADR-017`'s
compose `.env` and Docker secrets, and the systemd pull-loop in `BR-DEPLOY-*` — was never
tested against podman and does not need to be; see below.

**Upstream agrees, which we only noticed later.** The vendored
`docs/02-setup/02-build-setup.md` documents `podman build` as a **first-class equivalent**
to `docker build`, with byte-identical flags (`--build-arg`, `--secret=id=apps_json,src=…`,
`--tag`, `--file`). Reading the vendored documentation before reasoning from memory would
have shortened this investigation considerably.

**Outcome (`ADR-027`, same day):** the result was adopted. The build engine is now
pluggable (`docker` | `podman`); `DEPLOY` stays Docker on the target, unchanged. What made
that cheap was noticing the build machine and the target are **different machines** whose
only interchange is an OCI image in a registry (see below) — so the "harder half" this
entry originally warned about turned out to be out of scope by construction rather than a
cost to be paid. Two risks carried forward into `ADR-027`: OCI-vs-v2s2 manifest format on
push, and label readback across engines.

## 3. Ask which machine runs it before asking whether the tool supports it

*Reasoned. Illuminates `ADR-018`, `ADR-027`._

The podman question looked expensive for most of a session because it was framed as "can
cairn run on podman?" — which invites auditing every area, `DEPLOY` included. The useful
frame was "**which machine** runs each part, and what actually crosses between them?"

`ADR-018` had already answered the first half: build/control on the laptop, `reconcile` on
targets. The second half is that the only thing crossing the boundary is an **OCI image in
a registry** — a format both engines speak — plus the **registry manifest API**, which is
HTTP and speaks to neither. Once that was explicit, the engine question collapsed from
"rewrite `DEPLOY`" to "six lines across four documents", and `BR-DEPLOY-005`'s remote
provenance read turned out to need no change at all.

Generalizable: for a tool spanning multiple machines, a compatibility question is bounded
by the **interchange format**, not by the tool inventory of either end. Establish the
boundary artifact first; it usually shrinks the question by an order of magnitude.
