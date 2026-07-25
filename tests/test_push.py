"""Tests for registry upload (BR-CLI-003, BR-CFG-009/010/011)."""

from __future__ import annotations

import pytest

from cairn import push
from cairn.config import BuildConfig, Frappe, Manifest
from cairn.errors import PushError

MANIFEST = Manifest(
    image_name="erpnext-btu-v16",
    frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
    apps=(),
)
CONFIGURED = BuildConfig(registry="ghcr.io", namespace="datahenge")


def _completed(returncode: int):
    return type("Result", (), {"returncode": returncode})()


# --- registry guard (BR-CFG-011) --------------------------------------------


def test_refuses_to_push_without_a_registry():
    """BR-CFG-011: absent a registry the image is local; never infer Docker Hub."""
    with pytest.raises(PushError, match="No registry configured"):
        push.assert_registry_configured(BuildConfig())


def test_explicit_image_base_counts_as_configured():
    """An explicit image_base is a deliberate destination, registry or not."""
    push.assert_registry_configured(BuildConfig(image_base="registry.example.com/acme/erp"))


def test_configured_registry_passes():
    push.assert_registry_configured(CONFIGURED)


# --- reference composition (BR-CFG-011) -------------------------------------


def test_reference_uses_registry_and_namespace():
    assert (
        push.reference(MANIFEST, CONFIGURED, "v16-abc123")
        == "ghcr.io/datahenge/erpnext-btu-v16:v16-abc123"
    )


@pytest.mark.parametrize(
    ("image", "expected"),
    [
        ("ghcr.io/datahenge/erp:v16", "ghcr.io"),
        ("registry.example.com:5000/acme/erp:v16", "registry.example.com:5000"),
        ("cairn/erp:v16", "<registry>"),
    ],
)
def test_registry_host_detection(image, expected):
    """A first component with a dot or colon is a host; otherwise it's a namespace."""
    assert push.registry_host(image) == expected


# --- invocation (BR-CFG-010) ------------------------------------------------


def test_push_invokes_the_engine(monkeypatch):
    captured: list[list[str]] = []

    def _run(command, **kwargs):
        captured.append(command)
        return _completed(0)

    monkeypatch.setattr(push.subprocess, "run", _run)
    push.push("ghcr.io/datahenge/erp:v16", "podman")

    assert captured == [["podman", "push", "ghcr.io/datahenge/erp:v16"]]


def test_failure_points_at_login_not_at_cairn(monkeypatch):
    """BR-CFG-010: cairn stores no credentials, so the fix is the engine's login."""
    monkeypatch.setattr(push.subprocess, "run", lambda *a, **k: _completed(1))

    with pytest.raises(PushError, match=r"podman login ghcr\.io"):
        push.push("ghcr.io/datahenge/erp:v16", "podman")


def test_missing_engine_binary_is_actionable(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("podman")

    monkeypatch.setattr(push.subprocess, "run", _raise)

    with pytest.raises(PushError, match="not found on PATH"):
        push.push("ghcr.io/datahenge/erp:v16", "podman")
