# cairn

A thin, opinionated wrapper around [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker)
that makes running a custom ERPNext deployment (Frappe + ERPNext + custom apps) on a
single VPS reproducible, immutable, and low-thought — without ever modifying upstream.

Two pillars: **reproducible custom image builds** and a **pull-based deploy lifecycle**
(git ref → image tag → running stack, with image-only rollback). A strict data-plane
boundary keeps cairn out of your databases and volumes entirely — it ships code, not
data.

!!! note "This site is a work in progress"
    The full guides are still being written here. In the meantime, the most complete
    documentation lives in the repository itself:

    - [README](https://github.com/Datahenge/cairn/blob/main/README.md) — overview,
      installation, and the two roles cairn runs in
    - [Configuration](https://github.com/Datahenge/cairn/blob/main/CONFIGURATION.md)
    - [About container registries](https://github.com/Datahenge/cairn/blob/main/ABOUT_REGISTRIES.md)
    - [About GHCR](https://github.com/Datahenge/cairn/blob/main/ABOUT_GHCR.md)

## Where to go next

- **[Get Started](get-started/index.md)** — installing cairn and standing up your first
  deployment.
- **[Guides](guides/index.md)** — configuration and day-to-day operation.
- **[Reference](reference/index.md)** — command surface and file formats.
