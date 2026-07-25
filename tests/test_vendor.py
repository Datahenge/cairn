"""Tests for the vendored-tree drift and integrity checks (BR-VEND-005, BR-VEND-007)."""

from __future__ import annotations

import subprocess
import types

import pytest

from cairn import vendor
from cairn.errors import VendorDriftError, VendorToolError
from cairn.project import VendorSource


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_assert_clean_passes_when_ventwig_exits_zero(monkeypatch, tmp_path):
    """BR-VEND-005: a clean tree (ventwig exit 0) does not raise."""
    monkeypatch.setattr(vendor, "_run", lambda *a, **k: _completed(0))

    vendor.assert_clean(tmp_path)  # must not raise


def test_assert_clean_raises_on_drift(monkeypatch, tmp_path):
    """BR-VEND-005: drift (ventwig exit 1) is a hard stop, surfacing ventwig's detail."""
    monkeypatch.setattr(
        vendor, "_run", lambda *a, **k: _completed(1, stdout="frappe_docker drifted")
    )

    with pytest.raises(VendorDriftError, match="drifted"):
        vendor.assert_clean(tmp_path)


def test_assert_no_nested_git_raises_when_present(monkeypatch, tmp_path):
    """BR-VEND-007: a nested .git in a vendored source is rejected."""
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("frappe_docker", "frappe_docker")]
    )
    (tmp_path / "frappe_docker" / ".git").mkdir(parents=True)

    with pytest.raises(VendorDriftError, match=r"nested \.git"):
        vendor.assert_no_nested_git(tmp_path)


def test_assert_no_nested_git_passes_when_absent(monkeypatch, tmp_path):
    """BR-VEND-007: a plain vendored tree (no nested .git) passes."""
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("frappe_docker", "frappe_docker")]
    )
    (tmp_path / "frappe_docker").mkdir()

    vendor.assert_no_nested_git(tmp_path)  # must not raise


def test_require_ventwig_missing(monkeypatch):
    """A missing ventwig yields an actionable VendorToolError, not a confusing failure."""
    monkeypatch.setattr(vendor.importlib.util, "find_spec", lambda name: None)

    with pytest.raises(VendorToolError, match="pip install ventwig"):
        vendor._require_ventwig()


def test_args_helper():
    assert vendor._args("status", None) == ["status"]
    assert vendor._args("sync", "frappe_docker") == ["sync", "frappe_docker"]
