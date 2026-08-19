"""The maintenance hold — "deliberately not running" (`BR-DEPLOY-024`, `ADR-073`).

Before this existed, cairn's state model had exactly two values: converged, and broken.
``State.is_converged`` requires ``stack_up``, so a stack an operator had deliberately taken
down was indistinguishable from a host that had died — and the reconcile timer treated it
accordingly, pulling, starting and migrating it back within the poll interval. The hold is the
third value, and it is what makes a ``stop`` verb mean anything.

**Durable on purpose.** It lives under ``/etc/cairn``, not ``/run`` beside the deploy lock: a
host that reboots mid-maintenance must stay down, or "down" does not mean down. The price is
that a forgotten hold freezes deploys indefinitely with no natural expiry, which is why
``doctor`` reporting a live hold on every run is a requirement of the decision rather than a
convenience (`BR-CLI-020`).

The file's *presence* is the whole signal. Its contents are advisory — a timestamp and an
optional reason, for a human reading it later — and are never parsed for meaning.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

#: Durable by design; see the module docstring.
HOLD_PATH = Path("/etc/cairn/hold")


def _target(path: Path | None) -> Path:
    return path or HOLD_PATH


def is_held(path: Path | None = None) -> bool:
    """Whether a hold is in place (`BR-DEPLOY-024`).

    Presence only. A hold whose contents are unreadable or malformed is still a hold — the
    operator's intent was expressed by creating the file, and failing open on a parse error
    would resume deploys on a host somebody deliberately stopped.
    """
    try:
        return _target(path).is_file()
    except OSError:
        return False


def describe(path: Path | None = None) -> str | None:
    """The hold's own note, for reporting. None when there is no hold.

    Best-effort: an unreadable or empty hold still returns a usable line, because the caller
    is reporting *that the host is held*, and the note is decoration on that fact.
    """
    target = _target(path)
    if not is_held(path):
        return None
    try:
        note = target.read_text(encoding="utf-8").strip()
    except OSError:
        note = ""
    return note or "held (no detail recorded)"


def place(reason: str | None = None, path: Path | None = None) -> None:
    """Create the hold, recording when and why (`BR-DEPLOY-024`).

    Writing is not conditional on absence: re-holding an already-held host refreshes the note
    and succeeds, because ``stop`` must be idempotent (`BR-CLI-029`).
    """
    target = _target(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
    detail = f" — {reason}" if reason else ""
    target.write_text(f"held {stamp}{detail}\n", encoding="utf-8")


def release(path: Path | None = None) -> bool:
    """Remove the hold, returning whether one was actually there.

    The return value matters to `restart`, which must say when it has cleared a hold somebody
    else placed — silently resuming a host another operator deliberately stopped is a surprise
    worth one line of output (`BR-CLI-029`).
    """
    target = _target(path)
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        return False
