"""Tests for project-root discovery and vendor-source parsing (BR-VEND-001)."""

from __future__ import annotations

import pytest

from cairn.errors import ProjectRootNotFoundError
from cairn.project import VendorSource, find_project_root, read_vendor_sources

_PYPROJECT_WITH_VENTWIG = """\
[tool.ventwig]
create_parent_package_markers = false

[[tool.ventwig.sources]]
name = "frappe_docker"
local_path = "frappe_docker"
upstream = "https://github.com/frappe/frappe_docker.git"
ref = "v3.2.1"
"""


def test_find_project_root_walks_up_to_ventwig_pyproject(tmp_path):
    """find_project_root ascends to the pyproject that declares vendoring (BR-VEND-001)."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_VENTWIG)
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert find_project_root(nested) == tmp_path


def test_find_project_root_ignores_pyproject_without_ventwig(tmp_path):
    """A pyproject without [tool.ventwig] is not a cairn project root."""
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "unrelated"\n')

    with pytest.raises(ProjectRootNotFoundError):
        find_project_root(tmp_path)


def test_read_vendor_sources_parses_entries(tmp_path):
    """read_vendor_sources returns each [[tool.ventwig.sources]] entry (BR-VEND-001)."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_WITH_VENTWIG)

    assert read_vendor_sources(tmp_path) == [
        VendorSource(name="frappe_docker", local_path="frappe_docker", ref="v3.2.1"),
    ]
