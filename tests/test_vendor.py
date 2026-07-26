"""Tests for the vendored-tree drift and integrity checks (BR-VEND-005/006/007)."""

from __future__ import annotations

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


def _vendored_tree(root, containerfile: str = CONTAINERFILE) -> None:
    """Materialize a minimal vendored frappe_docker tree under *root*."""
    custom = root / vendor.CUSTOM_CONTAINERFILE
    custom.parent.mkdir(parents=True)
    custom.write_text(containerfile, encoding="utf-8")
    for name in ("resources/core/nginx/nginx-template.conf", "resources/core/start.sh"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x", encoding="utf-8")


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> types.SimpleNamespace:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


# --- assert_clean, package-relative and ventwig-independent (BR-VEND-005) ---


def test_assert_clean_passes_when_the_tree_matches_its_pin(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)
    monkeypatch.setattr(vendor, "read_pin", lambda: {"synced_tree": "deadbeef"})
    monkeypatch.setattr(vendor, "_tree_hash", lambda path: "deadbeef")

    vendor.assert_clean()  # must not raise


def test_assert_clean_raises_on_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)
    monkeypatch.setattr(vendor, "read_pin", lambda: {"synced_tree": "deadbeef"})
    monkeypatch.setattr(vendor, "_tree_hash", lambda path: "0000000")

    with pytest.raises(VendorDriftError, match="drifted"):
        vendor.assert_clean()


def test_assert_clean_raises_when_never_synced(monkeypatch):
    monkeypatch.setattr(vendor, "read_pin", lambda: {})

    with pytest.raises(VendorDriftError, match="no recorded pin"):
        vendor.assert_clean()


def test_tree_hash_matches_ventwigs_own_algorithm(tmp_path):
    """cairn recomputes the same git tree hash ventwig would, needing only `git`."""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world", encoding="utf-8")

    first = vendor._tree_hash(tmp_path)
    second = vendor._tree_hash(tmp_path)

    assert first == second  # deterministic
    assert len(first) == 40  # a real git object id


def test_tree_hash_changes_when_content_changes(tmp_path):
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    before = vendor._tree_hash(tmp_path)

    (tmp_path / "a.txt").write_text("hand-edited", encoding="utf-8")
    after = vendor._tree_hash(tmp_path)

    assert before != after


# --- assert_no_nested_git (BR-VEND-007) --------------------------------------


def test_assert_no_nested_git_raises_when_present(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)
    (tmp_path / ".git").mkdir()

    with pytest.raises(VendorDriftError, match=r"nested \.git"):
        vendor.assert_no_nested_git()


def test_assert_no_nested_git_passes_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)

    vendor.assert_no_nested_git()  # must not raise


# --- assert_build_inputs (BR-VEND-006) ---------------------------------------


def test_assert_build_inputs_passes_when_complete(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)
    _vendored_tree(tmp_path)

    vendor.assert_build_inputs()  # must not raise


def test_assert_build_inputs_raises_when_containerfile_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)

    with pytest.raises(VendorInputsMissingError, match="images/custom/Containerfile"):
        vendor.assert_build_inputs()


def test_assert_build_inputs_raises_when_a_copied_resource_is_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "FRAPPE_DOCKER_DIR", tmp_path)
    _vendored_tree(tmp_path)
    (tmp_path / "resources/core/start.sh").unlink()

    with pytest.raises(VendorInputsMissingError, match=r"resources/core/start\.sh"):
        vendor.assert_build_inputs()


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


# --- read_pin / sync's pin refresh (BR-VEND-002/003) -------------------------


def test_read_pin_returns_empty_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(vendor, "PIN_FILE", tmp_path / "absent.toml")

    assert vendor.read_pin() == {}


def test_read_pin_reads_ref_and_commit(monkeypatch, tmp_path):
    pin_file = tmp_path / "frappe_docker.pin.toml"
    pin_file.write_text(
        'ref = "v3.2.1"\ncommit = "d4a3100"\nsynced_tree = "abc123"\n', encoding="utf-8"
    )
    monkeypatch.setattr(vendor, "PIN_FILE", pin_file)

    assert vendor.read_pin() == {"ref": "v3.2.1", "commit": "d4a3100", "synced_tree": "abc123"}


def test_sync_refreshes_the_pin_file_after_a_successful_ventwig_sync(monkeypatch, tmp_path):
    """`sync()` is the only place a fresh pin is written — from ventwig's own lock."""
    root = tmp_path
    (root / "pyproject.toml").write_text(
        '[tool.ventwig]\n[[tool.ventwig.sources]]\nname = "frappe_docker"\n'
        'local_path = "frappe_docker"\nref = "v3.3.0"\n',
        encoding="utf-8",
    )
    (root / vendor.LOCK_NAME).write_text(
        '[frappe_docker]\nsynced_commit = "cafef00d"\nsynced_tree = "abc123"\n'
        'synced_at = "2026-08-01T00:00:00Z"\n',
        encoding="utf-8",
    )
    pin_file = tmp_path / "pin.toml"
    monkeypatch.setattr(vendor, "PIN_FILE", pin_file)
    monkeypatch.setattr(vendor, "_run", lambda *a, **k: _completed(0))

    vendor.sync(root)

    pin = vendor.read_pin()
    assert pin == {
        "ref": "v3.3.0",
        "commit": "cafef00d",
        "synced_tree": "abc123",
        "synced_at": "2026-08-01T00:00:00Z",
    }


def test_sync_does_not_touch_the_pin_file_when_ventwig_fails(monkeypatch, tmp_path):
    pin_file = tmp_path / "pin.toml"
    monkeypatch.setattr(vendor, "PIN_FILE", pin_file)
    monkeypatch.setattr(vendor, "_run", lambda *a, **k: _completed(1))

    vendor.sync(tmp_path)

    assert not pin_file.exists()


def test_refresh_pin_file_leaves_previous_pin_when_source_undeclared(monkeypatch, tmp_path):
    monkeypatch.setattr(
        vendor, "read_vendor_sources", lambda root: [VendorSource("other", "other")]
    )
    pin_file = tmp_path / "pin.toml"
    pin_file.write_text('ref = "old"\n', encoding="utf-8")
    monkeypatch.setattr(vendor, "PIN_FILE", pin_file)

    vendor._refresh_pin_file(tmp_path, "frappe_docker")

    assert pin_file.read_text(encoding="utf-8") == 'ref = "old"\n'


def test_require_ventwig_missing(monkeypatch):
    """A missing ventwig yields an actionable VendorToolError, not a confusing failure."""
    monkeypatch.setattr(vendor.importlib.util, "find_spec", lambda name: None)

    with pytest.raises(VendorToolError, match="pip install ventwig"):
        vendor._require_ventwig()


def test_args_helper():
    assert vendor._args("status", None) == ["status"]
    assert vendor._args("sync", "frappe_docker") == ["sync", "frappe_docker"]
