---
status: active
owner: project
purpose: Unresolved discovery and validation questions that need the user's answer before requirements can be finalized.
---

# Open Questions

Do not infer answers to these from general knowledge or unstated preference. Ask Brian.

## Status Values

| Status | Meaning |
| --- | --- |
| `open` | Question is unanswered. |
| `resolved` | Answered; the answer has been moved into the relevant requirement document. |

## Queue

| ID | Status | Question | Context | Answer |
|---|---|---|---|---|
| `OQ-003` | `resolved` | `ADR-065` gave the build timer a path to a per-client GitHub PAT (`/etc/cairn/<client>/github-token.env`), but nothing detects whether that path is actually populated when a manifest needs it. Should `cairn-build doctor` and/or `setup-timer` check this proactively, and if so, how — given cairn has no static way to know an app is "private" without a live network round-trip? | Raised 2026-08-06 by Brian: neither `doctor`'s check set nor `setup-timer`'s unconditional warning text actually verify reachability; the timer would fail unattended, diagnosably (`BR-BUILD-016` point 5's error already names the missing token) but not proactively. | `ADR-067`: both reuse `resolve.resolve_manifest()` — `doctor` with the invoking shell's own `$CAIRN_GITHUB_TOKEN` (mirroring a manual build), `setup-timer` with only what the eventual `EnvironmentFile=` would supply (simulating the unit, not the operator's shell). `doctor` FAILs on an unresolved ref; `setup-timer` refuses to write or enable anything until it resolves. |
| `OQ-002` | `resolved` | How does an unattended `cairn-build-<client>-<image_name>-<environment>.service`, run by the build timer (`BR-CLI-023`), authenticate a `git ls-remote`/clone against a private `github.com` app when the manifest declares one (`BR-BUILD-016`)? Expanded same day: a build host can serve more than one client, and a single shared `CAIRN_GITHUB_TOKEN` can't be assumed to cover every client's private repos. | Raised 2026-08-05 by Brian, reviewing the timer's generated unit after `ADR-062`/`ADR-064`; expanded by Brian overnight once he realized `BR-BUILD-016`'s "one token" model predates the multi-client builder. `github_auth.github_token()` reads `CAIRN_GITHUB_TOKEN` purely from the process environment (`ADR-017`), which a systemd unit never inherits. | `ADR-065`: `github_auth.py` unchanged — still one token, one process. `provision.build_service()` adds `EnvironmentFile=-/etc/cairn/<client>/github-token.env`, one per client, referenced only by that client's own generated unit; optional (`-`), never written by cairn. A manual build is unaffected — the operator still exports the token themselves. |
| `OQ-001` | `resolved` | On a VPS colocating build, registry, and target roles, what does "cairn's images" mean for `cairn-build images --local` — provenance (any image carrying cairn's `BR-BUILD-011` labels, wherever built) or origin (only images this host's build role produced)? | Raised 2026-08-05: a single-VPS three-role host showed `docker image ls` mixing a `cairn-adopt`-pulled deploy image (tagged `...:test`, pulled by `reconcile`'s `docker pull`, `reconcile.py:183`) alongside locally built images. Both carry `com.datahenge.cairn.*` labels since labels are baked into image content at build time and travel with a pull. `images.py`'s `inspect_local` currently filters purely on label presence (`image.input_hash` truthy), so it reports the pulled deploy image too — correct under a provenance reading, surprising under an origin reading. Registry blob storage itself is already segregated (bind-mounted, served by `registry:2`, `registry_provision.py`); the ambiguity is only about the container engine's single shared local image store when multiple cairn roles run on one host. | Both, distinguished explicitly rather than picked between (`BR-BUILD-018`, `ADR-061`, 2026-08-05). Every build applies a `cairn-build-owned` marker tag, stripped once pushed; `--local` now reports it per image, so "still owned" answers *origin* (built here, shared nowhere) and its absence answers *provenance* (built by cairn somewhere — pushed, or `cairn-adopt` pulled it, since a pull is only ever possible after a push). |

Unresolved architectural questions that already have a recorded lean live in
`docs/open/OPEN_DECISIONS.md` instead — this file is for questions that don't yet have one.

Resolved questions should move their answer into the relevant requirement document and be
noted in `docs/CHANGELOG.md`, then marked `resolved` here (or removed if no longer useful to
retain).
