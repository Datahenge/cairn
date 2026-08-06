"""Resolve manifest refs to concrete commits — "resolve and record" (BR-BUILD-005).

Every ref (Frappe plus each app) is resolved against its remote at build time with
``git ls-remote``, and the resulting commits are what drive provenance (`BR-BUILD-011`),
the cache bust (`BR-BUILD-007`), and the input hash in the image tag (`BR-BUILD-008`).

The commits are **recorded, never frozen into the build** (`BR-BUILD-005`): the build
still clones the declared branch or tag, so cairn's guarantee is input-determinism, not
hermeticity (`BR-BUILD-013`).

Two properties this module exists to enforce:

* **Refs pin by branch or tag only.** A raw commit SHA is rejected in the manifest
  (`config._reject_commit_sha`); here, a ref that is neither a branch nor a tag on the
  remote is an error naming the ref rather than a confusing clone failure later.
* **Moving refs are visible.** A branch resolves today and may resolve differently
  tomorrow, so :attr:`ResolvedRef.is_moving` marks it and :func:`moving_refs` collects
  them for the caller to warn about — `BR-BUILD-005` says the manifest *should* pin to
  tags.

Resolution authenticates only a `github.com` URL, and only with the one token
``CAIRN_GITHUB_TOKEN`` configures (`github_auth`, `BR-BUILD-016`) — everything else is
unauthenticated by design: ``GIT_TERMINAL_PROMPT=0`` ensures a private or misspelled URL still
fails fast rather than blocking on a credential prompt.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from enum import Enum

from . import github_auth
from .config import App, Manifest
from .errors import RefResolutionError

#: Ceiling on one `git ls-remote`, so an unreachable remote cannot stall a build.
LS_REMOTE_TIMEOUT_SECONDS = 60

#: Ceiling on the local `git --version` probe, which contacts nothing.
GIT_PROBE_TIMEOUT_SECONDS = 10

_HEADS = "refs/heads/"
_TAGS = "refs/tags/"
_PEELED_SUFFIX = "^{}"


class RefKind(Enum):
    """Whether a ref is immutable-by-convention (tag) or moving (branch)."""

    TAG = "tag"
    BRANCH = "branch"


@dataclass(frozen=True)
class ResolvedRef:
    """One manifest ref resolved to the commit it pointed at, at resolution time."""

    name: str
    url: str
    ref: str
    commit: str
    kind: RefKind

    @property
    def is_moving(self) -> bool:
        """Whether this ref may resolve to a different commit on a later build."""
        return self.kind is RefKind.BRANCH

    @property
    def short_commit(self) -> str:
        return self.commit[:12]


@dataclass(frozen=True)
class Resolution:
    """Every resolved input of one manifest, apps in manifest order (BR-BUILD-003)."""

    frappe: ResolvedRef
    apps: tuple[ResolvedRef, ...]

    @property
    def all_refs(self) -> tuple[ResolvedRef, ...]:
        """Frappe first, then apps in manifest order — a stable hashing sequence."""
        return (self.frappe, *self.apps)


def resolve_manifest(manifest: Manifest) -> Resolution:
    """Resolve Frappe and every app in *manifest* (BR-BUILD-005).

    App order is preserved so downstream hashing and the install sequence stay
    deterministic (`BR-BUILD-003`).
    """
    return Resolution(
        frappe=resolve_ref("frappe", manifest.frappe.url, manifest.frappe.ref),
        apps=tuple(resolve_app(app) for app in manifest.apps),
    )


def resolve_app(app: App) -> ResolvedRef:
    """Resolve one ``[[cairn.apps]]`` entry."""
    return resolve_ref(app.name, app.url, app.ref)


def resolve_ref(name: str, url: str, ref: str) -> ResolvedRef:
    """Resolve *ref* at *url* to a commit, or raise :class:`RefResolutionError`.

    An annotated tag resolves to the commit it peels to, not to the tag object — that
    is what a clone checks out, and what provenance must record.
    """
    heads, tags = _ls_remote(name, url, ref)

    if heads and tags:
        raise RefResolutionError(
            f"{name}: ref '{ref}' exists at {url} as both a branch and a tag, so which "
            f"commit gets built is ambiguous. Rename one, or pin to the other explicitly."
        )
    if tags:
        return ResolvedRef(name=name, url=url, ref=ref, commit=tags, kind=RefKind.TAG)
    if heads:
        return ResolvedRef(name=name, url=url, ref=ref, commit=heads, kind=RefKind.BRANCH)

    raise RefResolutionError(
        f"{name}: ref '{ref}' is neither a branch nor a tag at {url}. "
        f"Refs pin by branch or tag only."
    )


def git_version() -> str:
    """Return the installed git version, or raise :class:`RefResolutionError`.

    git is a build prerequisite because every manifest ref is resolved with
    ``git ls-remote`` (`BR-BUILD-005`), so ``cairn doctor`` probes for it (`BR-CLI-007`).
    No minimum version is enforced: ``ls-remote`` and its pattern matching predate every
    git a current distribution ships.
    """
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=GIT_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RefResolutionError(
            "`git` not found on PATH; cairn resolves every manifest ref with "
            "`git ls-remote`. Install git."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RefResolutionError(
            f"`git --version` timed out after {GIT_PROBE_TIMEOUT_SECONDS}s."
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RefResolutionError(
            f"`git --version` failed ({detail[-1] if detail else 'unknown error'})."
        )
    return result.stdout.strip().rsplit(maxsplit=1)[-1]  # "git version 2.47.1"


def moving_refs(resolution: Resolution) -> tuple[ResolvedRef, ...]:
    """Return the refs pinned to a moving branch, for the caller to warn about.

    `BR-BUILD-005` says cairn *should* warn; emitting the warning is the CLI's job, so
    this module stays free of output.
    """
    return tuple(ref for ref in resolution.all_refs if ref.is_moving)


def _ls_remote(name: str, url: str, ref: str) -> tuple[str | None, str | None]:
    """Return ``(branch_commit, tag_commit)`` for *ref* at *url*; either may be ``None``.

    Matching is exact on ``refs/heads/<ref>`` and ``refs/tags/<ref>`` — passing the bare
    name as a pattern would also match a ref merely *ending* in it (``release/<ref>``).

    The peeled pattern ``<ref>^{}`` must be requested explicitly: a pattern-filtered
    ``ls-remote`` omits the peeled line, so an annotated tag would otherwise resolve to
    the tag object rather than the commit the build checks out.
    """
    authenticated_url = github_auth.authenticated(url, github_auth.github_token())
    result = _run(
        ["git", "ls-remote", "--heads", "--tags", authenticated_url, ref, f"{ref}{_PEELED_SUFFIX}"],
        name,
        url,
    )

    branch_commit: str | None = None
    tag_commit: str | None = None
    peeled_commit: str | None = None
    for line in result.stdout.splitlines():
        commit, _, refname = line.partition("\t")
        refname = refname.strip()
        if refname == f"{_HEADS}{ref}":
            branch_commit = commit.strip()
        elif refname == f"{_TAGS}{ref}":
            tag_commit = commit.strip()
        elif refname == f"{_TAGS}{ref}{_PEELED_SUFFIX}":
            peeled_commit = commit.strip()

    # An annotated tag reports the tag object first and the commit it peels to second.
    return branch_commit, (peeled_commit or tag_commit)


def _run(command: list[str], name: str, url: str) -> subprocess.CompletedProcess[str]:
    """Run *command*, converting every failure mode into :class:`RefResolutionError`.

    *url* is always the **plain** URL, used only for messages — *command* may carry an
    authenticated form (`github_auth.authenticated`). git's own stderr is redacted too: some
    failures quote the URL they were given verbatim, which would otherwise leak the token
    through cairn's own exception even though cairn never put it in the message directly.
    """
    token = github_auth.github_token()
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=LS_REMOTE_TIMEOUT_SECONDS,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RefResolutionError(
            "`git` not found on PATH; cairn resolves manifest refs with git ls-remote."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RefResolutionError(
            f"{name}: timed out after {LS_REMOTE_TIMEOUT_SECONDS}s contacting {url}."
        ) from exc

    if result.returncode != 0:
        raw = github_auth.redacted(result.stderr or result.stdout, token)
        detail = raw.strip().splitlines()
        message = (
            f"{name}: cannot read {url} — {detail[-1] if detail else 'git ls-remote failed'}. "
            f"Check the URL, and that the repository is public or your git credentials "
            f"are configured."
        )
        if token is None and github_auth.targets_github(url):
            message += github_auth.missing_token_hint()
        raise RefResolutionError(message)
    return result
