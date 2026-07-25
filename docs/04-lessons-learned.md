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
needed `DOCKER_BUILDKIT=1`. Originally inferred here; **since confirmed by the vendored
upstream** at `frappe_docker/docs/02-setup/02-build-setup.md:15` — "BuildKit is the
default builder starting with Docker Engine 23.0 — older releases will fail or silently
fall back to the legacy builder, which does not support secret mounts."

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

So `BR-BUILD-007` — "set `CACHE_BUST` from a hash of all resolved commits; a correct
build MUST NOT require `--no-cache`" — is a **compensating mechanism for two cache blind
spots**, not a performance optimization. Read as an optimization it looks droppable. It
is not: without it, correctness depends on the operator remembering `--no-cache`.

**Corroborated by upstream** at `docs/03-production/06-automated-builds-and-deployment.md`:
"This is especially relevant because `apps.json` is provided as a secret. Secret contents
are not part of Docker layer cache keys and therefore cannot trigger cache invalidation
automatically. As a result, Docker may reuse an older cached layer even when the custom
app definition has changed." Derived here from the Containerfile before that prose was
found — the agreement is reassuring rather than circular.

**One gap upstream does not close:** its recommended technique is an *apps.json* hash,
which misses Frappe. `FRAPPE_BRANCH` is a build-arg and so enters the cache key by
**name**, but a branch that *moves* keeps its name — a Frappe-only update would reuse a
stale `bench init` layer. `BR-BUILD-007` was therefore revised (2026-07-24) to hash
**all** resolved commits, Frappe included.

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

**Upstream agrees, which we only noticed later.** The vendored
`docs/02-setup/02-build-setup.md` documents `podman build` as a **first-class equivalent**
to `docker build`, with byte-identical flags (`--build-arg`, `--secret=id=apps_json,src=…`,
`--tag`, `--file`). Reading the vendored documentation before reasoning from memory would
have shortened this investigation considerably.

**Outcome (`ADR-027`, same day):** the result was adopted. The build engine is now
pluggable (`docker` | `podman`); `DEPLOY` stays Docker on the target, unchanged. What made
that cheap was noticing the build machine and the target are **different machines** whose
only interchange is an OCI image in a registry (§8) — so the "harder half" this entry
originally warned about turned out to be out of scope by construction rather than a cost
to be paid. Two risks carried forward into `ADR-027`: OCI-vs-v2s2 manifest format on push,
and label readback across engines.

## 10. The OCI spec sets the label convention; Docker's docs carry the reasoning

*Measured (both documents read, 2026-07-24). Illuminates `ADR-030`, `BR-BUILD-011`._

Looking for *why* image labels use reverse-DNS keys, the obvious source is the wrong one.
The OCI image-spec's `annotations.md` says only:

> Keys SHOULD be named using a reverse domain notation - e.g. `com.example.myKey`.
> … Consumers MUST NOT generate an error if they encounter an unknown annotation key.

**SHOULD**, not MUST; `org.opencontainers` reserved; **no rationale given**, and **nothing
at all about domain ownership**. Both of the things one actually needs to decide a
namespace live in *Docker's* label documentation:

> Authors of third-party tools should prefix each label key with the reverse DNS notation
> of a domain **they own** … Don't use a domain in your label key without the domain
> owner's permission.

with the purpose stated as preventing "inadvertent duplication of labels across objects,
especially if you plan to use labels as a mechanism for automation."

Two consequences worth keeping: a non-conforming key is *tolerated* by the spec (consumers
must not error), so bare `cairn.*` would have worked mechanically — the reason to conform
is collision safety for automation, not validation. And the ownership norm is what rules
out a namespace like `io.cairn` for anyone who does not own `cairn.io`.

Generalizable: when a standard is terse, the operative guidance often sits in a dominant
implementer's documentation rather than in the standard. Read both before concluding a
spec is silent on something.

## 9. A pattern-filtered `git ls-remote` omits the peeled ref

*Measured, 2026-07-24. Illuminates `BR-BUILD-005`, `BR-BUILD-011`._

`git ls-remote --heads --tags <url>` lists an annotated tag twice — the tag object, then
the commit it peels to:

```
78e30c5a…  refs/tags/v1.0
6247c646…  refs/tags/v1.0^{}
```

Add a **pattern** and the second line disappears:

```
$ git ls-remote --heads --tags <url> v1.0
78e30c5a…  refs/tags/v1.0            # tag object only

$ git ls-remote --heads --tags <url> v1.0 'v1.0^{}'
78e30c5a…  refs/tags/v1.0
6247c646…  refs/tags/v1.0^{}         # the commit
```

The peeled entry is a ref whose name ends in `^{}`, so it does not match the pattern
`v1.0`; it must be requested by name. Without the second pattern, resolution records the
**tag object's** SHA — an object a clone never checks out. That would have poisoned
provenance (`BR-BUILD-011`), the input hash (`BR-BUILD-008`), and `CACHE_BUST`
(`BR-BUILD-007`) for every annotated-tag pin, while looking entirely plausible: a
40-character hex SHA, in the right field, wrong object.

**Why it survived unit testing:** the stub returned both lines, because that is what an
*unfiltered* `ls-remote` returns and what the documentation examples show. The test
encoded the author's assumption rather than the command's behaviour, and passed. It was
caught by resolving against a throwaway local repository with one annotated tag, one
lightweight tag, and one branch — three lines of setup that no amount of mocking would
have substituted for.

Generalizable: when stubbing a subprocess, the stub's *output* is a second assumption
under test, and a passing test only confirms the two assumptions agree. Verify the real
command's output shape at least once, especially where a wrong value is still
well-formed.

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
