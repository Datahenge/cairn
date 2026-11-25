"""Back-off after a failed converge (`BR-DEPLOY-027`, `ADR-083`).

A failed pass halts (`BR-DEPLOY-018`), but the environment tag still names the digest that
failed, so the next timer pass would try it again at once. This module remembers the failed
digest in ``/run`` and says when it may be tried again: 1, 5, 15, then every 60 minutes.

One record, overwritten each time. ``/run`` is tmpfs, so a reboot clears it. Every read and
write here is best effort: a record that cannot be read or written means no back-off, never
a failed pass.
"""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: Where the failed digest is remembered. ``/run`` is tmpfs, so a reboot starts afresh.
STATE_PATH = Path("/run/cairn/failed-deploy")

#: Minutes to wait after the first, second, third and every later failure of one digest.
SCHEDULE_MINUTES = (1, 5, 15, 60)


@dataclass(frozen=True)
class Failure:
    """The digest that last failed to converge, and how often it has."""

    digest: str
    failed_at: float
    attempts: int
    error: str

    @property
    def retry_at(self) -> float:
        minutes = SCHEDULE_MINUTES[min(self.attempts, len(SCHEDULE_MINUTES)) - 1]
        return self.failed_at + minutes * 60


def read(path: Path | None = None) -> Failure | None:
    """The remembered failure, or None when there is none or it cannot be read."""
    try:
        data = json.loads((path or STATE_PATH).read_text(encoding="utf-8"))
        return Failure(
            digest=str(data["digest"]),
            failed_at=float(data["failed_at"]),
            attempts=max(1, int(data["attempts"])),
            error=str(data.get("error", "")),
        )
    except (OSError, ValueError, KeyError, TypeError):
        return None


def record(
    digest: str, error: str, *, now: float | None = None, path: Path | None = None
) -> Failure:
    """Remember that *digest* failed, counting on from an earlier failure of the same digest."""
    previous = read(path)
    attempts = previous.attempts + 1 if previous and previous.digest == digest else 1
    failure = Failure(
        digest=digest,
        failed_at=time.time() if now is None else now,
        attempts=attempts,
        error=error,
    )
    target = path or STATE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "digest": failure.digest,
                    "failed_at": failure.failed_at,
                    "attempts": failure.attempts,
                    "error": failure.error,
                }
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return failure


def clear(path: Path | None = None) -> None:
    """Forget any remembered failure."""
    with contextlib.suppress(OSError):
        (path or STATE_PATH).unlink(missing_ok=True)


def waiting(digest: str, *, now: float | None = None, path: Path | None = None) -> Failure | None:
    """The failure *digest* is still waiting out, or None if it may be tried now."""
    failure = read(path)
    if failure is None or failure.digest != digest:
        return None
    current = time.time() if now is None else now
    return failure if current < failure.retry_at else None


def describe(failure: Failure) -> str:
    """What a waiting pass reports: the failure, the count, and when it will try again."""
    retry = datetime.fromtimestamp(failure.retry_at, tz=UTC).strftime("%H:%M:%S UTC")
    times = "once" if failure.attempts == 1 else f"{failure.attempts} times"
    reason = f": {failure.error}" if failure.error else ""
    return (
        f"Waiting — {failure.digest} failed to converge {times}{reason}. It will be tried "
        f"again after {retry}. Push a different image to deploy it now, or run "
        f"`cairn-adopt reconcile --retry-now` once the cause is fixed."
    )
