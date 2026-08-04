"""Environment pointers: assign, retire (BR-CLI-004, BR-CLI-009, BR-DEPLOY-004, ADR-052).

An environment is a **name for a registry tag**, and nothing more — at most one per manifest,
and the name *is* the tag (`BR-DEPLOY-009a`). Moving that pointer is the whole of deploying,
promoting, and rolling back (`BR-DEPLOY-004`): all three collapse into one question, asked of
one manifest at a time — does the registry already hold an image matching this manifest's own,
currently-resolved refs?

**Promotion is proof, not assertion** (`ADR-052`). This module never reads a second manifest,
and there is no selector menu (`--latest`/`--previous`/`--id`/`--from`, `ADR-050`, retired) to
choose between candidates. `check` always resolves this manifest's own refs exactly as `build`
would, computes the same deterministic primary tag (`BR-BUILD-008`), and asks the registry:

    found      -> retag this environment onto that digest (server-side, no rebuild)
    not found  -> report that, and do nothing; only `build` creates an image

Rollback is the same operation reached a different way: reset the tracked ref to an earlier
commit outside cairn, then check again — if that commit's image is still in the registry (not
yet GC'd), it retags instantly, no rebuild.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import build, registry
from .config import BuildConfig, Manifest
from .errors import RegistryError, UnknownEnvironmentError
from .registry import ImageRef

#: The environment whose pointer may never move without explicit confirmation (BR-CLI-010).
PRODUCTION = "production"


@dataclass(frozen=True)
class Environment:
    """A manifest's declared environment: its name, which is also its registry tag."""

    name: str
    ref: ImageRef

    @property
    def is_production(self) -> bool:
        """Whether moving this pointer requires explicit confirmation (BR-CLI-010).

        Matched on the environment's **name**, which is also its tag now (`ADR-052`) — there
        is no longer a name/tag distinction to worry about matching the wrong half of.
        """
        return self.name.lower() == PRODUCTION


@dataclass(frozen=True)
class Assignment:
    """A checked, but not yet applied, environment assignment (`BR-CLI-011`'s ``--dry-run``)."""

    environment: Environment
    source_ref: ImageRef | None  #: None means nothing matching exists in the registry yet
    digest: str | None  #: the source's digest, set whenever source_ref is
    previous_digest: str | None  #: what the environment's tag resolves to right now, if anything

    @property
    def found(self) -> bool:
        return self.source_ref is not None

    @property
    def is_noop(self) -> bool:
        """Whether the pointer already resolves to the found image."""
        return self.found and self.previous_digest == self.digest

    def render(self) -> str:
        lines = [f"environment  {self.environment.name}", f"tag          {self.environment.ref}"]
        if not self.found:
            lines.append(
                "image        nothing in the registry matches this manifest's current refs"
            )
            return "\n".join(lines)
        lines.append(f"image        {self.source_ref}")
        lines.append(f"digest       {self.digest}")
        if self.previous_digest is None:
            lines.append("currently    (the tag does not exist yet)")
        elif self.is_noop:
            lines.append("currently    the same image — this would change nothing")
        else:
            lines.append(f"currently    {self.previous_digest}")
        return "\n".join(lines)


def declared(manifest: Manifest, build_config: BuildConfig) -> Environment | None:
    """This manifest's declared environment, or ``None`` if it has none (`BR-DEPLOY-009a`)."""
    if manifest.environment is None:
        return None
    base = build_config.resolve_image_base(manifest.image_name)
    return Environment(
        name=manifest.environment,
        ref=registry.parse_ref(f"{base}:{manifest.environment}"),
    )


def require(manifest: Manifest, build_config: BuildConfig) -> Environment:
    """Return this manifest's declared environment, or raise (`BR-CLI-009`)."""
    environment = declared(manifest, build_config)
    if environment is None:
        raise UnknownEnvironmentError(
            f"{manifest.path} declares no environment — add `[cairn] environment = \"...\"` "
            f"naming the registry tag this manifest's build should point at."
        )
    return environment


def check(manifest: Manifest, build_config: BuildConfig) -> Assignment:
    """Resolve *manifest*'s own refs and check the registry — decide, but write nothing.

    Reuses `build.plan()` for resolution so the primary tag computed here is bit-for-bit the
    one a real build would produce (`BR-BUILD-008`) — anything less exact risks computing a
    *different*, wrong tag and never finding a match that genuinely exists.
    """
    environment = require(manifest, build_config)
    plan = build.plan(manifest, build_config)
    found = build.existing_in_registry(plan, build_config)
    return Assignment(
        environment=environment,
        source_ref=found.ref if found else None,
        digest=found.digest if found else None,
        previous_digest=_current_digest(environment),
    )


def check_known(environment: Environment, source_ref: ImageRef, digest: str) -> Assignment:
    """Like :func:`check`, but for a digest the caller already resolved
    (``build --assign-tag``, `BR-CLI-002a`) — skips re-resolving the manifest and re-querying
    the registry for something `build` just confirmed exists, whether by a fresh build or
    either of its own short-circuits (`BR-BUILD-014`/`014a`).
    """
    return Assignment(
        environment=environment,
        source_ref=source_ref,
        digest=digest,
        previous_digest=_current_digest(environment),
    )


def apply(assignment: Assignment) -> str:
    """Write the pointer, server-side, and return the digest now under it (`BR-DEPLOY-004`).

    Callers only reach this once :attr:`Assignment.found` is true — there is nothing to point
    at otherwise.
    """
    assert assignment.source_ref is not None, "apply() called on an assignment that found nothing"
    return registry.retag(assignment.source_ref, assignment.environment.name)


def retire(manifest: Manifest, build_config: BuildConfig) -> Environment:
    """Confirm this manifest's environment may be retired, returning it (`BR-CLI-009`).

    cairn removes nothing here. Retirement is the operator deleting `[cairn] environment` from
    the manifest; this validates that the manifest currently declares one and hands back what
    the caller must warn about — because **the registry tag persists**. GHCR has no per-tag
    delete, and deleting the underlying version would destroy an image other environments may
    still point at.
    """
    return require(manifest, build_config)


def _current_digest(environment: Environment) -> str | None:
    """What the environment's tag resolves to now, or ``None`` if it does not exist yet."""
    try:
        return registry.digest_of(environment.ref)
    except RegistryError:
        # A tag that is not there is the normal state before the first deploy, and is not a
        # failure — it is precisely what `assign-tag` creates.
        return None
