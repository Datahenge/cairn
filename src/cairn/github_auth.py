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

#: The secret id the owned Containerfile mounts for the builder stage's frappe clone.
#: Frappe's URL and ref travel as build-args, but its credential never does — a build-arg is
#: permanently readable via image history, so the token rides the same secret channel
#: `apps.json` uses (`BR-BUILD-016`, `ADR-077`).
TOKEN_SECRET_ID = "github_token"

#: Git's wording when `github.com` refuses an operation for want of credentials. It names a
#: terminal prompt, which is never the actual problem: GitHub rate-limits unauthenticated git
#: operations per IP and answers the `git-upload-pack` POST with a 401, so a *public*
#: repository fails exactly as a private one would (`BR-BUILD-019`, `ADR-077`).
_ANONYMOUS_REFUSAL_MARKER = "could not read Username for 'https://github.com'"

#: The only schemes a token can authenticate over. An SSH form (`git@github.com:...`, or
#: `ssh://`) needs a live handshake, not Basic-auth credentials — injecting into one of those
#: would silently produce a URL that does not mean what it looks like it means.
_AUTHENTICATABLE_SCHEMES = ("http", "https")


def github_token() -> str | None:
    """The one configured token, or ``None`` if private `github.com` apps aren't in use."""
    return os.environ.get(GITHUB_TOKEN_ENV_VAR) or None


def targets_github(url: str) -> bool:
    """Whether *url* is a host/scheme a token could ever be injected for.

    Same scoping as :func:`authenticated` — exact `github.com`, over `http`/`https` only —
    factored out so a caller can tell *why* an unauthenticated request failed (wrong host
    for a token to help, vs. a token that should have been configured).
    """
    parts = urlsplit(url)
    return parts.scheme in _AUTHENTICATABLE_SCHEMES and parts.hostname == _GITHUB_HOST


def authenticated(url: str, token: str | None) -> str:
    """Return *url* with *token* embedded as credentials, if it targets `github.com`.

    Any other host, any non-HTTP(S) scheme, or no token: *url* is returned unchanged. This
    MUST be the only place a token ever touches a URL, so every caller stays a single,
    auditable seam.
    """
    if not token or not targets_github(url):
        return url

    parts = urlsplit(url)
    netloc = f"{token}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def missing_token_hint() -> str:
    """The sentence appended to a failed `github.com` lookup when no token is configured
    (`BR-BUILD-016` point 5).

    A single source of truth, so a caller that supplies its own, more specific remedy (e.g.
    `setup-timer`'s token-file check, `ADR-067`) can strip exactly this sentence rather than
    duplicate its wording or leave both in the same message.
    """
    return (
        f" No ${GITHUB_TOKEN_ENV_VAR} is set — if this is a private repository, set it "
        f"and retry."
    )


def redacted(text: str, token: str | None) -> str:
    """Strip *token* out of *text*, for output that might otherwise echo it back.

    Git's own error messages sometimes quote the URL they were given verbatim — a failed
    authenticated `ls-remote` could otherwise leak the token through cairn's own exception
    message even though cairn never put it there directly.
    """
    if not token:
        return text
    return text.replace(token, "***")


def looks_like_anonymous_refusal(text: str) -> bool:
    """Whether *text* carries git's wording for a credential-less `github.com` refusal.

    Matched on git's own message rather than an HTTP status, because that message is all
    that reaches cairn: the failure happens inside the build sandbox, and only the engine's
    streamed output crosses back out (`BR-BUILD-019`).
    """
    return _ANONYMOUS_REFUSAL_MARKER in text


def anonymous_refusal_hint() -> str:
    """The remedy appended to a build that failed on an unauthenticated `github.com` clone.

    Deliberately contradicts git's own line rather than merely supplementing it: an operator
    who reads "could not read Username" reaches for a terminal or a prompt setting, neither
    of which is involved (`BR-BUILD-019`).
    """
    return (
        "github.com refused an unauthenticated git request during the build. This is not a "
        "terminal or prompt problem, despite git's wording, and the repository does not have "
        f"to be private: unauthenticated git operations are rate-limited per IP address. Set "
        f"${GITHUB_TOKEN_ENV_VAR} and retry."
    )


def unauthenticated_clone_warning() -> str:
    """The notice emitted when a build starts with no token configured.

    A token stays optional — a manifest with no private app builds without one, and always
    has (`BR-BUILD-019`). This says what the build is about to depend on, so an eventual
    refusal is recognisable rather than surprising.
    """
    return (
        f"No ${GITHUB_TOKEN_ENV_VAR} is set; the frappe clone will run unauthenticated. "
        "That works until github.com rate-limits anonymous requests from this host."
    )
