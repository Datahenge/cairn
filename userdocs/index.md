# cairn

A thin, opinionated wrapper around Frappe/ERPNext's Docker build tooling, built from
cairn's own owned Docker build recipe, that makes running a custom ERPNext deployment
(Frappe + ERPNext + custom apps) on a single VPS reproducible, immutable, and low-thought.

Two pillars: **reproducible custom image builds** and a **pull-based deploy lifecycle**
(git ref → image tag → running stack, with image-only rollback). A strict data-plane
boundary keeps cairn out of your databases and volumes entirely — it ships code, not
data.

!!! note "This site is a work in progress"
    [Get Started](get-started/index.md) is verified against a real deployment as it's written,
    as is [Builder](builder/index.md). [Target](target/index.md) is partly verified — see
    [Operating the Stack](target/operating.md), which says exactly which verbs have been run
    against a live host and which have not. [Self-Hosted Registry](registry/index.md) is still
    written ahead of a live run — decide the registry question first anyway (see [Get
    Started](get-started/index.md#next-steps)), since Builder's push/automation and the target
    role both assume the registry decision is already made. [Reference](reference/index.md)
    covers the manifest, build config, and target descriptor in full, but not yet the command
    surface.

## Where to go next

- **[Get Started](get-started/index.md)** — installing cairn, for any role.
- **[Registry](registry/index.md)** — decide and, if self-hosting, provision a registry.
  Do this before Builder — see why below.
- **[Builder](builder/index.md)** — building and pushing images.
- **[Target](target/index.md)** — adopting and converging an existing deployment.
- **[Guides](guides/index.md)** — configuration and day-to-day operation.
- **[Reference](reference/index.md)** — command surface and file formats.
