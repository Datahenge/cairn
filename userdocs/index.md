# cairn

A thin, opinionated wrapper around [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker)
that makes running a custom ERPNext deployment (Frappe + ERPNext + custom apps) on a
single VPS reproducible, immutable, and low-thought — without ever modifying upstream.

Two pillars: **reproducible custom image builds** and a **pull-based deploy lifecycle**
(git ref → image tag → running stack, with image-only rollback). A strict data-plane
boundary keeps cairn out of your databases and volumes entirely — it ships code, not
data.

!!! note "This site is a work in progress"
    [Get Started](get-started/index.md) and [Builder](builder/index.md) are verified against
    a real deployment as they're written. Guides, Reference, and the target-role guide are
    still placeholders — in the meantime, the most complete documentation for those topics
    lives in the repository itself:

    - [Configuration](https://github.com/Datahenge/cairn/blob/main/docs/technical/CONFIGURATION.md)
    - [About container registries](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_REGISTRIES.md)
    - [About GHCR](https://github.com/Datahenge/cairn/blob/main/docs/technical/ABOUT_GHCR.md)

## Where to go next

- **[Get Started](get-started/index.md)** — installing cairn, for either role.
- **[Builder](builder/index.md)** — building and pushing images.
- **[Guides](guides/index.md)** — configuration and day-to-day operation.
- **[Reference](reference/index.md)** — command surface and file formats.
