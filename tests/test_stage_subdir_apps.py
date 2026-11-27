"""Tests for the builder stage's subfolder staging script (BR-BUILD-003, 016, 020).

The script runs inside the image build with only the stdlib and git, so it is exercised here
the same way: as a subprocess, against a local git repository standing in for the remote.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cairn import vendor

SCRIPT = vendor.build_context() / "resources" / "stage_subdir_apps.py"


def _git(*args, cwd):
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def monorepo(tmp_path) -> Path:
    repo = tmp_path / "ERP"
    package = repo / "apps" / "ls_app" / "ls_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("__version__ = '1.0.0'\n")
    (repo / "README.md").write_text("outside the app\n")
    _git("init", "--quiet", "--initial-branch", "main", cwd=repo)
    _git("add", "--all", cwd=repo)
    _git("commit", "--quiet", "-m", "init", cwd=repo)
    _git("tag", "v1.0.0", cwd=repo)
    return repo


def _stage(tmp_path, entries):
    source = tmp_path / "apps.json"
    source.write_text(json.dumps(entries))
    work = tmp_path / "work"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), str(work)], capture_output=True, text=True
    )
    return result, work


def test_subfolder_becomes_a_local_repository_bench_can_clone(tmp_path, monorepo):
    """The rewritten entry points at a git repository holding only the subfolder, at the ref."""
    erpnext = {"url": "https://github.com/frappe/erpnext", "branch": "version-16"}
    result, work = _stage(
        tmp_path, [erpnext, {"url": str(monorepo), "branch": "v1.0.0", "subdir": "apps/ls_app"}]
    )
    assert result.returncode == 0, result.stderr

    staged = json.loads((work / "apps.json").read_text())
    assert staged[0] == erpnext
    assert set(staged[1]) == {"url", "branch"}
    app = Path(staged[1]["url"])
    assert app.is_absolute() and app.name == "ls_app"

    clone = tmp_path / "bench-apps" / "ls_app"
    _git("clone", "--quiet", "--branch", "v1.0.0", str(app), str(clone), cwd=tmp_path)
    assert (clone / "ls_app" / "__init__.py").is_file()
    assert not (clone / "README.md").exists()


def test_without_subfolders_entries_pass_through_in_order(tmp_path):
    """BR-BUILD-003: no subfolder, no clone, nothing reordered."""
    entries = [{"url": f"https://example.com/{n}", "branch": "main"} for n in ("a", "b", "c")]
    result, work = _stage(tmp_path, entries)

    assert result.returncode == 0, result.stderr
    assert json.loads((work / "apps.json").read_text()) == entries
    assert [p.name for p in work.iterdir()] == ["apps.json"]


@pytest.mark.parametrize("subdir", ["apps/missing", "escape"])
def test_a_folder_outside_the_repository_fails_the_build(tmp_path, monorepo, subdir):
    """A missing folder, or a symlink leading out of the clone, stops before bench runs."""
    (monorepo / "escape").symlink_to(tmp_path)
    _git("add", "--all", cwd=monorepo)
    _git("commit", "--quiet", "-m", "link", cwd=monorepo)

    result, _ = _stage(tmp_path, [{"url": str(monorepo), "branch": "main", "subdir": subdir}])

    assert result.returncode != 0
    assert f"subdir '{subdir}' is not a folder" in result.stderr


def test_credentials_never_reach_git():
    """BR-BUILD-016: the credential helper supplies the token; the URL git sees carries none."""
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        from stage_subdir_apps import plain
    finally:
        sys.path.pop(0)

    assert plain("https://x-access-token:secret@github.com/acme/ERP") == (
        "https://github.com/acme/ERP"
    )
    assert plain("https://github.com/acme/ERP") == "https://github.com/acme/ERP"
    assert plain("https://user:pw@git.example.com/ERP") == "https://user:pw@git.example.com/ERP"
