"""Authenticate a private `github.com` app URL with an operator-provided token (`BR-BUILD-016`).

One token, read from ``CAIRN_GITHUB_TOKEN``, covers every private app for now — multiple
tokens (per-org, per-app) is an explicit non-goal, deferred until a concrete need arises.

Two things are load-bearing:

* **Scoped to `github.com` exactly.** Sending the token as HTTP Basic-auth credentials to any
  other host would leak it there — this module is the one seam every caller routes through, so
  that scoping only has to be right in one place.
* **The token is never stored.** Not in ``cairn.toml`` — that manifest stays portable and
  secret-free (`BR-BUILD-001`, `ADR-017`). Not in ``builder.toml`` either — that file is
  deliberately shared and group-writable (`BR-DEPLOY-022`), the wrong place for a secret. It
  exists only in memory, and inside the already-ephemeral, owner-only ``apps.json`` secret file
  (`appsjson.written`) — never in provenance, `--dry-run` output, or an error message.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

#: Read directly, like `CAIRN_MANIFEST` — not a `BUILD_CONFIG_KEYS` entry, since (by design)
#: it has no `builder.toml` counterpart: rule 4 is that cairn stores no secrets.
GITHUB_TOKEN_ENV_VAR = "CAIRN_GITHUB_TOKEN"

#: The only host a token is ever injected for.
_GITHUB_HOST = "github.com"

#: The only schemes a token can authenticate over. An SSH form (`git@github.com:...`, or
#: `ssh://`) needs a live handshake, not Basic-auth credentials — injecting into one of those
#: would silently produce a URL that does not mean what it looks like it means.
_AUTHENTICATABLE_SCHEMES = ("http", "https")


def github_token() -> str | None:
    """The one configured token, or ``None`` if private `github.com` apps aren't in use."""
    return os.environ.get(GITHUB_TOKEN_ENV_VAR) or None


def authenticated(url: str, token: str | None) -> str:
    """Return *url* with *token* embedded as credentials, if it targets `github.com`.

    Any other host, any non-HTTP(S) scheme, or no token: *url* is returned unchanged. This
    MUST be the only place a token ever touches a URL, so every caller stays a single,
    auditable seam.
    """
    if not token:
        return url

    parts = urlsplit(url)
    if parts.scheme not in _AUTHENTICATABLE_SCHEMES or parts.hostname != _GITHUB_HOST:
        return url

    netloc = f"{token}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def redacted(text: str, token: str | None) -> str:
    """Strip *token* out of *text*, for output that might otherwise echo it back.

    Git's own error messages sometimes quote the URL they were given verbatim — a failed
    authenticated `ls-remote` could otherwise leak the token through cairn's own exception
    message even though cairn never put it there directly.
    """
    if not token:
        return text
    return text.replace(token, "***")
