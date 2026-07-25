"""Tests for apps.json generation (BR-BUILD-003/004/006)."""

from __future__ import annotations

import json
import stat

from cairn import appsjson
from cairn.config import App, Frappe, Manifest


def _manifest(apps=None):
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
        apps=apps
        if apps is not None
        else (
            App("erpnext", "https://github.com/frappe/erpnext", "version-16"),
            App("btu", "https://github.com/Datahenge/btu", "version-16"),
        ),
    )


def test_matches_upstream_shape(tmp_path):
    """Upstream expects an array of {"url", "branch"} objects."""
    assert appsjson.entries(_manifest()) == [
        {"url": "https://github.com/frappe/erpnext", "branch": "version-16"},
        {"url": "https://github.com/Datahenge/btu", "branch": "version-16"},
    ]


def test_frappe_is_not_included():
    """BR-BUILD-004: Frappe rides the FRAPPE_* build-args, never apps.json."""
    urls = [entry["url"] for entry in appsjson.entries(_manifest())]

    assert "https://github.com/frappe/frappe" not in urls


def test_order_is_preserved():
    """BR-BUILD-003: manifest order is the install sequence."""
    assert [e["url"].rsplit("/", 1)[-1] for e in appsjson.entries(_manifest())] == [
        "erpnext",
        "btu",
    ]


def test_carries_declared_refs_not_commits():
    """BR-BUILD-005: commits are recorded in provenance, never frozen into the build."""
    branches = {entry["branch"] for entry in appsjson.entries(_manifest())}

    assert branches == {"version-16"}


def test_empty_app_list_renders_an_empty_array():
    """A Frappe-only image is legal; the Containerfile skips an empty apps.json."""
    assert json.loads(appsjson.render(_manifest(apps=()))) == []


def test_render_is_byte_stable():
    """BR-BUILD-012: identical input renders identically, so --dry-run output diffs."""
    assert appsjson.render(_manifest()) == appsjson.render(_manifest())


def test_secret_file_is_private_and_removed():
    """BR-BUILD-006/BR-CFG-010: the file may carry tokens, so it is owner-only and transient."""
    with appsjson.secret_file(_manifest()) as path:
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert json.loads(path.read_text(encoding="utf-8"))[0]["url"].endswith("erpnext")
        remembered = path

    assert not remembered.exists()


def test_secret_file_removed_even_when_the_build_fails():
    """A failed build must not leave a token-bearing file behind."""
    try:
        with appsjson.secret_file(_manifest()) as path:
            remembered = path
            raise RuntimeError("build blew up")
    except RuntimeError:
        pass

    assert not remembered.exists()


def test_secret_file_is_outside_the_project(tmp_path, monkeypatch):
    """BR-BUILD-011: cairn writes nothing into its own tree or the deployment directory."""
    monkeypatch.chdir(tmp_path)

    with appsjson.secret_file(_manifest()) as path:
        assert tmp_path not in path.parents
