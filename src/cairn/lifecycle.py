"""Target-stack lifecycle: `stop`, `start`, `restart` (`BR-CLI-029`, `ADR-073`).

The operator's answer to "I need this stack down for a moment." Before these existed the only
way to stop a cairn-managed stack was `docker compose` by hand, which `ADR-073` forbids — and
which the reconcile timer would undo within the poll interval anyway, `bench migrate` included.

Every verb here holds the deploy lock for its **whole** duration, so a timer firing mid-command
exits on the lock instead of interleaving with it. That is why they call
:func:`reconcile.run_locked` rather than :func:`reconcile.run`: the latter takes the lock
again, and a second ``flock`` on a fresh descriptor blocks against the process's own lock.
"""

from __future__ import annotations

from collections.abc import Callable

from . import hold, reconcile
from .descriptor import Descriptor

Report = Callable[[str], None]


def stop(
    descriptor: Descriptor,
    *,
    reason: str | None = None,
    report: Report = lambda message: None,
) -> str:
    """Hold this environment, then bring its containers down (`BR-CLI-029`).

    The hold is placed **first**. Ordering is belt-and-braces given the lock — a timer firing
    now exits on it either way — but it means that if this command dies between the two steps,
    it dies having recorded the operator's intent rather than having stopped a stack that the
    next pass would silently restart.

    ``compose stop``, not ``down``: containers are kept, and volumes are never touched
    (`BR-DATA-005`). Idempotent — stopping a stopped stack succeeds.
    """
    with reconcile.single_flight():
        hold.place(reason)
        report("Held — automatic convergence is suspended until `start`")
        reconcile.compose_run(
            descriptor, ["stop"], reconcile.COMPOSE_TIMEOUT_SECONDS, "stopping the stack"
        )
        return "Stopped. This host will not converge until you run `start`."


def start(descriptor: Descriptor, *, report: Report = lambda message: None) -> str:
    """Release the hold, then converge (`BR-CLI-029`).

    Deliberately carries no lifecycle logic of its own: a stopped stack is already
    not-converged, so the ordinary reconcile pass pulls, recreates, migrates and health-checks
    exactly as it should. Duplicating that here would create a second sequence to keep in step
    with the first.
    """
    with reconcile.single_flight():
        if hold.release():
            report("Hold released")
        outcome = reconcile.run_locked(descriptor, report=report)
        return outcome.detail


def restart(descriptor: Descriptor, *, report: Report = lambda message: None) -> str:
    """Stop and start as one command, clearing any hold and setting none (`BR-CLI-029`).

    Brian's two rules, 2026-08-19. Setting no hold of its own is the important half: a hold
    would outlive a `restart` that crashed between down and up, freezing the host — the exact
    opposite of what the command means. The lock, held across both steps, is what actually
    protects the interval.

    Clearing a hold is reported rather than silent, because resuming a host somebody else
    deliberately stopped should not be something they discover later.
    """
    with reconcile.single_flight():
        if hold.release():
            report("Cleared an existing hold — this host was deliberately stopped")
        reconcile.compose_run(
            descriptor, ["stop"], reconcile.COMPOSE_TIMEOUT_SECONDS, "stopping the stack"
        )
        outcome = reconcile.run_locked(descriptor, report=report)
        return outcome.detail
