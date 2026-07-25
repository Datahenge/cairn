"""Tests for the vendored-tree drift and integrity checks (BR-VEND-005/006/007)."""

from __future__ import annotations

import subprocess
import types

import pytest

from cairn import vendor
from cairn.errors import VendorDriftError, VendorInputsMissingError, VendorToolError
from cairn.project import VendorSource

CONTAINERFILE = """\
FROM base AS builder
COPY resources/core/nginx/nginx-template.conf /templates/nginx/frappe.conf.template
COPY --from=builder --chown=frappe:frappe /home/frappe/frappe-bench /home/frappe/frappe-bench
COPY resources/core/start.sh /usr/local/bin/start.sh
RUN echo not-a-copy
"""


def _vendored_tree(tmp_path, containerfile: str = CONTAINERFILE) -> None:
    """Materialize a minimal vendored frappe_docker tree under *tmp_path*."""
    source_root = tmp_path / "frappe_docker"
    custom = source_root / vendor.CUSTOM_CONTAINERFILE
    custom.parent.mkdir(parents=True)
    custom.write_text(containerfile, encoding="utf-8")
    for name in ("resources/core/nginx/nginx-template.conf", "resources/core/start.sh"):
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


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


def test_assert_build_inputs_passes_when_complete(monkeypatch, tmp_path):
    """BR-VEND-006: a tree holding the Containerfile and every file it copies passes."""
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("frappe_docker", "frappe_docker")]
    )
    _vendored_tree(tmp_path)

    vendor.assert_build_inputs(tmp_path)  # must not raise


def test_assert_build_inputs_raises_when_containerfile_absent(monkeypatch, tmp_path):
    """BR-VEND-006: a missing custom Containerfile aborts with a clear error."""
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("frappe_docker", "frappe_docker")]
    )
    (tmp_path / "frappe_docker").mkdir()

    with pytest.raises(VendorInputsMissingError, match="images/custom/Containerfile"):
        vendor.assert_build_inputs(tmp_path)


def test_assert_build_inputs_raises_when_a_copied_resource_is_absent(monkeypatch, tmp_path):
    """BR-VEND-006: a resource the Containerfile copies but the tree lacks aborts."""
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("frappe_docker", "frappe_docker")]
    )
    _vendored_tree(tmp_path)
    (tmp_path / "frappe_docker" / "resources/core/start.sh").unlink()

    with pytest.raises(VendorInputsMissingError, match=r"resources/core/start\.sh"):
        vendor.assert_build_inputs(tmp_path)


def test_assert_build_inputs_raises_when_source_undeclared(monkeypatch, tmp_path):
    """BR-VEND-006: no such vendored source is an actionable error, not a KeyError."""
    monkeypatch.setattr(vendor, "read_vendor_sources", lambda root: [])

    with pytest.raises(VendorInputsMissingError, match=r"tool\.ventwig\.sources"):
        vendor.assert_build_inputs(tmp_path)


def test_context_copies_skips_build_stage_copies(tmp_path):
    """Only build-context paths are required; `COPY --from=<stage>` sources are not."""
    containerfile = tmp_path / "Containerfile"
    containerfile.write_text(CONTAINERFILE, encoding="utf-8")

    assert vendor._context_copies(containerfile) == [
        "resources/core/nginx/nginx-template.conf",
        "resources/core/start.sh",
    ]


def test_resolves_accepts_a_glob(tmp_path):
    """A wildcard COPY source is satisfied by at least one match."""
    (tmp_path / "resources").mkdir()
    (tmp_path / "resources" / "a.conf").write_text("x", encoding="utf-8")

    assert vendor._resolves(tmp_path, "resources/*.conf")
    assert not vendor._resolves(tmp_path, "resources/*.missing")


def test_require_ventwig_missing(monkeypatch):
    """A missing ventwig yields an actionable VendorToolError, not a confusing failure."""
    monkeypatch.setattr(vendor.importlib.util, "find_spec", lambda name: None)

    with pytest.raises(VendorToolError, match="pip install ventwig"):
        vendor._require_ventwig()


def test_args_helper():
    assert vendor._args("status", None) == ["status"]
    assert vendor._args("sync", "frappe_docker") == ["sync", "frappe_docker"]
