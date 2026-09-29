---
status: authoritative
owner: technical
purpose: Durable findings about Frappe's background-job queues and how the recipe's worker services map onto them.
---

# Lessons: Frappe queues and the recipe's worker services

What turned out to be true about Frappe's background-job queues as the recipe's compose
services model them. Illuminates `BR-VEND-003` and `ADR-059`.

_Last updated: 2026-09-29._

## Frappe v16 still has three built-in queues

**Measured**, 2026-09-29, reading `frappe/utils/background_jobs.py` at `version-16`
(commit `5c16f12`, 2026-06-02).

`get_queues_timeout()` returns `short` (300s), `default` (300s), `long` (1500s), merged over
whatever the site's `common_site_config.json` declares under `workers`. Unchanged from v15 —
no queue was renamed or removed, and `enqueue()` still defaults to `default`.

The ordering of that mapping is load-bearing, not cosmetic: the source comments it, and a
worker started without an explicit `--queue` inherits the order as RQ's priority order.

## A queue is not a service — two workers cover all three

`src/cairn/recipe/compose.yaml` defines two worker services, neither named for `default`:

| Service | Command |
| --- | --- |
| `queue-short` | `bench worker --queue short,default` |
| `queue-long` | `bench worker --queue long,default,short` |

`bench worker --queue` takes a comma-separated priority list, so `default` is consumed by both
containers. There is no `queue-default` service and nothing is dropped. Upstream frappe_docker
collapsed its separate `queue-default` service into these two before cairn took ownership of the
recipe; cairn kept that shape, and no override under `src/cairn/recipe/overrides/` adds or
removes a worker.

The absent service name reads as a missing worker to anyone who knows the three queue names.
It is the first thing to rule out when a deployment "looks like it lost the default worker" —
count `bench worker` processes, not service names.

## Job timeout follows the queue, not the worker

`background_jobs.py` resolves `timeout` from `get_queues_timeout()` at **enqueue** time, keyed
on the queue the caller named. A `default` job that happens to be picked up by `queue-long`
therefore still gets 300s, not 1500s. Putting `long` in a worker's list widens what that
container will run; it does not grant the other queues a longer leash.
