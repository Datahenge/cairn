---
status: authoritative
owner: technical
purpose: Durable findings about method and process — how this project avoids repeating known mistakes.
---

# Lessons Learned — Process Notes

Part of the [lessons-learned](04-lessons-learned.md) set. See that file for what this
document type is for and how findings are marked (**measured** vs **reasoned**).

_Last updated: 2026-08-03_

---

## 1. Derive build-input checks from the source, don't hardcode them

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

## 2. The agent's shell cannot run rootless podman

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

## 3. Two corrections worth remembering as method

*Method notes._

**An overstated claim.** "`docker buildx` has no podman equivalent" was asserted from
memory and was wrong — it conflated the front-end with the engine (see
[04a-lessons-build-engines.md](04a-lessons-build-engines.md) §1) and ignored that buildah
independently implements `--secret`, `--label`, `--cache-from/--cache-to`, `--jobs`, and
`--platform`. Checking `podman build --help` would have cost seconds. The capability of an
adjacent toolchain is a *measurable* fact; asserting it from recall produced a wrong
recommendation for a right-sounding reason.

**A test's failure is not the subject's failure.** A run initially reported one failure —
"mount not owned by 1000:1000" — while the very output it examined showed
`-r-------- 1 1000 1000`. The assertion's regex required a mode beginning `-rw`, but a
secret mount is read-only. The test encoded an assumption the subject didn't share.
Before reporting a negative result, confirm the assertion tested what it claimed to.

## 4. A convention that lives only in prose will be violated

*Measured the hard way — twice. Illuminates `/CLAUDE.md`._

`/CLAUDE.md` has always said internal docstrings cite `BR` IDs while external descriptions
omit them. It was violated twice in two days: first every Typer command leaked its `BR` ID
into `--help` (Typer renders the **docstring** as help text), then eight runtime error
messages leaked theirs through `Error: …`. Both were caught by a human reading output.

The wording was fine. The **placement and enforcement** were not:

- It sat in workflow step 6, *"User documentation"* — a phase not yet started, so while
  writing Phase-4 code it read as a future task rather than a present constraint.
- "External/API descriptions" did not obviously name the channels that actually leak:
  help text, error messages, warnings, progress output.
- It was absent from the *"For the AI (operating rules)"* section — the part that binds
  behaviour.
- Nothing checked it. Compliance depended on remembering, every time, in every string.

Fixed on all four axes, but the last is the one that matters: `tests/test_conventions.py`
now parses every non-docstring string literal in the package and fails on any `BR-`/`ADR-`
identifier. It includes a test that plants a violation and asserts the guard catches it —
a guard that cannot fail is worse than none, because it manufactures confidence.

Generalizable: **prefer conventions that can fail a test.** For a rule stated in prose,
the honest question is not "is the wording clear?" but "what would notice if I broke it?"
If the answer is "a careful reader, eventually", the rule is decorative. This one was
decorative for two days while being violated in two different channels.
