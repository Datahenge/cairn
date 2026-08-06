---
status: authoritative
owner: technical
purpose: Durable findings about Docker Engine, containerd, and host disk layout, from a live client-VPS disk-space incident.
---

# Lessons Learned — Docker & Host Storage

Part of the [lessons-learned](04-lessons-learned.md) set. See that file for what this
document type is for and how findings are marked (**measured** vs **reasoned**).

_Last updated: 2026-08-06_

---

## 1. Docker Engine's `data-root` and containerd's `root` are independent — redirecting one does not redirect the other

*Measured, on a live client VPS.*

A host provisioned with a small root volume and a large secondary volume mounted at
`/var/lib/docker` looks fully relocated. It isn't. Docker Engine's storage location
(`data-root` in `/etc/docker/daemon.json`) and containerd's storage location (`root` in
`/etc/containerd/config.toml`) are two separate settings read by two separate daemons.
On a host with the **containerd image store** feature active — `driver-type:
io.containerd.snapshotter.v1` in `docker info` — containerd, not Docker's own graphdriver,
holds the actual unpacked image/container layer bytes. If containerd's `root` was never
explicitly set, it silently defaults to `/var/lib/containerd`, on whatever filesystem
holds ordinary `/var/lib` — commonly the small one, regardless of what `data-root` points
at.

The client's own `/etc/containerd/config.toml` had never been touched beyond
`disabled_plugins = ["cri"]` — the stock Debian/Ubuntu `containerd.io` package default —
confirming the containerd side of this was never considered when the host was
provisioned.

Generalizable: before trusting that "Docker's storage" has been relocated on any host,
check `docker info` for `driver-type: io.containerd.snapshotter.v1`. If present, most of
what actually grows isn't where `data-root` says it is.

## 2. Settle a disk-usage hypothesis with filesystem evidence, not size/timestamp pattern-matching

*Measured — a plausible-looking theory was wrong.*

Two directories (`/var/lib/docker/rootfs` and containerd's own
`io.containerd.snapshotter.v1.overlayfs`) were both exactly 18G, both created at the exact
same timestamp, and both named `overlayfs` one level in. That pattern was convincing
enough to propose as the likely explanation: a bind mount, with `du` counting the same
underlying blocks twice.

`stat -f` on both paths disproved it outright — different filesystem IDs, different total
block counts, each matching a *different* physical volume. Sizes matching by coincidence,
not duplication. Digging further (`ls` on each directory) revealed the real mechanism: one
held per-running-container mount points (directory names were exact matches to live
container IDs), the other held containerd's own numbered snapshot store — two genuinely
separate, both legitimately-sized datasets, not one thing double-counted.

Generalizable: a coincidence convincing enough to state as the likely answer is still a
hypothesis. `stat -f`, `findmnt`, and a raw `ls` comparison are cheap enough to run before
committing to an explanation — and worth running even when the pattern feels obvious,
because this one wasn't what it looked like.

## 3. Nesting one service's data inside another service's managed directory couples their blast radius

*Reasoned, applied (and avoided) twice in one session.*

The original mistake: the client relocated `cairn-registry`'s `data_dir` to a directory
created inside `/var/lib/docker`. Beyond the immediate permission wall this hit (Docker
locks that tree down against non-root traversal by design), it would have meant a future
"wipe and reinitialize Docker's data" operation could destroy the registry's data as
collateral — `rm -rf /var/lib/docker` has no way to know a sibling service is living
inside it.

The same reasoning was applied deliberately the second time: when consolidating
containerd and `cairn-registry` onto one shared volume, that volume was mounted at a
**neutral** path (`/data`) rather than nested inside `/var/lib/docker` specifically — so
none of the three services (`docker`, `containerd`, `cairn-registry`) sits inside another's
own territory, even though they now share one filesystem.

This mirrors a principle this project's own `ADR-053`/`ADR-060` already apply to
`/etc/cairn` vs. `/opt/cairn-registry`, generalized to host-level Docker tooling:
**shared space between peers is fine; nesting inside one peer's own managed tree is not.**

## 4. Shell glob expansion happens in the invoking shell, before `sudo` ever runs

*Measured.*

`sudo du -sh /var/lib/docker/*` produced total silence — no output, no error — on a
directory the invoking user couldn't list. `sudo` only elevates the command it's given;
`/var/lib/docker/*` is expanded by the *current, unprivileged* shell before `sudo` starts,
and since that shell couldn't list the directory, the glob matched nothing and bash passed
the literal, unexpanded `*` through. `du` then failed on a path that doesn't exist, and a
`2>/dev/null` tacked on for unrelated reasons quietly swallowed that error too.

Generalizable: `sudo <cmd> <restricted-dir>/*` doesn't elevate the glob. Wrap the whole
pipeline (`sudo bash -c '...'`) so expansion itself happens as root. And treat a
suspiciously silent result under `2>/dev/null` as reason to drop the redirect and look
again, not as confirmation of nothing found.

## 5. `mount <path>` with one argument trusts `/etc/fstab` silently — verify the device explicitly for a one-time interactive migration

*Method note.*

A migration script rewrote an existing `/etc/fstab` line's mount-point column via `sed`,
then remounted with `sudo mount /data` — a single argument, which tells `mount` to look
itself up in `/etc/fstab` and use whatever device that line names. Functionally correct,
but it gave no visibility into *which* device was actually about to be mounted, and its
correctness depended entirely on the `sed` having matched the intended line — unverifiable
by inspection of the command itself.

Safer for a live, hard-to-undo, remote-hands operation: capture the device explicitly
before touching anything (`findmnt -n -o SOURCE /var/lib/docker`), echo it for a human to
confirm looks right, and mount that captured device by name rather than trusting an
implicit fstab lookup. Still update `/etc/fstab` for boot persistence — just don't make
*this* mount's correctness depend on it.

## 6. When per-service storage isolation costs more than the risk it prevents, collapsing to one shared volume is a legitimate choice — not corner-cutting

*Reasoned.*

The textbook answer to "three services, three storage needs" is three separately-sized
volumes, each isolating the others from a runaway neighbor. That answer assumes the cost
of managing three volumes is low relative to the risk being isolated against. On a single
low-stakes test VPS, reachable only through a remote client's tech team on a 24–48 hour
communication cycle, with no other tenant depending on isolation between these three
specific peers, that assumption doesn't hold: the operational overhead of three volumes
was the actual dominant cost, not the small risk of one peer crowding another on a box with
plenty of headroom.

The choice made — one shared volume, three sibling directories under a neutral parent
(finding 3) — keeps the one property worth keeping (no service nested inside another's
own wipe-able tree) and drops the one that wasn't earning its cost on this box (independent
capacity ceilings per service). Worth re-deciding explicitly, not defaulting to, on a
host where the stakes or the communication cost are different.
