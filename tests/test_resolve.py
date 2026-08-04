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


@pytest.mark.parametrize(
    ("ref", "stdout", "expected_commit", "expected_kind", "expected_moving"),
    [
        # BR-BUILD-005: a branch resolves, but is flagged as able to move.
        ("version-16", f"{BRANCH_SHA}\trefs/heads/version-16\n", BRANCH_SHA, resolve.RefKind.BRANCH, True),
        ("v15.0.0", f"{TAG_OBJECT_SHA}\trefs/tags/v15.0.0\n", TAG_OBJECT_SHA, resolve.RefKind.TAG, False),
        # an annotated tag names a tag object; the build checks out what it peels to.
        (
            "v15.0.0",
            f"{TAG_OBJECT_SHA}\trefs/tags/v15.0.0\n{PEELED_SHA}\trefs/tags/v15.0.0^{{}}\n",
            PEELED_SHA,
            resolve.RefKind.TAG,
            False,
        ),
    ],
    ids=["branch", "lightweight-tag", "annotated-tag"],
)
def test_a_ref_resolves_to_its_commit_and_kind(
    monkeypatch, ref, stdout, expected_commit, expected_kind, expected_moving
):
    _stub(monkeypatch, stdout)

    resolved = resolve.resolve_ref("erpnext", "https://example.com/erpnext", ref)

    assert resolved.commit == expected_commit
    assert resolved.kind is expected_kind
    assert resolved.is_moving is expected_moving


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


def _raise_file_not_found(*args, **kwargs):
    raise FileNotFoundError("git")


def _raise_timeout(*args, **kwargs):
    raise subprocess.TimeoutExpired(cmd="git", timeout=60)


@pytest.mark.parametrize(
    ("run_stub", "expected"),
    [
        (
            lambda *a, **k: _completed(returncode=128, stderr="fatal: repository not found\n"),
            "repository not found",
        ),
        (_raise_file_not_found, "`git` not found on PATH"),
        (_raise_timeout, "timed out"),
    ],
    ids=["unreachable-remote", "missing-git-binary", "timeout"],
)
def test_a_failed_lookup_is_actionable(monkeypatch, run_stub, expected):
    """A failed ls-remote surfaces something actionable regardless of failure mode: git's own
    last line plus the likely fix, a missing binary, or a timeout."""
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(resolve.subprocess, "run", run_stub)

    with pytest.raises(RefResolutionError, match=expected):
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


def test_a_missing_token_is_named_on_a_failed_github_lookup(monkeypatch):
    """BR-BUILD-016 point 5: git's own wording (`could not read Username`, `terminal prompts
    disabled`) names the symptom, not the fix — cairn must also name the env var."""
    monkeypatch.delenv(github_auth.GITHUB_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(
        resolve.subprocess,
        "run",
        lambda *a, **k: _completed(
            returncode=128,
            stderr="fatal: could not read Username for 'https://github.com': "
            "terminal prompts disabled\n",
        ),
    )

    with pytest.raises(RefResolutionError, match=github_auth.GITHUB_TOKEN_ENV_VAR):
        resolve.resolve_ref("btu", "https://github.com/clientorg/btu", "main")


def test_no_token_hint_for_a_non_github_host(monkeypatch):
    """The hint only makes sense where a token could ever have helped."""
    monkeypatch.delenv(github_auth.GITHUB_TOKEN_ENV_VAR, raising=False)
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(
        resolve.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=128, stderr="fatal: repository not found\n"),
    )

    with pytest.raises(RefResolutionError) as excinfo:
        resolve.resolve_ref("btu", "https://example.com/btu", "main")

    assert github_auth.GITHUB_TOKEN_ENV_VAR not in str(excinfo.value)


def test_no_token_hint_when_a_token_is_already_configured(monkeypatch):
    """A configured-but-wrong token is a different problem; don't tell the operator to set
    something they already set."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    monkeypatch.setattr(resolve, "_run", resolve._run)  # use the real wrapper
    monkeypatch.setattr(
        resolve.subprocess,
        "run",
        lambda *a, **k: _completed(returncode=128, stderr="fatal: Authentication failed\n"),
    )

    with pytest.raises(RefResolutionError) as excinfo:
        resolve.resolve_ref("btu", "https://github.com/clientorg/btu", "main")

    assert github_auth.GITHUB_TOKEN_ENV_VAR not in str(excinfo.value)


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
