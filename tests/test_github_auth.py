"""Tests for authenticating private `github.com` app URLs (BR-BUILD-016)."""

from __future__ import annotations

import pytest

from cairn import github_auth


@pytest.mark.parametrize(
    ("url", "token"),
    [
        ("https://github.com/clientorg/theirrepo.git", None),
        # sending the token as Basic-auth credentials to any other host would leak it there.
        ("https://gitlab.com/clientorg/theirrepo.git", "ghp_secret"),
        # `hostname` matching is exact — a domain merely containing "github.com" is not
        # github.com.
        ("https://github.com.evil.example/clientorg/theirrepo.git", "ghp_secret"),
        # SSH needs a live handshake, not Basic-auth credentials; injecting into one of these
        # would silently produce a URL that does not mean what it looks like it means.
        ("git@github.com:clientorg/theirrepo.git", "ghp_secret"),
        ("ssh://git@github.com/clientorg/theirrepo.git", "ghp_secret"),
    ],
    ids=["no-token", "unrelated-host", "lookalike-host", "scp-style-ssh", "explicit-ssh"],
)
def test_the_url_is_left_unchanged(url, token):
    assert github_auth.authenticated(url, token) == url


def test_a_github_url_is_authenticated():
    url = "https://github.com/clientorg/theirrepo.git"

    result = github_auth.authenticated(url, "ghp_secret")

    assert result == "https://ghp_secret@github.com/clientorg/theirrepo.git"


def test_a_port_is_preserved():
    url = "https://github.com:443/clientorg/theirrepo.git"

    result = github_auth.authenticated(url, "ghp_secret")

    assert result == "https://ghp_secret@github.com:443/clientorg/theirrepo.git"


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ghp_secret", "ghp_secret"), (None, None), ("", None)],
    ids=["set", "unset", "empty"],
)
def test_github_token_reads_the_env_var(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv(github_auth.GITHUB_TOKEN_ENV_VAR, raising=False)
    else:
        monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, value)

    assert github_auth.github_token() == expected


def test_redacted_strips_the_token():
    text = "fatal: could not read from 'https://ghp_secret@github.com/clientorg/theirrepo'"

    assert "ghp_secret" not in github_auth.redacted(text, "ghp_secret")


def test_redacted_is_a_no_op_without_a_token():
    text = "fatal: repository not found"

    assert github_auth.redacted(text, None) == text


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/clientorg/theirrepo.git", True),
        ("https://github.com:443/clientorg/theirrepo.git", True),
        ("https://gitlab.com/clientorg/theirrepo.git", False),
        ("https://github.com.evil.example/clientorg/theirrepo.git", False),
        ("git@github.com:clientorg/theirrepo.git", False),
        ("ssh://git@github.com/clientorg/theirrepo.git", False),
    ],
    ids=["https", "https-with-port", "unrelated-host", "lookalike-host", "scp-style-ssh", "explicit-ssh"],
)
def test_targets_github(url, expected):
    assert github_auth.targets_github(url) is expected
