"""Tests for the registry client — remote reads and the server-side retag.

Covers `BR-DEPLOY-004` (retag with no rebuild and no pull) and `BR-DEPLOY-005` (tags,
digests, and provenance labels read remotely). No test touches the network: every one
substitutes the single transport function, which is the seam the whole module funnels
through.

Boundaries: credential *use* is tested here, credential *provisioning* is not cairn's
(`BR-CFG-010`) — the operator's `podman login` writes the file, and these tests only
verify cairn reads what is there and never writes it.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error

import pytest

from cairn import registry
from cairn.errors import RegistryError

MANIFEST = json.dumps(
    {
        "schemaVersion": 2,
        "mediaType": "application/vnd.oci.image.manifest.v1+json",
        "config": {"digest": "sha256:" + "c" * 64, "size": 4096},
        "layers": [{"size": 100_000_000}, {"size": 2_650_000_000}],
    },
    separators=(",", ":"),
).encode()

OCI_TYPE = "application/vnd.oci.image.manifest.v1+json"
INDEX_TYPE = "application/vnd.oci.image.index.v1+json"

REF = registry.ImageRef("ghcr.io", "datahenge/erpnext-btu-v16", "production")

OCI_HEADERS = {"Content-Type": OCI_TYPE}

CHALLENGE = 'Bearer realm="https://ghcr.io/token",service="ghcr.io"'


class Transport:
    """Records every request and answers from a scripted routing table."""

    def __init__(self, routes):
        self.routes = routes
        self.calls: list[dict] = []

    def __call__(self, url, method, body, headers):
        self.calls.append({"url": url, "method": method, "body": body, "headers": dict(headers)})
        for fragment, answer in self.routes.items():
            if fragment in url:
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"no route for {url}")


def _http_error(code, *, headers=None, body=b"{}"):
    return urllib.error.HTTPError(
        "https://ghcr.io/v2/x", code, "Unauthorized", headers or {}, None
    )


def _install(monkeypatch, routes):
    transport = Transport(routes)
    monkeypatch.setattr(registry, "_send", transport)
    return transport


# --- reference parsing (BR-CFG-009) -----------------------------------------


def test_a_full_reference_parses():
    ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-aaa111")

    assert ref.registry == "ghcr.io"
    assert ref.repository == "datahenge/erpnext-btu-v16"
    assert ref.tag == "v16.0.1-aaa111"
    assert str(ref) == "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-aaa111"


def test_a_reference_without_a_registry_is_refused():
    """cairn is registry-agnostic and must never infer Docker Hub."""
    with pytest.raises(RegistryError, match="no registry host"):
        registry.parse_ref("datahenge/erpnext-btu-v16:v16")


def test_a_reference_without_a_tag_is_refused():
    with pytest.raises(RegistryError, match="not a full image reference"):
        registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16")


def test_localhost_is_a_registry():
    """A local registry has no dot in its name, and is still a registry."""
    assert registry.parse_ref("localhost:5000/x/y:v1").registry == "localhost:5000"


def test_docker_hub_is_addressed_at_its_api_host():
    """The name written in a reference is not the host the API lives on."""
    assert registry.ImageRef("docker.io", "library/nginx", "latest").api_host == (
        "registry-1.docker.io"
    )
    assert REF.api_host == "ghcr.io"


# --- reading (BR-DEPLOY-005) ------------------------------------------------


def test_tags_are_listed(monkeypatch):
    _install(
        monkeypatch,
        {
            "/tags/list": (
                json.dumps({"tags": ["v16", "production", "v16.0.1-aaa111"]}).encode(),
                {},
            )
        },
    )

    assert registry.tags(REF) == ["v16", "production", "v16.0.1-aaa111"]


def test_an_empty_repository_lists_no_tags(monkeypatch):
    _install(monkeypatch, {"/tags/list": (json.dumps({"tags": None}).encode(), {})})

    assert registry.tags(REF) == []


def test_inspect_reads_the_digest_and_labels_without_pulling(monkeypatch):
    """BR-DEPLOY-005: provenance read remotely. Labels live in the config blob, which is why
    this costs a manifest fetch plus one blob fetch — and no layer is ever requested."""
    config_blob = json.dumps({"config": {"Labels": {"com.datahenge.cairn.input-hash": "aaa111"}}})
    transport = _install(
        monkeypatch,
        {
            "/manifests/": (MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:abc"}),
            "/blobs/": (config_blob.encode(), {}),
        },
    )

    image = registry.inspect(REF)

    assert image.digest == "sha256:abc"
    assert image.labels["com.datahenge.cairn.input-hash"] == "aaa111"
    assert image.size == 4096 + 100_000_000 + 2_650_000_000
    assert not any("layer" in call["url"] for call in transport.calls)


def test_the_digest_is_computed_when_the_registry_omits_it(monkeypatch):
    """The digest is defined as the hash of the manifest bytes, so it can always be derived
    rather than demanded of a registry that does not send the header."""
    _install(monkeypatch, {"/manifests/": (MANIFEST, {"Content-Type": OCI_TYPE})})

    expected = "sha256:" + hashlib.sha256(MANIFEST).hexdigest()
    assert registry.digest_of(REF) == expected


def test_a_multi_arch_index_resolves_to_linux_amd64(monkeypatch):
    """cairn builds single-arch, so an index means a shared repository. Picking deliberately
    beats reading whichever entry happens to be first."""
    index = json.dumps(
        {
            "manifests": [
                {"digest": "sha256:arm", "platform": {"os": "linux", "architecture": "arm64"}},
                {"digest": "sha256:amd", "platform": {"os": "linux", "architecture": "amd64"}},
            ]
        }
    ).encode()
    config_blob = json.dumps({"config": {"Labels": {}}}).encode()

    calls: list[str] = []

    def _transport(url, method, body, headers):
        calls.append(url)
        if "/manifests/sha256:amd" in url:
            return MANIFEST, {"Content-Type": OCI_TYPE, "Docker-Content-Digest": "sha256:amd"}
        if "/manifests/" in url:
            return index, {"Content-Type": INDEX_TYPE, "Docker-Content-Digest": "sha256:idx"}
        return config_blob, {}

    monkeypatch.setattr(registry, "_send", _transport)

    assert registry.inspect(REF).digest == "sha256:amd"
    assert any("/manifests/sha256:amd" in url for url in calls)


def test_a_manifest_without_a_config_is_reported(monkeypatch):
    _install(
        monkeypatch,
        {"/manifests/": (json.dumps({"schemaVersion": 2}).encode(), {"Content-Type": OCI_TYPE})},
    )

    with pytest.raises(RegistryError, match="names no image config"):
        registry.inspect(REF)


def test_unreadable_labels_are_reported_as_absent_not_invented(monkeypatch):
    _install(
        monkeypatch,
        {
            "/manifests/": (MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:a"}),
            "/blobs/": (json.dumps({"config": {}}).encode(), {}),
        },
    )

    assert registry.inspect(REF).labels == {}


# --- the server-side retag (BR-DEPLOY-004) ---------------------------------


def test_retag_writes_the_manifest_bytes_verbatim(monkeypatch):
    """The single most important property in this module. Re-serializing the manifest would
    change its digest and so mint a second image out of what must be the same one."""
    transport = _install(
        monkeypatch,
        {
            "/manifests/": (MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:abc"}),
        },
    )

    digest = registry.retag(REF, "staging")

    put = next(call for call in transport.calls if call["method"] == "PUT")
    assert put["body"] == MANIFEST
    assert put["headers"]["Content-Type"] == OCI_TYPE
    assert put["url"].endswith("/manifests/staging")
    assert digest == "sha256:abc"


def test_retag_uploads_no_blobs(monkeypatch):
    """Nothing is pulled and nothing is uploaded but the manifest: within one repository the
    blobs are already present, which is what makes deploy, promote and rollback equally cheap."""
    transport = _install(
        monkeypatch,
        {"/manifests/": (MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:a"})},
    )

    registry.retag(REF, "staging")

    assert [call["method"] for call in transport.calls] == ["GET", "PUT"]
    assert not any("/blobs/" in call["url"] for call in transport.calls)


def test_retag_requests_push_scope(monkeypatch):
    """A pull-scoped token cannot write a tag; asking for the wrong scope fails at the PUT
    with an authentication error that looks like a credential problem."""
    scopes: list[str] = []

    def _transport(url, method, body, headers):
        if "/token" in url:
            scopes.append(url)
            return json.dumps({"token": "t"}).encode(), {}
        if "Authorization" not in headers:
            raise _http_error(401, headers={"WWW-Authenticate": CHALLENGE})
        return MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:a"}

    monkeypatch.setattr(registry, "_send", _transport)
    registry.retag(REF, "staging")

    assert any("pull%2Cpush" in scope or "pull,push" in scope for scope in scopes)


# --- authentication (BR-CFG-010) -------------------------------------------


def test_an_anonymous_request_is_tried_first(monkeypatch):
    """A public repository must need no credentials, and cairn must not read the credential
    file it does not need."""
    read = []
    monkeypatch.setattr(registry, "read_credential", lambda name: read.append(name))
    transport = _install(monkeypatch, {"/tags/list": (json.dumps({"tags": []}).encode(), {})})

    registry.tags(REF)

    assert "Authorization" not in transport.calls[0]["headers"]
    assert read == []


def test_a_challenge_is_answered_with_a_bearer_token(monkeypatch):
    calls: list[dict] = []

    def _transport(url, method, body, headers):
        calls.append({"url": url, "headers": dict(headers)})
        if "/token" in url:
            return json.dumps({"token": "abc123"}).encode(), {}
        if "Authorization" not in headers:
            raise _http_error(
                401,
                headers={"WWW-Authenticate": CHALLENGE},
            )
        return json.dumps({"tags": ["v16"]}).encode(), {}

    monkeypatch.setattr(registry, "_send", _transport)
    monkeypatch.setattr(registry, "read_credential", lambda name: None)

    assert registry.tags(REF) == ["v16"]
    assert calls[-1]["headers"]["Authorization"] == "Bearer abc123"


def test_a_stored_credential_is_used_for_the_token_exchange(monkeypatch):
    seen: dict = {}

    def _transport(url, method, body, headers):
        if "/token" in url:
            seen["token_headers"] = dict(headers)
            return json.dumps({"token": "abc"}).encode(), {}
        if "Authorization" not in headers:
            raise _http_error(
                401, headers={"WWW-Authenticate": CHALLENGE}
            )
        return json.dumps({"tags": []}).encode(), {}

    monkeypatch.setattr(registry, "_send", _transport)
    monkeypatch.setattr(registry, "read_credential", lambda name: "dXNlcjp0b2tlbg==")

    registry.tags(REF)

    assert seen["token_headers"]["Authorization"] == "Basic dXNlcjp0b2tlbg=="


def test_a_challenge_naming_no_realm_says_how_to_log_in(monkeypatch):
    def _transport(url, method, body, headers):
        raise _http_error(401, headers={"WWW-Authenticate": "Basic"})

    monkeypatch.setattr(registry, "_send", _transport)

    with pytest.raises(RegistryError, match=re.escape("podman login ghcr.io")):
        registry.tags(REF)


def test_the_credential_file_is_read_not_written(tmp_path, monkeypatch):
    """cairn reads what `podman login` wrote and persists nothing of its own."""
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"auths": {"ghcr.io": {"auth": "c2VjcmV0"}}}), encoding="utf-8")
    monkeypatch.setattr(registry, "CREDENTIAL_PATHS", (str(auth),))

    before = auth.read_text(encoding="utf-8")
    assert registry.read_credential("ghcr.io") == "c2VjcmV0"
    assert auth.read_text(encoding="utf-8") == before


def test_a_missing_credential_file_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CREDENTIAL_PATHS", (str(tmp_path / "absent.json"),))

    assert registry.read_credential("ghcr.io") is None


def test_an_unparseable_credential_file_is_skipped(tmp_path, monkeypatch):
    """A broken file must not crash a read; the next candidate, or anonymous, still works."""
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"auths": {"ghcr.io": {"auth": "ok"}}}), encoding="utf-8")
    monkeypatch.setattr(registry, "CREDENTIAL_PATHS", (str(broken), str(good)))

    assert registry.read_credential("ghcr.io") == "ok"


def test_docker_hub_credentials_are_found_under_their_legacy_key(tmp_path, monkeypatch):
    auth = tmp_path / "config.json"
    auth.write_text(
        json.dumps({"auths": {"https://index.docker.io/v1/": {"auth": "hub"}}}), encoding="utf-8"
    )
    monkeypatch.setattr(registry, "CREDENTIAL_PATHS", (str(auth),))

    assert registry.read_credential("docker.io") == "hub"


def test_an_unset_environment_variable_is_not_a_path(monkeypatch):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)

    assert registry._expand("${XDG_RUNTIME_DIR}/containers/auth.json") is None


# --- errors that name the fix (BR-CLI-015) ---------------------------------


def test_a_missing_tag_says_so_and_suggests_how_to_look(monkeypatch):
    _install(monkeypatch, {"/manifests/": _http_error(404)})

    with pytest.raises(RegistryError, match="does not exist in the registry"):
        registry.digest_of(REF)


def test_a_refused_push_names_the_login_and_the_access_needed(monkeypatch):
    def _transport(url, method, body, headers):
        if method == "PUT":
            raise _http_error(403)
        return MANIFEST, {**OCI_HEADERS, "Docker-Content-Digest": "sha256:a"}

    monkeypatch.setattr(registry, "_send", _transport)

    with pytest.raises(RegistryError, match="write access"):
        registry.retag(REF, "production")


def test_the_registrys_own_explanation_is_surfaced(monkeypatch):
    class _Detailed(urllib.error.HTTPError):
        def read(self):
            return json.dumps({"errors": [{"message": "manifest invalid"}]}).encode()

    _install(monkeypatch, {"/manifests/": _Detailed("u", 400, "Bad Request", {}, None)})

    with pytest.raises(RegistryError, match="manifest invalid"):
        registry.digest_of(REF)


def test_an_unreachable_registry_is_reported_as_such(monkeypatch):
    def _fail(request, timeout=None):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(registry.urllib.request, "urlopen", _fail)

    with pytest.raises(RegistryError, match="Cannot reach the registry"):
        registry.digest_of(REF)


def test_a_non_json_answer_is_reported(monkeypatch):
    _install(monkeypatch, {"/tags/list": (b"<html>gateway timeout</html>", {})})

    with pytest.raises(RegistryError, match="not valid JSON"):
        registry.tags(REF)


# --- challenge parsing -----------------------------------------------------


def test_a_challenge_is_parsed_into_its_parameters():
    parsed = registry._parse_challenge(
        'Bearer realm="https://ghcr.io/token",service="ghcr.io",scope="repository:x/y:pull"'
    )

    assert parsed["realm"] == "https://ghcr.io/token"
    assert parsed["service"] == "ghcr.io"
    assert parsed["scope"] == "repository:x/y:pull"


def test_a_refused_token_names_every_possible_cause(monkeypatch):
    """GHCR answers "private", "absent", and "not logged in" identically, on purpose, so a
    message naming only one sends the operator to fix the wrong thing."""
    monkeypatch.setattr(registry, "read_credential", lambda name: None)

    def _transport(url, method, body, headers):
        if "/token" in url:
            raise _http_error(403)
        raise _http_error(401, headers={"WWW-Authenticate": CHALLENGE})

    monkeypatch.setattr(registry, "_send", _transport)

    with pytest.raises(RegistryError) as caught:
        registry.tags(REF)

    message = str(caught.value)
    assert "not logged in" in message
    assert "does not exist" in message
    assert "private" in message


def test_a_refused_token_with_a_credential_does_not_suggest_logging_in(monkeypatch):
    """Telling someone to log in when they already are is the least useful thing to say."""
    monkeypatch.setattr(registry, "read_credential", lambda name: "dXNlcjpwYXNz")

    def _transport(url, method, body, headers):
        if "/token" in url:
            raise _http_error(403)
        raise _http_error(401, headers={"WWW-Authenticate": CHALLENGE})

    monkeypatch.setattr(registry, "_send", _transport)

    with pytest.raises(RegistryError) as caught:
        registry.tags(REF)

    assert "you are not logged in" not in str(caught.value)
    assert "cannot read it" in str(caught.value)
