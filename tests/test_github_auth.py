"""Tests for authenticating private `github.com` app URLs (BR-BUILD-016)."""

from __future__ import annotations

from cairn import github_auth


def test_no_token_leaves_the_url_unchanged():
    url = "https://github.com/clientorg/theirrepo.git"

    assert github_auth.authenticated(url, None) == url


def test_a_github_url_is_authenticated():
    url = "https://github.com/clientorg/theirrepo.git"

    result = github_auth.authenticated(url, "ghp_secret")

    assert result == "https://ghp_secret@github.com/clientorg/theirrepo.git"


def test_an_unrelated_host_is_never_authenticated():
    """Sending the token as Basic-auth credentials to any other host would leak it there."""
    url = "https://gitlab.com/clientorg/theirrepo.git"

    assert github_auth.authenticated(url, "ghp_secret") == url


def test_a_lookalike_host_is_not_authenticated():
    """`hostname` matching is exact — a domain merely containing "github.com" is not github.com."""
    url = "https://github.com.evil.example/clientorg/theirrepo.git"

    assert github_auth.authenticated(url, "ghp_secret") == url


def test_an_ssh_form_is_never_authenticated():
    """SSH needs a live handshake, not Basic-auth credentials; injecting into one of these
    would silently produce a URL that does not mean what it looks like it means."""
    scp_style = "git@github.com:clientorg/theirrepo.git"
    explicit_ssh = "ssh://git@github.com/clientorg/theirrepo.git"

    assert github_auth.authenticated(scp_style, "ghp_secret") == scp_style
    assert github_auth.authenticated(explicit_ssh, "ghp_secret") == explicit_ssh


def test_a_port_is_preserved():
    url = "https://github.com:443/clientorg/theirrepo.git"

    result = github_auth.authenticated(url, "ghp_secret")

    assert result == "https://ghp_secret@github.com:443/clientorg/theirrepo.git"


def test_github_token_reads_the_env_var(monkeypatch):
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")

    assert github_auth.github_token() == "ghp_secret"


def test_github_token_is_none_when_unset(monkeypatch):
    monkeypatch.delenv(github_auth.GITHUB_TOKEN_ENV_VAR, raising=False)

    assert github_auth.github_token() is None


def test_github_token_is_none_when_empty(monkeypatch):
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "")

    assert github_auth.github_token() is None


def test_redacted_strips_the_token():
    text = "fatal: could not read from 'https://ghp_secret@github.com/clientorg/theirrepo'"

    assert "ghp_secret" not in github_auth.redacted(text, "ghp_secret")


def test_redacted_is_a_no_op_without_a_token():
    text = "fatal: repository not found"

    assert github_auth.redacted(text, None) == text
