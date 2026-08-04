"""Environment pointers: assign, retire (BR-CLI-004, BR-CLI-009, BR-DEPLOY-004, ADR-050).

An environment is a **name for a registry tag** and nothing more. The manifest's
``[cairn.declared_environments]`` table says which names exist (`BR-DEPLOY-009a`); the tag it
maps to is the desired-state pointer a target watches (`BR-DEPLOY-002`). Moving that pointer
is the whole of deploying:

    deploy   = point an environment's tag at a newly built image
    promote  = point it at whatever another environment currently runs
    rollback = point it back at a prior image

All three are one operation on one tag, with **no rebuild and no pull** (`BR-DEPLOY-004`).
That equivalence is the reason a rollback is as fast and as boring as a deploy, and it is
why this module has no notion of "forward" or "backward".

**The name is declared, never inferred** (`BR-CLI-009`). A tag that happens to exist in the
registry does not make an environment, and cairn will not create one to satisfy a command:
`assign-tag` and `retire` both refuse a name that is not in the declared list. The
alternative — auto-vivification — turns a typo into a silent new environment, which is the
failure mode this rule exists to prevent. Whether the *pointer itself* already exists is a
separate, non-fatal question `assign-tag` answers by creating or moving it and reporting
which (`ADR-050`) — it is no longer a reason to refuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from . import registry
from .config import BuildConfig, Manifest
from .errors import RegistryError, UnknownEnvironmentError
from .images import INPUT_HASH_LABEL
from .registry import ImageRef, RemoteImage

#: The environment whose pointer may never move without explicit confirmation (BR-CLI-010).
PRODUCTION = "production"


class Selector(Enum):
    """How the caller chose the image an environment should point at (`BR-CLI-004`)."""

    LATEST = "latest"
    PREVIOUS = "previous"
    IDENTIFIER = "id"
    FROM_ENV = "from"


@dataclass(frozen=True)
class Environment:
    """One declared environment: its name, and the registry tag that is its pointer."""

    name: str
    tag: str
    ref: ImageRef

    @property
    def is_production(self) -> bool:
        """Whether moving this pointer requires explicit confirmation (BR-CLI-010).

        Matched on the environment's **name**, not its tag: the name is what the operator
        typed and what the confirmation will quote back, and a tag is free to be spelled
        however a registry's conventions require.
        """
        return self.name.lower() == PRODUCTION


@dataclass(frozen=True)
class Move:
    """A decided pointer move, before anything is written (`BR-CLI-011`'s ``--dry-run``)."""

    environment: Environment
    source: RemoteImage
    previous_digest: str | None

    @property
    def is_noop(self) -> bool:
        """Whether the pointer already resolves to the chosen image.

        Worth naming rather than performing: a retag that changes nothing still writes a
        manifest, and reporting "already there" tells the operator something a cheerful
        success message would hide.
        """
        return self.previous_digest == self.source.digest

    def render(self) -> str:
        lines = [
            f"environment  {self.environment.name}",
            f"tag          {self.environment.ref}",
            f"image        {self.source.ref}",
            f"digest       {self.source.digest}",
        ]
        if input_hash := self.source.labels.get(INPUT_HASH_LABEL):
            lines.append(f"input hash   {input_hash}")
        if self.previous_digest is None:
            lines.append("currently    (the tag does not exist yet)")
        elif self.is_noop:
            lines.append("currently    the same image — this would change nothing")
        else:
            lines.append(f"currently    {self.previous_digest}")
        return "\n".join(lines)


def declared(manifest: Manifest, build_config: BuildConfig) -> dict[str, Environment]:
    """Return every declared environment, keyed by name (`BR-DEPLOY-009a`)."""
    base = build_config.resolve_image_base(manifest.image_name)
    return {
        name: Environment(name=name, tag=tag, ref=registry.parse_ref(f"{base}:{tag}"))
        for name, tag in manifest.declared_environments.items()
    }


def require(manifest: Manifest, build_config: BuildConfig, name: str) -> Environment:
    """Return the declared environment *name*, or raise (`BR-CLI-009`)."""
    known = declared(manifest, build_config)
    if name in known:
        return known[name]
    raise UnknownEnvironmentError(_no_such(name, known))


def action(move: Move) -> str:
    """Whether ``assign-tag`` creates this pointer or moves it (`ADR-050`).

    Existence has two levels and only the manifest's is authoritative for *whether an
    environment exists*: `require` has already established that the name is declared. What
    this decides is whether the pointer has ever been **materialized** in the registry — and
    unlike the old `new-tag`/`retag` split, that fact is no longer a reason to refuse.
    `assign-tag` always proceeds; this only decides what it reports having done.
    """
    return "created" if move.previous_digest is None else "moved"


def plan_move(
    environment: Environment,
    *,
    selector: Selector,
    identifier: str | None = None,
    source_environment: Environment | None = None,
    candidates: list[RemoteImage] | None = None,
) -> Move:
    """Decide which image *environment* should point at, reading the registry but writing nothing.

    Separated from :func:`apply` so ``--dry-run`` and the production confirmation both act on
    a fully decided move (`BR-CLI-011`): the operator is shown the digest that *will* be
    deployed, not the selector that will later choose one.
    """
    source = _resolve_source(
        environment,
        selector=selector,
        identifier=identifier,
        source_environment=source_environment,
        candidates=candidates,
    )
    return Move(
        environment=environment,
        source=source,
        previous_digest=_current_digest(environment),
    )


def apply(move: Move) -> str:
    """Write the pointer, server-side, and return the digest now under it (`BR-DEPLOY-004`)."""
    return registry.retag(move.source.ref, move.environment.tag)


def retire(manifest: Manifest, build_config: BuildConfig, name: str) -> Environment:
    """Confirm *name* may be retired, returning it (`BR-CLI-009`).

    cairn removes nothing here. Retirement is the operator deleting the entry from
    ``[cairn.declared_environments]``; this validates that the entry exists and hands back
    what the caller must warn about — because **the registry tag persists**. GHCR has no per-tag
    delete, and deleting the underlying version would destroy an image other environments
    may still point at.
    """
    return require(manifest, build_config, name)


def history(environment: Environment, images: list[RemoteImage]) -> list[RemoteImage]:
    """Return *images* newest-first, excluding whatever the pointer resolves to now.

    This is what ``--previous`` selects from: the candidate list for a rollback is "images
    that are not the one running", which is a different question from "images older than
    the current one" — a pointer may already have been rolled back.
    """
    current = _current_digest(environment)
    return [image for image in images if image.digest != current]


# --- selectors (BR-CLI-004) -------------------------------------------------


def _resolve_source(
    environment: Environment,
    *,
    selector: Selector,
    identifier: str | None,
    source_environment: Environment | None,
    candidates: list[RemoteImage] | None,
) -> RemoteImage:
    if selector is Selector.IDENTIFIER:
        # Both of these are cairn calling itself wrongly, not operator error — the CLI
        # enforces that exactly one selector arrives with its argument. Raising a plain
        # ValueError is deliberate: it surfaces as an internal error, which is what it is.
        if not identifier:
            raise ValueError("Selector.IDENTIFIER requires an identifier")
        return registry.inspect(environment.ref.with_tag(identifier))

    if selector is Selector.FROM_ENV:
        if source_environment is None:
            raise ValueError("Selector.FROM_ENV requires a source environment")
        return registry.inspect(source_environment.ref)

    ordered = candidates or []
    if selector is Selector.LATEST:
        if not ordered:
            raise RegistryError(
                f"No images cairn built were found in {environment.ref.base}, so there is "
                f"nothing to point '{environment.name}' at. Run `cairn build --push` first."
            )
        return ordered[0]

    remaining = history(environment, ordered)
    if not remaining:
        raise RegistryError(
            f"No earlier image was found in {environment.ref.base} to roll "
            f"'{environment.name}' back to. `cairn images` lists what the registry holds."
        )
    return remaining[0]


def _current_digest(environment: Environment) -> str | None:
    """What the environment's tag resolves to now, or ``None`` if it does not exist yet."""
    try:
        return registry.digest_of(environment.ref)
    except RegistryError:
        # A tag that is not there is the normal state before the first deploy, and is not a
        # failure — it is precisely what `assign-tag` creates.
        return None


def _no_such(name: str, known: dict[str, Environment]) -> str:
    """The message for an undeclared environment, listing what does exist (`BR-CLI-015`)."""
    if not known:
        return (
            f"No such environment '{name}' — the manifest declares none. Add a "
            f"[cairn.declared_environments] table naming each environment and the registry "
            f"tag it watches."
        )
    available = ", ".join(sorted(known))
    return f"No such environment '{name}'. Declared environments are: {available}."
