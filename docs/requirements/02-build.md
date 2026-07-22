# BR-BUILD — Image Build Requirements

_Status: living · Pass 2 (drafted) · Last updated: 2026-07-21_

Requirements for building a custom ERPNext image from a manifest, using the vendored
`frappe_docker` `custom/Containerfile`. Conventions: see `/CLAUDE.md`. Decisions cited:
`ADR-001`, `ADR-004`, `ADR-007`, `ADR-009`, `ADR-011`, `ADR-015`, `ADR-020`, `ADR-021`.

---

## Manifest & inputs

**`BR-BUILD-001`** — cairn MUST build a custom image from a standalone `cairn.toml`
declaring exactly one image (environment-agnostic — an image is Frappe + app code +
prerequisites, not an environment). *(ADR-015)*

**`BR-BUILD-002`** — The manifest MUST provide `[cairn] image_name`; a `[cairn.frappe]`
section (`url`, `ref`) driving `FRAPPE_PATH`/`FRAPPE_BRANCH`; an **ordered**
`[[cairn.apps]]` list (`name`, `url`, `ref`) for ERPNext + custom apps; and
`[cairn.build]` knobs (`python_version`, `node_version`, `install_chromium`) with an
optional passthrough for the long tail (`debian_base`, `wkhtmltopdf_*`). *(ADR-015)*

**`BR-BUILD-003`** — `[[cairn.apps]]` is **order-significant**: cairn MUST preserve
manifest order into `apps.json` (build) and into the deploy-time install sequence, and
MUST NOT reorder or resolve dependencies. This rule MUST be documented prominently in
`README.md`, and **every shipped `cairn.toml` template/example MUST carry an inline TOML
comment declaring the list ordered.** *(ADR-015)*

**`BR-BUILD-004`** — Frappe MUST be supplied via the `FRAPPE_*` build-args, never in
`apps.json`; `apps.json` MUST contain only ERPNext + custom apps. *(custom Containerfile
interface)*

## Ref resolution & immutability (Option A — resolve-and-record)

**`BR-BUILD-005`** — Refs pin by **branch or tag only**; a raw commit SHA is unsupported
(bench clones via `git clone --branch`, strips `.git`, no post-clone checkout — verified).
cairn MUST resolve every ref (Frappe + each app) to its commit at build time
(`git ls-remote`) and MUST **record** the resolved commit in provenance; it MUST NOT
attempt to freeze commits into the build. The manifest SHOULD pin to **tags** for
reproducibility, and cairn SHOULD warn when a moving branch is used. *(ADR-015; cf.
ADR-020, ADR-021)*

**`BR-BUILD-006`** — `apps.json` MUST be passed only as a BuildKit secret
(`--secret id=apps_json`), never as a build-arg. *(upstream security note)*

## Cache & tagging

**`BR-BUILD-007`** — cairn MUST set `CACHE_BUST` from a hash of the resolved app commits,
so the app layer rebuilds exactly when app pins change; a correct build MUST NOT require
`--no-cache`. *(reproducibility; upstream cache technique)*

**`BR-BUILD-008`** — cairn MUST tag the image with an **immutable primary tag** = a short
hash of all resolved inputs (Frappe + app commits + effective build args), plus a moving
convenience tag (`<image_name>-latest`). Image base defaults to `cairn/<image_name>` and
MUST be registry-agnostic (`ADR-009` deferred). *(ADR-011)*

## Build invocation & knobs

**`BR-BUILD-009`** — cairn MUST build using the vendored `images/custom/Containerfile`
with `frappe_docker/` as the build context, and MUST enforce the `VEND` preconditions
first: drift hard-stop (`BR-VEND-005`) and build-input completeness (`BR-VEND-006`).
*(ADR-004; cites VEND)*

**`BR-BUILD-010`** — cairn MUST pass the `[cairn.build]` knobs as the matching build-args
and MUST record the **effective** values (including Containerfile defaults where unset)
in provenance. *(ADR-015)*

## Provenance (the cairn marker)

**`BR-BUILD-011`** — On a successful build, cairn MUST stamp build provenance onto the
image as OCI/Docker **labels** (via `docker build --label`, no Containerfile edit),
recording: `image_name`; resolved Frappe + app commits *with* their source refs;
effective build args; both tags; the `frappe_docker` pin (from `.ventwig.lock`); the
input-hash; and a timestamp. Labels travel with the image and are the authoritative
record. cairn MAY additionally emit a sidecar marker into the **deployment working
directory** (where that deployment's `cairn.toml` lives). cairn MUST NOT write markers
into its own installation or source tree. *(ADR-011 concept)*

**`BR-BUILD-012`** — cairn MUST offer a **dry-run** that emits the resolved `apps.json`,
the exact `docker build` command, the computed tags, and the intended provenance, without
building (CI-safe). *(usability; the `cairn build` command itself is `BR-CLI`)*

## Reproducibility bar

**`BR-BUILD-013`** — cairn's guarantee is **input-deterministic** (same resolved inputs →
same declared image), explicitly *not* bit-for-bit hermetic; the Debian base image and
`apt` layer are outside cairn's control, and this limit MUST be documented. *(ADR-004,
ADR-007)*

---

## Open within BUILD (Pass 2)

- **`BR-BUILD-008` tag composition** — confirm the primary tag is a pure input-hash, or
  whether it should carry a human-legible component (e.g. `<image_name>-<frappe-short>-
  <hash>`). *Awaiting decision.*

## Cross-references

- Preconditions `BR-VEND-005` / `BR-VEND-006` are enforced here at build time.
- The `cairn build` command surface (flags, `--dry-run`, output) is specified under
  `BR-CLI`.
