# Guides

This section will cover day-to-day configuration and operation.

- **[Docker Storage on a Multi-Volume Host](docker-storage-layout.md)** — Docker Engine and
  containerd have two independent storage settings; relocating only one is a common way to fill
  a small root disk anyway. Read this before your first `docker pull` on any host with more
  than one volume.

For the manifest, build config, and where each setting lives, see
[Reference](../reference/index.md). For choosing and operating a registry, see
[Registry](../registry/index.md), starting with [Choosing a container
registry](../registry/choosing-a-registry.md).
