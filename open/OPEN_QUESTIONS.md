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
| `OQ-001` | `resolved` | On a VPS colocating build, registry, and target roles, what does "cairn's images" mean for `cairn-build images --local` — provenance (any image carrying cairn's `BR-BUILD-011` labels, wherever built) or origin (only images this host's build role produced)? | Raised 2026-08-05: a single-VPS three-role host showed `docker image ls` mixing a `cairn-adopt`-pulled deploy image (tagged `...:test`, pulled by `reconcile`'s `docker pull`, `reconcile.py:183`) alongside locally built images. Both carry `com.datahenge.cairn.*` labels since labels are baked into image content at build time and travel with a pull. `images.py`'s `inspect_local` currently filters purely on label presence (`image.input_hash` truthy), so it reports the pulled deploy image too — correct under a provenance reading, surprising under an origin reading. Registry blob storage itself is already segregated (bind-mounted, served by `registry:2`, `registry_provision.py`); the ambiguity is only about the container engine's single shared local image store when multiple cairn roles run on one host. | Both, distinguished explicitly rather than picked between (`BR-BUILD-018`, `ADR-061`, 2026-08-05). Every build applies a `cairn-build-owned` marker tag, stripped once pushed; `--local` now reports it per image, so "still owned" answers *origin* (built here, shared nowhere) and its absence answers *provenance* (built by cairn somewhere — pushed, or `cairn-adopt` pulled it, since a pull is only ever possible after a push). |

Unresolved architectural questions that already have a recorded lean live in
`open/OPEN_DECISIONS.md` instead — this file is for questions that don't yet have one.

Resolved questions should move their answer into the relevant requirement document and be
noted in `docs/CHANGELOG.md`, then marked `resolved` here (or removed if no longer useful to
retain).
