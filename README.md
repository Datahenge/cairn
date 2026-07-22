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

## Deployment manifest (`cairn.toml`) — design in progress

An image is declared by a standalone `cairn.toml` (one file = one image; an image is
**not** an environment — it's Frappe + app code + prerequisites). It names the Frappe
branch, an **ordered list** of apps (ERPNext + custom apps), and version knobs.

> ⚠️ **`[[cairn.apps]]` is an ORDERED LIST.** The order is significant: it is the app
> **install order** (App A before App B before App C). List every app *after* the apps
> it depends on. cairn does not reorder or resolve dependencies for you. Every shipped
> `cairn.toml` template/example repeats this warning inline.

Schema and rules: see `docs/requirements/02-build.md` (in progress) and the
[Phase-1 build plan](docs/plans/phase-1-build.md).

## Design docs

| Doc | Contents |
| --- | --- |
| [docs/00-project-scope.md](docs/00-project-scope.md) | Purpose, pillars, what it is/isn't, principles |
| [docs/01-decisions-closed.md](docs/01-decisions-closed.md) | Settled decisions (`ADR-001`…) with rationale |
| [docs/02-decisions-open.md](docs/02-decisions-open.md) | Unresolved questions + current leans |
| [docs/03-discussion-log.md](docs/03-discussion-log.md) | Chronological design reasoning |

## Vendored upstream

`frappe_docker/` is a pinned, read-only copy of upstream, vendored as plain committed
files via [`ventwig`](https://github.com/brian-pond/ventwig) and never edited by hand
(`ADR-001` / `ADR-007`). It is pinned to upstream release tag **`v3.2.1`**; the exact
synced commit + content-tree hash are recorded in `.ventwig.lock`.

```
.venv/bin/ventwig status   # verify the vendored tree is clean / unmodified
.venv/bin/ventwig sync      # re-materialize from the pinned ref
```

To upgrade upstream: bump `ref` in `pyproject.toml`, `ventwig sync`, review the diff,
test-build, then commit.
