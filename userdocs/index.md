# cairn

A thin, opinionated wrapper around [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker)
that makes running a custom ERPNext deployment (Frappe + ERPNext + custom apps) on a
single VPS reproducible, immutable, and low-thought — without ever modifying upstream.

Two pillars: **reproducible custom image builds** and a **pull-based deploy lifecycle**
(git ref → image tag → running stack, with image-only rollback). A strict data-plane
boundary keeps cairn out of your databases and volumes entirely — it ships code, not
data.

!!! note "This site is a work in progress"
    [Get Started](get-started/index.md) is verified against a real deployment as it's written,
    as is [Builder](builder/index.md). [Registry](registry/index.md) is written ahead of a
    live run against a real registry host — decide that first anyway (see [Get
    Started](get-started/index.md#next-steps)), since Builder's push/automation and the
    target role both assume the registry decision is already made. [Reference](reference/index.md)
    now covers the manifest, build config, and target descriptor in full. Guides and the
    target-role guide are still placeholders — in the meantime, the most complete
    documentation for those topics lives in the repository itself:

    - [About container registries](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md)
    - [About GHCR](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_GHCR.md)

## Where to go next

- **[Get Started](get-started/index.md)** — installing cairn, for any role.
- **[Registry](registry/index.md)** — decide and, if self-hosting, provision a registry.
  Do this before Builder — see why below.
- **[Builder](builder/index.md)** — building and pushing images.
- **[Guides](guides/index.md)** — configuration and day-to-day operation.
- **[Reference](reference/index.md)** — command surface and file formats.
