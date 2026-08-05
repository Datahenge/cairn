"""Read and repoint registry tags without pulling anything (BR-DEPLOY-004, BR-DEPLOY-005).

Two operations the deploy verbs are built on, and one reason this module exists at all.

* **Read** — which tags a repository holds, what digest each resolves to, and the
  provenance labels baked into the image (`BR-BUILD-011`), all over the registry API with
  **no pull** (`BR-DEPLOY-005`).
* **Repoint** — a **server-side retag**: fetch a manifest by one tag and write the identical
  bytes back under another. Deploy, promote, and rollback are all this one operation
  (`BR-DEPLOY-004`), and none of them transfers a layer, because within one repository the
  blobs the manifest references are already there.

**Why cairn speaks HTTP here rather than shelling out.** Everywhere else cairn delegates to
the container engine. It cannot here: reading a *remote* image's labels is something no
podman or buildah subcommand does, and `BR-DEPLOY-005` requires exactly that. The engines
that can (`docker buildx imagetools`, `skopeo`) are a Docker plugin and a separate binary
respectively — neither is present on a podman-only control machine, and requiring one to
read a label is a heavy dependency for a manifest fetch. The registry API is a small,
stable, versioned interface, and the whole of it cairn needs is three GETs and a PUT
(`ADR-036`).

**Credentials are still never cairn's.** cairn provisions nothing, prompts for nothing, and
persists nothing (`BR-CFG-010`). It reads the credential file the operator's `podman login`
or `docker login` already wrote, uses it for the duration of one command, and forgets it.
An unauthenticated request is tried first, so public repositories need no login at all.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import RegistryError

#: Ceiling on one registry request. Manifests are kilobytes; a slow answer is a broken one.
TIMEOUT_SECONDS = 30

#: Manifest media types cairn can read. Order is the ``Accept`` preference: a single-arch
#: manifest first, because that is what cairn builds, then the multi-arch indexes it may
#: nonetheless meet in a registry someone else also pushes to.
MANIFEST_TYPES = (
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)

INDEX_TYPES = frozenset(
    {
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
    }
)

#: Credential files cairn will *read*, most specific first. podman writes the first two,
#: docker the third; the format is shared.
CREDENTIAL_PATHS = (
    "${XDG_RUNTIME_DIR}/containers/auth.json",
    "~/.config/containers/auth.json",
    "~/.docker/config.json",
)

#: Docker Hub's API host differs from the name written in an image reference.
_DOCKER_HUB_NAMES = frozenset({"docker.io", "index.docker.io"})
_DOCKER_HUB_API = "registry-1.docker.io"


@dataclass(frozen=True)
class ImageRef:
    """A parsed image reference: where the registry is, and what to ask it about."""

    registry: str
    repository: str
    tag: str

    @property
    def api_host(self) -> str:
        """The host to send API requests to, which is not always the name in the reference."""
        return _DOCKER_HUB_API if self.registry in _DOCKER_HUB_NAMES else self.registry

    @property
    def base(self) -> str:
        """The reference without its tag — the repository as a user writes it."""
        return f"{self.registry}/{self.repository}"

    def with_tag(self, tag: str) -> ImageRef:
        return ImageRef(registry=self.registry, repository=self.repository, tag=tag)

    def __str__(self) -> str:
        return f"{self.base}:{self.tag}"


@dataclass(frozen=True)
class RemoteImage:
    """What a tag resolves to, read remotely (`BR-DEPLOY-005`)."""

    ref: ImageRef
    digest: str
    media_type: str
    size: int
    labels: dict[str, str]

    @property
    def short_digest(self) -> str:
        return self.digest.removeprefix("sha256:")[:12]


def _looks_like_host(segment: str) -> bool:
    """Whether *segment* reads as a registry host rather than a namespace.

    Docker's own heuristic: a host has a dot, a port (colon), or is literally ``localhost`` —
    anything else is the first path segment of a hostless (implicitly Docker Hub) reference.
    """
    return "." in segment or ":" in segment or segment == "localhost"


def parse_ref(reference: str) -> ImageRef:
    """Parse ``<registry>/<repository>:<tag>``, or raise :class:`RegistryError`.

    A registry host is required. cairn is registry-agnostic and MUST NOT assume Docker Hub
    (`BR-CFG-009`), so a bare ``erpnext:v16`` is an error naming the fix rather than a
    silent request to a registry the operator never chose.
    """
    remainder, _, tag = reference.rpartition(":")
    if not remainder or "/" not in remainder or "/" in tag:
        raise RegistryError(
            f"'{reference}' is not a full image reference. Write it as "
            f"<registry>/<namespace>/<name>:<tag>, e.g. "
            f"registry.example.com/acmecorp/erpnext-v16:production."
        )

    registry, _, repository = remainder.partition("/")
    if not _looks_like_host(registry):
        raise RegistryError(
            f"'{reference}' has no registry host, so cairn cannot tell where to send the "
            f"request. Prefix it with the registry, e.g. registry.example.com/{remainder}:{tag}."
        )
    return ImageRef(registry=registry, repository=repository, tag=tag)


def split_host(base: str) -> tuple[str, str]:
    """Split a tagless ``<repository>`` reference into its registry host and repository path.

    Unlike :func:`parse_ref`, a missing host is not an error here: the caller may be recording
    a fact about an image already running (`cairn-adopt examine`, `BR-CLI-020`), and a running
    container's own reference is often exactly what was written when it was pulled — a bare
    ``frappe/erpnext`` for a Docker Hub image, never ``docker.io/frappe/erpnext`` in practice.
    A missing host means Docker Hub — the same interpretation ``docker`` itself gives a hostless
    reference — made explicit as ``docker.io`` (one of the two names `_DOCKER_HUB_NAMES`
    recognizes) rather than left unstated.
    """
    first, _, rest = base.partition("/")
    if rest and _looks_like_host(first):
        return first, rest
    return "docker.io", base


def tags(ref: ImageRef) -> list[str]:
    """Return every tag in *ref*'s repository (`BR-DEPLOY-005`).

    Order is the registry's own, which the spec does not require to be meaningful — callers
    that need chronology must read it from the images, not from this list.
    """
    payload = _get_json(ref, f"/v2/{ref.repository}/tags/list", scope="pull")
    listed = payload.get("tags")
    if listed is None:
        return []
    if not isinstance(listed, list):
        raise RegistryError(f"{ref.base}: the registry's tag list was not a list.")
    return [tag for tag in listed if isinstance(tag, str)]


def inspect(ref: ImageRef) -> RemoteImage:
    """Resolve *ref* to its digest and provenance labels, without pulling (`BR-DEPLOY-005`)."""
    raw, media_type, digest = _fetch_manifest(ref)
    manifest = _decode(ref, raw)

    if media_type in INDEX_TYPES:
        child = _pick_from_index(ref, manifest)
        raw, media_type, digest = _fetch_manifest(ref, reference=child)
        manifest = _decode(ref, raw)

    config = manifest.get("config")
    if not isinstance(config, dict) or not isinstance(config.get("digest"), str):
        raise RegistryError(
            f"{ref}: the manifest names no image config, so its provenance cannot be read."
        )

    return RemoteImage(
        ref=ref,
        digest=digest,
        media_type=media_type,
        size=_manifest_size(manifest),
        labels=_labels(ref, config["digest"]),
    )


def inspect_or_none(ref: ImageRef) -> RemoteImage | None:
    """Like :func:`inspect`, but a missing image reads as ``None`` rather than a raised error.

    For a caller deciding "build or reuse" (`BR-BUILD-014a`, `ADR-052`) rather than reporting a
    hard failure — the same trade-off every other "does this tag exist yet" caller in this
    codebase already accepts: any `RegistryError` (not found, auth, network) reads as "cannot
    confirm this exists," not specifically "confirmed absent".
    """
    try:
        return inspect(ref)
    except RegistryError:
        return None


def digest_of(ref: ImageRef) -> str:
    """Return the digest *ref* currently resolves to, reading no blobs.

    The one question `reconcile` asks on every poll (`BR-DEPLOY-002`), so it deliberately
    costs a single HEAD-shaped request rather than a manifest plus a config blob.
    """
    _, _, digest = _fetch_manifest(ref)
    return digest


def delete_digest(ref: ImageRef, digest: str) -> None:
    """Delete a manifest by digest (`BR-REG-006`, `DELETE /v2/<repo>/manifests/<digest>`).

    Deletes by **digest**, never by tag name — the registry API has no operation to delete
    "one tag": deleting a manifest removes every tag currently pointing at it. This is why
    `retire` (`cli_build.py`) has always refused to delete a tag itself, and why
    `registry_retention.py`'s whole algorithm exists to prove, before ever calling this, that
    the digest carries no tag worth keeping.
    """
    _request(ref, f"/v2/{ref.repository}/manifests/{digest}", scope="pull,push", method="DELETE")


def catalog(host: str) -> list[str]:
    """Return every repository name in the registry at *host* (`GET /v2/_catalog`).

    Anonymous only. cairn's own self-hosted registry (`cairn-registry setup`) is
    unauthenticated — TLS only, no htpasswd — so this always succeeds against it. A registry
    that requires authentication for catalog access is out of scope for `cairn-registry`,
    which only ever operates on the one registry it itself provisions; a 401 here is reported
    plainly rather than attempting the repository-scoped token dance the rest of this module
    uses, since catalog access has no repository to scope a token to.
    """
    url = f"https://{host}/v2/_catalog"
    try:
        body, _ = _send(url, "GET", None, {"Accept": "application/json"})
    except urllib.error.HTTPError as exc:
        detail = _error_detail(exc) or f"{exc.code} {exc.reason}"
        raise RegistryError(
            f"{host}: the registry would not list its catalog ({detail}). "
            f"`cairn-registry` only supports an unauthenticated catalog listing."
        ) from exc
    except urllib.error.URLError as exc:
        raise RegistryError(f"Cannot reach the registry at {host} ({exc.reason}).") from exc

    payload = json.loads(body) if body else {}
    if not isinstance(payload, dict):
        raise RegistryError(f"{host}: expected a JSON object from the catalog endpoint.")
    repositories = payload.get("repositories")
    if repositories is None:
        return []
    if not isinstance(repositories, list):
        raise RegistryError(f"{host}: the catalog's 'repositories' was not a list.")
    return [name for name in repositories if isinstance(name, str)]


def retag(source: ImageRef, tag: str) -> str:
    """Point *tag* at whatever *source* resolves to, server-side (`BR-DEPLOY-004`).

    Returns the digest now under *tag*. The manifest bytes are written back **verbatim**:
    re-serializing them would change the digest and so mint a second image out of what is
    meant to be the same one. Because source and destination share a repository, every blob
    the manifest references is already present — nothing is pulled and nothing is uploaded
    but the manifest itself, which is what makes deploy, promote, and rollback the same
    cheap operation.
    """
    raw, media_type, digest = _fetch_manifest(source)
    destination = source.with_tag(tag)

    _request(
        destination,
        f"/v2/{destination.repository}/manifests/{tag}",
        scope="pull,push",
        method="PUT",
        body=raw,
        headers={"Content-Type": media_type},
    )
    return digest


# --- HTTP, and the token dance ----------------------------------------------


def _fetch_manifest(ref: ImageRef, reference: str | None = None) -> tuple[bytes, str, str]:
    """Return ``(raw bytes, media type, digest)`` for a tag or a digest in *ref*'s repository."""
    target = reference or ref.tag
    body, headers = _request(
        ref,
        f"/v2/{ref.repository}/manifests/{target}",
        scope="pull",
        headers={"Accept": ", ".join(MANIFEST_TYPES)},
    )
    media_type = headers.get("Content-Type", "").split(";")[0].strip()
    digest = headers.get("Docker-Content-Digest", "")

    if not digest:
        # Not every registry sends it; the digest is defined as the hash of these very
        # bytes, so it can always be computed rather than demanded.
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
    return body, media_type, digest


def _manifest_size(manifest: dict[str, Any]) -> int:
    """Total transfer size of the image: its config plus every layer.

    The registry reports each blob's size in the manifest, so this is the size a target would
    download — not the size the image occupies once unpacked, which is what
    `cairn images --local` reports. The two legitimately differ and are never compared.
    """
    blobs = [manifest.get("config"), *(manifest.get("layers") or [])]
    return sum(
        blob["size"]
        for blob in blobs
        if isinstance(blob, dict) and isinstance(blob.get("size"), int)
    )


def _labels(ref: ImageRef, config_digest: str) -> dict[str, str]:
    """Read the image config blob and return its labels (`BR-BUILD-011`).

    Labels live in the config, not the manifest, which is why reading provenance remotely
    costs a second request — and why no ``docker`` subcommand short of `imagetools` can do
    it.
    """
    payload = _get_json(ref, f"/v2/{ref.repository}/blobs/{config_digest}", scope="pull")
    config = payload.get("config")
    labels = config.get("Labels") if isinstance(config, dict) else None
    if not isinstance(labels, dict):
        return {}
    return {key: value for key, value in labels.items() if isinstance(value, str)}


def _pick_from_index(ref: ImageRef, index: dict[str, Any]) -> str:
    """Choose one manifest from a multi-arch index, preferring ``linux/amd64``.

    cairn builds single-arch images, so meeting an index means the repository is shared with
    something else. Picking deliberately — and saying which — beats reading whichever entry
    happens to be first.
    """
    entries = index.get("manifests")
    if not isinstance(entries, list) or not entries:
        raise RegistryError(f"{ref}: the registry returned a multi-arch index with no entries.")

    def _is_linux_amd64(entry: Any) -> bool:
        platform = entry.get("platform") if isinstance(entry, dict) else None
        if not isinstance(platform, dict):
            return False
        return platform.get("os") == "linux" and platform.get("architecture") == "amd64"

    chosen = next((e for e in entries if _is_linux_amd64(e)), entries[0])
    digest = chosen.get("digest") if isinstance(chosen, dict) else None
    if not isinstance(digest, str):
        raise RegistryError(f"{ref}: an entry in the multi-arch index carries no digest.")
    return digest


def _get_json(ref: ImageRef, path: str, *, scope: str) -> dict[str, Any]:
    body, _ = _request(ref, path, scope=scope, headers={"Accept": "application/json"})
    return _decode(ref, body)


def _decode(ref: ImageRef, body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RegistryError(
            f"{ref.base}: the registry's answer was not valid JSON — {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise RegistryError(f"{ref.base}: expected a JSON object from the registry.")
    return payload


def _request(
    ref: ImageRef,
    path: str,
    *,
    scope: str,
    method: str = "GET",
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    """Perform one registry request, authenticating only if the registry asks.

    Anonymous first, deliberately: a public repository then needs no credentials at all, and
    cairn never touches the credential file it does not need.
    """
    url = f"https://{ref.api_host}{path}"
    attempt = dict(headers or {})

    try:
        return _send(url, method, body, attempt)
    except urllib.error.HTTPError as exc:
        if exc.code != 401:
            raise _http_error(ref, method, exc) from exc
        challenge = exc.headers.get("WWW-Authenticate", "")

    token = _token(ref, challenge, scope)
    attempt["Authorization"] = f"Bearer {token}"
    try:
        return _send(url, method, body, attempt)
    except urllib.error.HTTPError as exc:
        raise _http_error(ref, method, exc) from exc


def _send(
    url: str, method: str, body: bytes | None, headers: dict[str, str]
) -> tuple[bytes, dict[str, str]]:
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return response.read(), dict(response.headers)
    except urllib.error.URLError as exc:
        if isinstance(exc, urllib.error.HTTPError):
            raise
        raise RegistryError(
            f"Cannot reach the registry at {urllib.parse.urlsplit(url).netloc} ({exc.reason}). "
            f"Check the network, and that the registry host is spelled correctly."
        ) from exc


def _token(ref: ImageRef, challenge: str, scope: str) -> str:
    """Exchange the registry's challenge for a bearer token (`BR-CFG-010`).

    The credential file is read here and nowhere else, at the last possible moment — only
    once a registry has actually demanded authentication.
    """
    parameters = _parse_challenge(challenge)
    realm = parameters.get("realm")
    if not realm:
        raise RegistryError(
            f"{ref.base}: the registry asked for authentication but named no way to obtain "
            f"it. If this registry needs a login, run `podman login {ref.registry}`."
        )

    query = {"scope": f"repository:{ref.repository}:{scope}"}
    if service := parameters.get("service"):
        query["service"] = service

    headers = {"Accept": "application/json"}
    credential = read_credential(ref.registry)
    if credential:
        headers["Authorization"] = f"Basic {credential}"

    try:
        body, _ = _send(f"{realm}?{urllib.parse.urlencode(query)}", "GET", None, headers)
    except urllib.error.HTTPError as exc:
        raise RegistryError(_token_refused(ref, exc, credential is not None)) from exc

    payload = _decode(ref, body)
    token = payload.get("token") or payload.get("access_token")
    if not isinstance(token, str):
        raise RegistryError(f"{ref.base}: the registry's token response carried no token.")
    return token


def _token_refused(ref: ImageRef, exc: urllib.error.HTTPError, had_credential: bool) -> str:
    """Explain a refused token, naming every cause rather than assuming the likeliest.

    Some registries — GHCR among them — answer a token request for a repository that is
    private, absent, *or* merely unauthenticated with the same ``403 DENIED``, deliberately, so
    that a probe cannot discover which repositories exist. A message naming only one of the
    three sends the operator to fix the wrong thing.
    """
    detail = _error_detail(exc) or f"{exc.code} {exc.reason}"
    causes = [
        f"  - the repository does not exist (check the namespace: '{ref.repository}')",
        "  - it is private and this login cannot read it",
    ]
    if not had_credential:
        causes.insert(
            0,
            f"  - you are not logged in to {ref.registry} "
            f"(cairn found no credential the container engine had stored)",
        )
    return "\n".join(
        [
            f"{ref.base}: the registry would not issue a read token ({detail}).",
            "This registry answers all of these the same way, so it may be any of:",
            *causes,
            f"If a login is needed, run `podman login {ref.registry}` — cairn never stores "
            f"registry credentials, it only reads what the engine saved.",
        ]
    )


def _parse_challenge(challenge: str) -> dict[str, str]:
    """Parse a ``WWW-Authenticate: Bearer realm="…",service="…"`` header."""
    _, _, parameters = challenge.partition(" ")
    parsed: dict[str, str] = {}
    for part in parameters.split(","):
        key, _, value = part.strip().partition("=")
        if key and value:
            parsed[key.strip()] = value.strip().strip('"')
    return parsed


def read_credential(registry: str) -> str | None:
    """Return the base64 ``user:secret`` the engine stored for *registry*, or ``None``.

    cairn reads; it never writes, prompts, or persists (`BR-CFG-010`). The operator's
    `podman login` / `docker login` is the act that provisions this, and remains the only
    one.
    """
    for candidate in CREDENTIAL_PATHS:
        path = _expand(candidate)
        if path is None:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # Absent, unreadable, or malformed are all the same answer here: this file has
            # no credential for us. Notably `OSError` covers a file that exists but cannot
            # be stat'ed — a root-owned ~/.docker/config.json is common, and it must not
            # turn every registry command into a traceback when anonymous would have worked.
            continue
        auths = payload.get("auths")
        if not isinstance(auths, dict):
            continue
        for name in _credential_keys(registry):
            entry = auths.get(name)
            if isinstance(entry, dict) and isinstance(entry.get("auth"), str):
                return entry["auth"]
            if isinstance(entry, dict) and entry.get("identitytoken"):
                # An entry with no `auth` still proves a login happened; the token flow
                # below will fail informatively rather than pretending to be anonymous.
                return _basic("<token>", str(entry["identitytoken"]))
    return None


def _credential_keys(registry: str) -> tuple[str, ...]:
    """Names a credential for *registry* may be filed under."""
    if registry in _DOCKER_HUB_NAMES:
        return ("https://index.docker.io/v1/", "index.docker.io", "docker.io")
    return (registry, f"https://{registry}")


def _basic(user: str, secret: str) -> str:
    return base64.b64encode(f"{user}:{secret}".encode()).decode("ascii")


def _expand(candidate: str) -> Path | None:
    """Expand ``${XDG_RUNTIME_DIR}`` and ``~``, returning None if the variable is unset."""
    expanded = os.path.expandvars(candidate)
    if "$" in expanded:  # an unset variable; the path cannot be meant
        return None
    return Path(expanded).expanduser()


def _http_error(ref: ImageRef, method: str, exc: urllib.error.HTTPError) -> RegistryError:
    """Turn a registry HTTP failure into a message naming the fix (`BR-CLI-015`)."""
    if exc.code == 404:
        return RegistryError(
            f"{ref} does not exist in the registry. Check the tag with `cairn images`, and "
            f"that the namespace is right."
        )
    if exc.code in (401, 403):
        verb = "push to" if method == "PUT" else "delete from" if method == "DELETE" else "read"
        needs = "read" if method == "GET" else "write"
        return RegistryError(
            f"Not permitted to {verb} {ref.base} ({exc.code} {exc.reason}). Run "
            f"`podman login {ref.registry}` with a token carrying {needs} access — cairn "
            f"never stores registry credentials."
        )
    detail = _error_detail(exc)
    return RegistryError(
        f"The registry rejected {method} {ref} ({exc.code} {exc.reason})"
        + (f": {detail}" if detail else ".")
    )


def _error_detail(exc: urllib.error.HTTPError) -> str:
    """Pull the registry's own explanation out of its error body, if it gave one."""
    try:
        payload = json.loads(exc.read())
    except (OSError, ValueError):
        return ""
    errors = payload.get("errors") if isinstance(payload, dict) else None
    if not isinstance(errors, list):
        return ""
    messages = [e.get("message") for e in errors if isinstance(e, dict) and e.get("message")]
    return "; ".join(str(message) for message in messages)
