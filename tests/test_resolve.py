"""Tests for ref → commit resolution (BR-BUILD-005, BR-BUILD-003).

`git ls-remote` is stubbed; the parsing these tests pin down is exercised against a real
remote in the module's end-to-end verification.
"""

from __future__ import annotations

import subprocess
import types

import pytest

from cairn import github_auth, resolve
from cairn.config import App, Frappe, Manifest
from cairn.errors import RefResolutionError

BRANCH_SHA = "1111111111111111111111111111111111111111"
TAG_OBJECT_SHA = "2222222222222222222222222222222222222222"
PEELED_SHA = "3333333333333333333333333333333333333333"


def _completed(stdout: str = "", returncode: int = 0, stderr: str = ""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _stub(monkeypatch, stdout: str = "", returncode: int = 0, stderr: str = ""):
    monkeypatch.setattr(
        resolve, "_run", lambda command, name, url: _completed(stdout, returncode, stderr)
    )


# --- kind detection (BR-BUILD-005) ------------------------------------------


def test_branch_resolves_and_is_marked_moving(monkeypatch):
    """BR-BUILD-005: a branch resolves, but is flagged as able to move."""
    _stub(monkeypatch, f"{BRANCH_SHA}\trefs/heads/version-16\n")

    resolved = resolve.resolve_ref("erpnext", "https://example.com/erpnext", "version-16")

    assert resolved.commit == BRANCH_SHA
    assert resolved.kind is resolve.RefKind.BRANCH
    assert resolved.is_moving


def test_lightweight_tag_resolves_and_is_not_moving(monkeypatch):
    _stub(monkeypatch, f"{TAG_OBJECT_SHA}\trefs/tags/v15.0.0\n")

    resolved = resolve.resolve_ref("erpnext", "https://example.com/erpnext", "v15.0.0")

    assert resolved.commit == TAG_OBJECT_SHA
    assert resolved.kind is resolve.RefKind.TAG
    assert not resolved.is_moving


def test_annotated_tag_resolves_to_the_peeled_commit(monkeypatch):
    """An annotated tag names a tag object; the build checks out what it peels to."""
    _stub(
        monkeypatch,
        f"{TAG_OBJECT_SHA}\trefs/tags/v15.0.0\n{PEELED_SHA}\trefs/tags/v15.0.0^{{}}\n",
    )

    resolved = resolve.resolve_ref("erpnext", "https://example.com/erpnext", "v15.0.0")

    assert resolved.commit == PEELED_SHA
    assert resolved.kind is resolve.RefKind.TAG


def test_peeled_pattern_is_requested_explicitly(monkeypatch):
    """A pattern-filtered ls-remote omits `<ref>^{}` unless asked for it by name.

    Without this, an annotated tag resolves to the tag object instead of the commit —
    caught only by running against a real repository, since a stub can hand back a
    peeled line the real command never returns.
    """
    seen: list[list[str]] = []

    def _capture(command, name, url):
        seen.append(command)
        return _completed(f"{TAG_OBJECT_SHA}\trefs/tags/v1.0\n{PEELED_SHA}\trefs/tags/v1.0^{{}}\n")

    monkeypatch.setattr(resolve, "_run", _capture)
    resolve.resolve_ref("local", "/tmp/repo", "v1.0")

    assert seen[0][-2:] == ["v1.0", "v1.0^{}"]


def test_partial_name_match_is_not_accepted(monkeypatch):
    """Matching is exact: a ref merely ending in the name must not satisfy it."""
    _stub(monkeypatch, f"{BRANCH_SHA}\trefs/heads/release/version-16\n")

    with pytest.raises(RefResolutionError, match="neither a branch nor a tag"):
        resolve.resolve_ref("erpnext", "https://example.com/erpnext", "version-16")


# --- error paths ------------------------------------------------------------


def test_ambiguous_ref_is_rejected(monkeypatch):
    """A name that is both a branch and a tag makes the built commit ambiguous."""
    _stub(
        monkeypatch,
        f"{BRANCH_SHA}\trefs/heads/version-16\n{TAG_OBJECT_SHA}\trefs/tags/version-16\n",
    )

    with pytest.raises(RefResolutionError, match="both a branch and a tag"):
        resolve.resolve_ref("erpnext", "https://example.com/erpnext", "version-16")


def test_unknown_ref_names_the_rule(monkeypatch):
    """BR-CLI-015: the error states the constraint, not just the symptom."""
    _stub(monkeypatch, "")

    with pytest.raises(RefResolutionError, match="branch or tag only"):
        resolve.resolve_ref("btu", "https://example.com/btu", "nope")


def test_unreachable_remote_is_actionable(monkeypatch):
    """A failed ls-remote surfaces git's own last line plus the likely fix."""
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(
        resolve.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=128, stderr="fatal: repository not found\n"),
    )

    with pytest.raises(RefResolutionError, match="repository not found"):
        resolve.resolve_ref("btu", "https://example.com/nope", "main")


def test_missing_git_binary_is_actionable(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(resolve.subprocess, "run", _raise)

    with pytest.raises(RefResolutionError, match="`git` not found on PATH"):
        resolve.resolve_ref("btu", "https://example.com/btu", "main")


def test_timeout_is_actionable(monkeypatch):
    def _raise(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="git", timeout=60)

    monkeypatch.setattr(resolve.subprocess, "run", _raise)

    with pytest.raises(RefResolutionError, match="timed out"):
        resolve.resolve_ref("btu", "https://example.com/btu", "main")


def test_terminal_prompt_is_disabled(monkeypatch):
    """A private or misspelled URL must fail fast, never block on a credential prompt."""
    captured: dict = {}

    def _capture(command, **kwargs):
        captured.update(kwargs)
        return _completed(f"{BRANCH_SHA}\trefs/heads/main\n")

    monkeypatch.setattr(resolve.subprocess, "run", _capture)
    resolve.resolve_ref("btu", "https://example.com/btu", "main")

    assert captured["env"]["GIT_TERMINAL_PROMPT"] == "0"


# --- private github.com apps (BR-BUILD-016) ----------------------------------


def test_a_github_token_authenticates_the_ls_remote_url(monkeypatch):
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    captured: dict = {}

    def _capture(command, **kwargs):
        captured["command"] = command
        return _completed(f"{BRANCH_SHA}\trefs/heads/main\n")

    monkeypatch.setattr(resolve.subprocess, "run", _capture)
    resolve.resolve_ref("btu", "https://github.com/clientorg/btu", "main")

    assert "https://ghp_secret@github.com/clientorg/btu" in captured["command"]


def test_a_github_token_is_not_sent_to_an_unrelated_host(monkeypatch):
    """Injecting anywhere but github.com would leak the token to that host."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    captured: dict = {}

    def _capture(command, **kwargs):
        captured["command"] = command
        return _completed(f"{BRANCH_SHA}\trefs/heads/main\n")

    monkeypatch.setattr(resolve.subprocess, "run", _capture)
    resolve.resolve_ref("btu", "https://example.com/btu", "main")

    assert "ghp_secret" not in " ".join(captured["command"])


def test_resolved_ref_url_stays_plain_even_with_a_token(monkeypatch):
    """The token is for the live git call only — never for anything stored or recorded."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    _stub(monkeypatch, f"{BRANCH_SHA}\trefs/heads/main\n")

    resolved = resolve.resolve_ref("btu", "https://github.com/clientorg/btu", "main")

    assert resolved.url == "https://github.com/clientorg/btu"


def test_a_failed_authenticated_lookup_does_not_leak_the_token(monkeypatch):
    """git's own error text can quote the URL it was given verbatim; that must not carry the
    token back out through cairn's own exception."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(
        resolve.subprocess,
        "run",
        lambda *a, **k: _completed(
            returncode=128,
            stderr="fatal: could not read from 'https://ghp_secret@github.com/clientorg/btu'\n",
        ),
    )

    with pytest.raises(RefResolutionError) as excinfo:
        resolve.resolve_ref("btu", "https://github.com/clientorg/btu", "main")

    assert "ghp_secret" not in str(excinfo.value)


# --- whole-manifest resolution ----------------------------------------------


def _manifest():
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://example.com/frappe", "version-16"),
        apps=(
            App("erpnext", "https://example.com/erpnext", "version-16"),
            App("btu", "https://example.com/btu", "version-16"),
        ),
    )


def test_resolve_manifest_preserves_app_order(monkeypatch):
    """BR-BUILD-003: order is load-bearing for hashing and the install sequence."""
    _stub(monkeypatch, f"{BRANCH_SHA}\trefs/heads/version-16\n")

    resolution = resolve.resolve_manifest(_manifest())

    assert [r.name for r in resolution.apps] == ["erpnext", "btu"]
    assert [r.name for r in resolution.all_refs] == ["frappe", "erpnext", "btu"]


def test_moving_refs_collects_every_branch(monkeypatch):
    """BR-BUILD-005: cairn should warn when a manifest pins to a moving branch."""
    _stub(monkeypatch, f"{BRANCH_SHA}\trefs/heads/version-16\n")

    resolution = resolve.resolve_manifest(_manifest())

    assert [r.name for r in resolve.moving_refs(resolution)] == ["frappe", "erpnext", "btu"]


def test_moving_refs_empty_when_all_tags(monkeypatch):
    _stub(monkeypatch, f"{TAG_OBJECT_SHA}\trefs/tags/version-16\n")

    resolution = resolve.resolve_manifest(_manifest())

    assert resolve.moving_refs(resolution) == ()
    assert resolution.frappe.short_commit == TAG_OBJECT_SHA[:12]


# --- git presence probe (BR-CLI-007) ----------------------------------------


def test_git_version_parses_the_banner(monkeypatch):
    monkeypatch.setattr(
        resolve.subprocess, "run", lambda *a, **k: _completed("git version 2.47.1\n")
    )

    assert resolve.git_version() == "2.47.1"


def test_git_version_reports_absence_actionably(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(resolve.subprocess, "run", _raise)

    with pytest.raises(RefResolutionError, match="Install git"):
        resolve.git_version()
