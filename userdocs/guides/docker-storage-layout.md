# Docker Storage on a Multi-Volume Host

If `/` is small and a second volume holds Docker's data, redirecting *Docker's* storage there
is not enough. Docker Engine and containerd are two independent daemons with two independent
storage settings, and the one actually holding your image layers is easy to miss — right up
until the small volume fills.

## Two daemons, two storage locations

- **Docker Engine (`dockerd`)** — `data-root` in `/etc/docker/daemon.json`, default
  `/var/lib/docker`.
- **containerd** — `root` in `/etc/containerd/config.toml`, default `/var/lib/containerd`.
  This setting is **entirely independent of `data-root`.** Redirecting one does nothing to the
  other.

On a Docker install with the **containerd image store** enabled — check for `driver-type:
io.containerd.snapshotter.v1` in `docker info` — Docker delegates image and container layer
storage to containerd's own content store and snapshotter, rather than managing it itself.
That's the layer that actually grows large, and it lives under containerd's `root`, not
Docker's `data-root`.

**The trap:** a host provisioned with a big secondary volume mounted at `/var/lib/docker` looks
fully relocated. It isn't. If containerd's `root` was never explicitly set, it silently
defaults to `/var/lib/containerd` — on whatever filesystem holds ordinary `/var/lib`, commonly
your small root volume — and grows there instead, unnoticed until root disk pressure shows up.

## How to check what's actually using the space

```bash
sudo apt install ncdu   # if not already present
sudo ncdu /var/lib
```

If `containerd` shows up large next to (or instead of) `docker`, work through this:

**1. Is containerd's `root` actually configured?**

```bash
sudo cat /etc/containerd/config.toml
```

On Debian/Ubuntu Docker installs, this file commonly ships with almost nothing in it —
`disabled_plugins = ["cri"]` and no explicit `root` line — meaning containerd is quietly using
its compiled-in default rather than anything intentionally set.

**2. Is this containerd instance actually backing your Docker containers**, not some unrelated
workload (Kubernetes, `nerdctl`, a stray install)?

```bash
systemctl status containerd --no-pager | grep -i namespace
```

Docker always runs its containers under the `moby` namespace. `-namespace moby` on every shim
process confirms it's Docker; anything else (`k8s.io`, for example) means something other than
Docker is also using this containerd instance, and needs its own accounting before you touch
anything.

**3. Confirm from Docker's own side:**

```bash
sudo docker info | grep -i -A2 'containerd\|driver-type'
```

## Moving containerd's storage

This requires stopping Docker and every running container for the duration — plan a
maintenance window, not a mid-day fix.

**Give containerd its own volume, rather than nesting it inside `/var/lib/docker`.** Nesting it
there works, but it quietly couples containerd's data to Docker's data-root's own blast
radius — a future "wipe and reinitialize Docker's data" runbook that does `rm -rf
/var/lib/docker` would take containerd's content store down with it as collateral damage, the
same risk this trap already caused once. If your volume group has room (`vgs`), a dedicated
logical volume avoids that:

```bash
# 1. Create and format a dedicated volume — adjust size and VG name to your host
sudo lvcreate -L 50G -n cairn-containerd vg0
sudo mkfs.ext4 /dev/vg0/cairn-containerd

# 2. Mount it where containerd will look for its data
sudo mkdir -p /var/lib/containerd-new
UUID=$(sudo blkid -s UUID -o value /dev/vg0/cairn-containerd)
echo "UUID=$UUID /var/lib/containerd-new ext4 defaults 0 2" | sudo tee -a /etc/fstab
sudo mount /var/lib/containerd-new

# 3. Point containerd at it
echo 'root = "/var/lib/containerd-new"' | sudo tee -a /etc/containerd/config.toml

# 4. Stop both daemons — Docker depends on containerd, stop it first
sudo systemctl stop docker
sudo systemctl stop containerd

# 5. Copy the existing data across
sudo rsync -aHAX /var/lib/containerd/ /var/lib/containerd-new/

# 6. Restart, containerd first
sudo systemctl start containerd
sudo systemctl start docker

# 7. Verify before deleting anything
sudo docker ps
sudo ncdu /var/lib
```

Once containers are confirmed healthy and `/var/lib/containerd` (the old path) has stopped
growing, keep it around briefly as a rollback, then remove it:

```bash
sudo mv /var/lib/containerd /var/lib/containerd.bak
# after a few days of confidence:
sudo rm -rf /var/lib/containerd.bak
```

If there's no free space left to allocate a new volume, nesting containerd's `root` under your
existing `/var/lib/docker` volume (e.g. `/var/lib/docker/containerd`) is the fallback — same
`rsync` procedure, just pointed at a subdirectory of the volume you already have, with the
blast-radius caveat above accepted rather than avoided.

## Before you provision, not after

Setting this up correctly from the start avoids the stop/rsync/verify dance entirely:

- Set **both** `data-root` (`/etc/docker/daemon.json`) and containerd's `root`
  (`/etc/containerd/config.toml`) to their final locations *before* the first `docker pull` or
  `docker run` on a new host — not just `data-root`.
- Re-check after any Docker upgrade. Whether the containerd image store is enabled, and by what
  default, has changed across Docker Engine versions — a host that previously stored everything
  under `data-root` can start filling `/var/lib/containerd` again after an otherwise routine
  `apt upgrade`, with nothing in your own configuration having changed.
- A periodic `ncdu /var/lib` (or `du -sh /var/lib/*`) is the cheap early warning that catches
  this drift before it becomes a full root disk.

## Next

- **[Self-Hosted Registry](../registry/index.md)** — the same "which directory actually holds
  the bytes" question applies to `cairn-registry`'s own `data_dir`; see its `setup`/`doctor`
  output for the equivalent check on that role.
