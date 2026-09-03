---
status: authoritative
owner: requirements
purpose: BR-BUILD requirements — building a custom ERPNext image from a manifest.
---

# BR-BUILD — Image Build Requirements

_Status: **approved** 2026-07-21 (living — may be revised via CHANGELOG) · Last updated: 2026-08-05_

Requirements for building a custom ERPNext image from a manifest, using cairn's own owned
`custom/Containerfile` recipe. Conventions: see `/CLAUDE.md`. Decisions cited:
`ADR-004`, `ADR-009`, `ADR-011`, `ADR-015`, `ADR-052`, `ADR-059`, `ADR-061`.

---

## Manifest & inputs

**`BR-BUILD-001`** — cairn MUST build a custom image from a standalone `cairn.toml`
declaring exactly one, environment-agnostic image. *(ADR-015)*

**`BR-BUILD-002`** — The manifest MUST provide `[cairn] image_name`; a `[cairn.frappe]`
section (`url`, `ref`) driving `FRAPPE_PATH`/`FRAPPE_BRANCH`; an **ordered** `[[cairn.apps]]`
list (`name`, `url`, `ref`) for ERPNext + custom apps; and `[cairn.build]` knobs
(`python_version`, `node_version`, `install_chromium`) with an optional passthrough for the
long tail (`debian_base`, `wkhtmltopdf_*`). It MAY provide an optional `[cairn] environment`
string — the manifest's single declared environment (`BR-DEPLOY-009`, `ADR-052`), which no
build reads or writes by default (see `BR-CLI-002a` for the opt-in `--assign-tag` flag) — and
an optional `[cairn] series` naming the legible half of the image tag (`BR-BUILD-008`,
`ADR-032`). A manifest declares **at most one** environment; there is no table, no list, and
no cross-manifest reference — `ADR-052`. *(ADR-015, ADR-032, ADR-052)*

**`BR-BUILD-003`** — `[[cairn.apps]]` is **order-significant**: cairn MUST preserve manifest
order into `apps.json` and into the deploy-time install sequence, and MUST NOT reorder or
resolve dependencies. This rule MUST be documented in `README.md`, and every shipped
`cairn.toml` template/example MUST carry an inline comment declaring the list ordered.
*(ADR-015)*

**`BR-BUILD-004`** — Frappe MUST be supplied via the `FRAPPE_*` build-args, never in
`apps.json`; `apps.json` MUST contain only ERPNext + custom apps. *(frappe_docker interface)*

## Ref resolution (Option A — resolve-and-record)

**`BR-BUILD-005`** — Refs pin by **branch or tag only** (raw commit SHA unsupported). cairn
MUST resolve every ref (Frappe + each app) to its commit at build time and record it in
provenance; it MUST NOT freeze commits into the build. The manifest SHOULD pin to tags;
cairn SHOULD warn when a moving branch is used — deliberately, not merely tolerated: it lets
a manifest auto-track a target's latest release, at the cost of reproducibility (`ADR-015`
has the tradeoff). *(ADR-015)*

**`BR-BUILD-006`** — `apps.json` MUST be passed only as a **build secret**
(`--secret id=apps_json`), never as a build-arg. *(ADR-015, ADR-027)*

## Build invocation

**`BR-BUILD-009`** — cairn MUST build using its own owned `images/Containerfile` with
`src/cairn/recipe/` as the build context, and MUST enforce the `VEND` precondition first:
`BR-VEND-003` (build-input completeness). *(ADR-004)*

**`BR-BUILD-010`** — cairn MUST pass the `[cairn.build]` knobs as the matching build-args and
MUST record the effective values (including Containerfile defaults where unset) in
provenance. *(ADR-015)*

**`BR-BUILD-015`** *(name the build-cache stage)* — On **podman**, after a build that
actually ran, cairn SHOULD tag the recipe's Containerfile's `builder` stage
`cairn-cache/<image_name>:builder` (podman stores this as `localhost/…`). `--no-cache-tag`
disables it.

An untagged image invites deletion. The `builder` stage is untagged, **larger** than the
final image (measured: 4.63 GB against 2.75 GB), and is what lets a rebuild skip
`bench init` — so an administrator running `podman image list`, seeing `<none>`, and
reaching for `prune` converts every later build into a cold one, with no error to explain
it. A tag is a pointer: naming it changes no digest, creates no image, and costs no disk
(measured at 0.762s, every step a cache hit).

Constraints, each load-bearing:
- **podman only.** Docker keeps build cache in a separate store rather than as images, so
  there is no stage to name and `--target` would make BuildKit **materialize** several GB
  that otherwise never exist. See the `ADR-027` amendment.
- **Only after a build that ran** — never after a `BR-BUILD-014` short-circuit, and never as
  a standalone verb. The pass is cheap *only* against a warm cache; if the stage has since
  been pruned, the identical command is a full `bench init`. Confining it to the moment
  after a real build is what guarantees the stage exists.
- **The tagging pass MUST NOT pass `--no-cache`**, even when the build did. It exists to
  name what that build just produced.
- **Best-effort.** A failure MUST NOT fail the build; the image is already built and
  verified. It is reported, not raised.
- The tag **moves** with each build, like `latest`. Superseded stages revert to untagged and
  are then genuinely collectable — which is correct, and is why cairn does not tag per input
  hash: that would identify them but pin every one of them forever. *(lessons §12, ADR-027,
  ADR-032, BR-CLI-018)*

## Provenance

**`BR-BUILD-011`** — On a successful build, cairn MUST stamp provenance onto the image as OCI
labels (via the build engine's `--label`, `ADR-027`), recording: `image_name`; resolved Frappe + app commits
with their source refs; effective build args; both tags; the owned recipe's own provenance
(cairn's package version and the git commit covering `src/cairn/recipe/` at
build time — there is no separate upstream pin to record, `ADR-059`); the input-hash; and a
timestamp. cairn MAY emit a sidecar marker into the deployment working directory, and MUST NOT
write markers into its own installation or source tree. The concrete label schema is
`ADR-030`. *(ADR-011, ADR-030, ADR-059)*

**`BR-BUILD-012`** — cairn MUST offer a `--dry-run` that emits the resolved `apps.json`, the
exact build command, the computed tags, and the intended provenance, without
building. *(BR-CLI)*

## Reproducibility bar

**`BR-BUILD-013`** — cairn's guarantee is **input-deterministic** (same resolved inputs →
same declared image), not bit-for-bit hermetic; this limit MUST be documented. *(ADR-004,
ADR-059)*

## Private `github.com` apps

**`BR-BUILD-016`** *(one token, `github.com` only)* — cairn MAY authenticate a manifest app's
`github.com` URL with an operator-provided token, read from `$CAIRN_GITHUB_TOKEN`. Not a
`BUILD_CONFIG_KEYS` entry — no `builder.toml` counterpart, by design: that file is shared and
group-writable (`BR-DEPLOY-022`), the wrong place for a secret; rule 4's "cairn stores no
secrets" applies here as to every other credential (`BR-DEPLOY-011`, `ADR-017`).

Where a token is configured, cairn MUST use it for all three places it talks to a `github.com`
remote: ref resolution (`git ls-remote`, `BR-BUILD-005`), the `apps.json` build secret
(`BR-BUILD-006`), and the builder stage's frappe clone (`ADR-077`). Five things are
load-bearing:

1. **Scoped to `github.com` exactly.** Injected only when a URL's host is exactly `github.com`
   over `http`/`https` — never any other host, never an SSH form (`git@github.com:...`,
   `ssh://…`), which needs a live handshake, not Basic-auth. Sending the token to an
   unrelated host would leak it there.
2. **The manifest never carries it.** `cairn.toml` app URLs stay plain and portable
   (`BR-BUILD-001`); the token is layered on only at the git invocation itself — in memory
   for `ls-remote`, inside the ephemeral, owner-only `apps.json` secret file for the build —
   never written back into anything persistent.
3. **Provenance stays plain.** Resolved-ref URLs on the image (`BR-BUILD-011`), `--dry-run`
   output (`BR-BUILD-012`), and every error message MUST show the untouched URL. Where a
   tool's own output might quote a credentialed URL back (e.g. git's error text on a failed
   `ls-remote`), cairn MUST redact the token first.
4. **One token per build, not one token per host.** One `$CAIRN_GITHUB_TOKEN` covers every
   private app in a single build; per-app/per-org credentials stay a non-goal. A build host
   MAY serve several clients (`BR-CLI-022`) whose tokens MUST NOT be assumed interchangeable;
   `github_auth.py` is unchanged — *which* value it sees per client is external
   (`BR-CLI-023`'s `EnvironmentFile=`, or the operator's shell), never multiplexed in code
   (`ADR-065`).
5. **A missing token is named as a candidate.** When `ls-remote` fails against a `github.com`
   URL with no token configured, cairn's error MUST point at `$CAIRN_GITHUB_TOKEN` as a
   possible fix, alongside git's own failure line — git's own wording (e.g. "could not read
   Username") names the symptom, not the missing token.

Frappe is **not** exempt. Its URL and ref stay plain in the `FRAPPE_*` build-args
(`BR-BUILD-004`); its *credential* does not travel that way. Where a token is configured,
cairn MUST supply it to the builder stage's frappe clone as a **build secret**, on the same
terms as `apps.json` (`BR-BUILD-006`). Anonymous `github.com` access is not a guaranteed
floor, so a public frappe fails exactly as a private one would. *(ADR-077)*

**`BR-BUILD-019`** *(anonymous refusal is named)* — a token stays optional: with none
configured cairn MUST still build, warning once that the clone runs unauthenticated. When a
build fails because `github.com` refused an unauthenticated operation, cairn MUST name
`$CAIRN_GITHUB_TOKEN`; git's own wording (`could not read Username`) names a terminal prompt
that was never the problem. *(ADR-077)*
*(BR-BUILD-001, BR-BUILD-004, BR-BUILD-005, BR-BUILD-006, BR-BUILD-011, BR-DEPLOY-011,
BR-DEPLOY-022, ADR-017, ADR-067, ADR-077)*

---

## Cross-references
- Cache-busting, the tag scheme, input-hash reuse, and the ownership marker:
  [`02a-build-tagging.md`](02a-build-tagging.md) (`BR-BUILD-007`, `008`, `014`, `014a`, `018`).
- Precondition `BR-VEND-003` is enforced here.
- The `cairn-build build` command surface is specified under `BR-CLI`.
