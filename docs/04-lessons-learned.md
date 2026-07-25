# Lessons Learned

Durable technical findings — mechanisms understood, claims measured, mistakes worth not
repeating. Distinct from the neighbouring documents by *kind*, not topic:

| Document | Answers |
| --- | --- |
| `docs/requirements/` | What the system must do (`BR-<AREA>-NNN`) |
| `01-decisions-closed.md` / `02-decisions-open.md` | What we chose, and why (`ADR-NNN`) |
| `03-discussion-log.md` | How the design conversation unfolded, chronologically |
| **this file** | What turned out to be **true** about the tools we build on |

Findings here are written to survive a change of direction: they hold whether or not the
decision that prompted them stands. Each cites the `BR`/`ADR` IDs it illuminates, and
marks whether it was **measured** or **reasoned**.

_Last updated: 2026-07-24_

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
needed `DOCKER_BUILDKIT=1`. The requirement states the floor without a rationale, so this
is inference — but it is the only reading under which the version and the feature set
line up.

## 2. The secret mount and the cache key interact in a way that *requires* `CACHE_BUST`

*Reasoned, then measured (§4). Illuminates `BR-BUILD-006`, `BR-BUILD-007`._

This is the most valuable thing learned, and it is not obvious from either requirement in
isolation. At `frappe_docker/images/custom/Containerfile:124-134`:

```dockerfile
ARG CACHE_BUST=""
RUN --mount=type=secret,id=apps_json,target=/opt/frappe/apps.json,uid=1000,gid=1000 \
  : "${CACHE_BUST}" && \
  ... bench init ${APP_INSTALL_ARGS} --frappe-branch=${FRAPPE_BRANCH} ...
```

Three facts compose into one requirement:

1. `apps.json` is mounted as a tmpfs file existing only for that one `RUN`. It never
   enters a layer — which is the point, since app URLs may carry tokens for private
   repos. A build-arg would be permanently readable via image history. Hence
   `BR-BUILD-006`'s "secret, **never** a build-arg".
2. **A secret's contents are deliberately excluded from the layer cache key.** If they
   were included, the secret would leak into cache metadata. So editing `apps.json`
   leaves the `RUN` instruction byte-identical and the cached layer is reused — you get
   an image built from your *previous* app list, silently and with no error.
3. `bench init` runs `git clone` against remote branches, which the builder cannot
   content-address either. A branch that moved is likewise invisible.

Line 129's `: "${CACHE_BUST}"` is the shell no-op `:` used solely to *reference* the ARG,
forcing its value into that instruction's cache key.

So `BR-BUILD-007` — "set `CACHE_BUST` from a hash of the resolved app commits; a correct
build MUST NOT require `--no-cache`" — is a **compensating mechanism for two cache blind
spots**, not a performance optimization. Read as an optimization it looks droppable. It
is not: without it, correctness depends on the operator remembering `--no-cache`.

## 3. The build destroys its own provenance

*Measured (read from the vendored source). Illuminates `BR-BUILD-005`, `BR-BUILD-011`._

`Containerfile:144` ends the builder stage with:

```
find apps -mindepth 1 -path "*/.git" | xargs rm -fr
```

Every app's git metadata is stripped from the image. Once the image exists, **there is no
way to recover which commits went into it by inspecting it.**

This is why `BR-BUILD-005` (resolve-and-record) and `BR-BUILD-011` (stamp resolved commits
as OCI labels) are necessary rather than merely tidy: provenance must be captured *outside*
the build, at resolve time, because the build itself deletes the evidence. Any future
proposal to "just inspect the image" for provenance is foreclosed by this line.

## 4. Buildah handles everything this Containerfile needs — measured, 2026-07-24

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

**Outcome (`ADR-027`, same day):** the result was adopted. The build engine is now
pluggable (`docker` | `podman`); `DEPLOY` stays Docker on the target, unchanged. What made
that cheap was noticing the build machine and the target are **different machines** whose
only interchange is an OCI image in a registry (§8) — so the "harder half" this entry
originally warned about turned out to be out of scope by construction rather than a cost
to be paid. Two risks carried forward into `ADR-027`: OCI-vs-v2s2 manifest format on push,
and label readback across engines.

## 8. Ask which machine runs it before asking whether the tool supports it

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

## 5. Derive build-input checks from the source, don't hardcode them

*Applied in code. Illuminates `BR-VEND-006`._

`BR-VEND-006` requires verifying the vendored tree holds "at minimum
`images/custom/Containerfile` and the `resources/` it references". The obvious
implementation — a hardcoded list of six resource paths — is wrong by construction: it
silently rots the first time the `frappe_docker` pin is bumped and upstream adds or moves
a file, and it rots *quietly*, still reporting success.

`vendor.assert_build_inputs` instead parses the Containerfile's own `COPY` instructions
and requires each build-context path to exist, skipping `COPY --from=<stage>` lines whose
sources come from an earlier build stage rather than the vendored tree. The check derives
its expectations from the artifact it is checking, so it stays correct across upgrades.

Generalizable: when a requirement says "and everything it references", parse the
referencing artifact rather than transcribing its current contents.

## 6. The agent's shell cannot run rootless podman

*Measured. Operational note for future sessions._

Every podman invocation — including `podman info` — failed with a bare `permission
denied`, while `podman --version` and `podman build --help` worked fine. Diagnosis:

```
/proc/self/uid_map  →  1000  1000  1        # only uid 1000 mapped
/usr/bin/sudo       →  -rwsr-xr-x 1 nobody nogroup
```

The agent shell runs inside a user namespace mapping a single uid. Root is unmapped, so
root-owned files read as `nobody:nogroup` and the setuid helpers `newuidmap`/`newgidmap`
cannot claim the subuid range. This is a property of the *agent's* environment, not the
workstation: `/etc/subuid` and `/etc/subgid` are correctly provisioned and podman works
normally in the user's own shell.

Resolution pattern: write the experiment as a self-contained script with machine-checkable
assertions, hand it to the user to run, and read the results back. Worth reaching for
whenever a tool needs privileges the agent shell lacks.

## 7. Two corrections worth remembering as method

*Method notes._

**An overstated claim.** "`docker buildx` has no podman equivalent" was asserted from
memory and was wrong — it conflated the front-end with the engine (§1) and ignored that
buildah independently implements `--secret`, `--label`, `--cache-from/--cache-to`,
`--jobs`, and `--platform`. Checking `podman build --help` would have cost seconds. The
capability of an adjacent toolchain is a *measurable* fact; asserting it from recall
produced a wrong recommendation for a right-sounding reason.

**A test's failure is not the subject's failure.** The §4 run initially reported one
failure — "mount not owned by 1000:1000" — while the very output it examined showed
`-r-------- 1 1000 1000`. The assertion's regex required a mode beginning `-rw`, but a
secret mount is read-only. The test encoded an assumption the subject didn't share.
Before reporting a negative result, confirm the assertion tested what it claimed to.
