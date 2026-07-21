# docker-cairn

A thin, opinionated wrapper around [`frappe/frappe_docker`](https://github.com/frappe/frappe_docker)
that makes running a custom ERPNext deployment (Frappe + ERPNext + custom apps) on a
single VPS **reproducible, immutable, and low-thought** — without ever modifying
upstream.

Three pillars: **reproducible custom image builds**, **CI/CD + deploy lifecycle**
(git ref → image tag → running stack), and **backup / restore / rollback** of the
database.

> _Cairn: a trail marker of stacked stones. Each deploy drops a durable marker
> (ref → image tag → DB snapshot) you can navigate back to._

## Status

Early design. No code yet — scaffolding and decisions are being recorded first.

## Design docs

| Doc | Contents |
| --- | --- |
| [docs/00-project-scope.md](docs/00-project-scope.md) | Purpose, pillars, what it is/isn't, principles |
| [docs/01-decisions-closed.md](docs/01-decisions-closed.md) | Settled decisions (`D-001`…) with rationale |
| [docs/02-decisions-open.md](docs/02-decisions-open.md) | Unresolved questions + current leans |
| [docs/03-discussion-log.md](docs/03-discussion-log.md) | Chronological design reasoning |

## Vendored upstream

`frappe_docker/` is a pinned, read-only copy of upstream (currently a plain clone;
to be managed via [`ventwig`](https://github.com/brian-pond/ventwig)). It is never
edited by hand — see `D-001` / `D-007`.
