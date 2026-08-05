---
status: authoritative
owner: technical
purpose: ADR-030 — Provenance label schema: `com.datahenge.cairn.*` + standard OCI keys
---

# ADR-030 — Provenance label schema: `com.datahenge.cairn.*` + standard OCI keys

**Decided:** 2026-07-24
`BR-BUILD-011` says *what* provenance to stamp but not under which keys. The keys are an
interface, not a detail: `BR-DEPLOY-005` reads them remotely, and `retag`/rollback depend
on them. Renaming them after images are published means older images become unreadable to
`cairn images`, so this is settled before the first push.

**What the sources actually say.** The OCI image-spec is terse: keys **SHOULD** use
reverse domain notation, `org.opencontainers` is reserved, "Consumers MUST NOT generate an
error if they encounter an unknown annotation key" — and it gives **no rationale** and
**no ownership rule**. Both of those live in Docker's label documentation instead:
"Authors of third-party tools should prefix each label key with the reverse DNS notation
of a domain **they own**"; "**Don't use a domain in your label key without the domain
owner's permission**"; the purpose being to "prevent inadvertent duplication of labels
across objects, especially if you plan to use labels as a mechanism for automation."

**Decision:** cairn-specific keys use **`com.datahenge.cairn.*`** — the only reverse-DNS
namespace the author is entitled to use. `io.cairn` / `dev.cairn` were **rejected**: they
are real domains owned by others, which the ownership norm forbids. Bare `cairn.*` was
considered — it claims nothing and the spec tolerates it — but forfeits exactly the
collision protection the convention exists for, and cairn *does* key behavior off these
labels.

**The business name is not branding here.** Toolchain provenance labels are routine: an
image built through podman already carries `io.buildah.version` (Buildah owns
`buildah.io`). cairn deliberately does **not** set `org.opencontainers.image.vendor` — the
distributing entity of a client's image is the client's to declare, not cairn's.

**Schema.** Standard keys where one already fits; cairn's namespace for the rest:

| Key | Value |
| --- | --- |
| `org.opencontainers.image.created` | RFC 3339 build timestamp |
| `org.opencontainers.image.title` | manifest `image_name` |
| `org.opencontainers.image.version` | the immutable primary tag |
| `org.opencontainers.image.revision` | resolved Frappe commit |
| `com.datahenge.cairn.version` | the cairn that built it |
| `com.datahenge.cairn.input-hash` | `BR-BUILD-008` input hash |
| `com.datahenge.cairn.tag.primary` / `.tag.moving` | both applied tags |
| `com.datahenge.cairn.frappe.url` / `.ref` / `.commit` | Frappe source, declared ref, resolved commit |
| `com.datahenge.cairn.apps` | JSON array of `{name, url, ref, commit}`, **manifest order** |
| `com.datahenge.cairn.build-args` | JSON object of **effective** build args (`BR-BUILD-010`) |
| `com.datahenge.cairn.frappe-docker.ref` / `.commit` | the owned recipe's own provenance — cairn's package version and the git commit covering `src/cairn/recipe/frappe_docker/` at build time; there is no separate upstream pin (`ADR-059`) |

Apps and build args are single JSON labels because their cardinality varies; everything
else is scalar so it can be read without parsing.

**Rejected: a per-deployment namespace** (`com.microsoft.cairn.*` for a client Microsoft,
`shop.foobarbaz.cairn.*` for foobarbaz.shop). Attractive, because it keeps the builder's
name off a client's image — but it breaks on the fact that **cairn reads these labels, it
does not merely write them**:

- A configurable prefix must be known to the *reader*. `cairn images` reads provenance
  remotely (`BR-DEPLOY-005`) and `reconcile` runs on a target that has an environment
  descriptor, **not** the build manifest — so the target cannot know which prefix its own
  images used.
- The bootstrap does not close: discovering a configured namespace from the image requires
  a **fixed** key to look it up under. Configurability therefore buys an alias, never an
  escape from having one fixed namespace.
- A typo is silent. `com.microsft.cairn.apps` is a perfectly valid label; nothing
  validates it, and the failure surfaces much later as absent provenance — at rollback,
  which is the worst moment to discover it.
- It misattributes the schema. A namespace says *who defines these keys' meaning*, not who
  owns the image. Microsoft does not define `.input-hash`; cairn does.

The legitimate need underneath — recording **whose** image this is — is what the standard
OCI fields exist for: `org.opencontainers.image.vendor`, `.title`, `.url`. If a client
engagement ever calls for it, the answer is to make *those* settable per deployment, never
to make cairn's own key namespace variable. Not built now (no such need yet); recorded so
the option is not re-litigated from scratch.

Note the blast radius is narrower than it first appears: a wrong namespace does not make
an image or container **incompatible** — the image builds, pushes, pulls, and runs
normally. What breaks is cairn's own introspection, promotion, and rollback.
*(BR-BUILD-008/010/011, BR-DEPLOY-005)*
