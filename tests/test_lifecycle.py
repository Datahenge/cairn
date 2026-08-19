"""Tests for the maintenance hold and the lifecycle verbs (BR-DEPLOY-024, BR-CLI-029)."""

from __future__ import annotations

import pytest

from cairn import descriptor, hold, lifecycle, reconcile


def _descriptor(**overrides):
    values = {
        "environment": "production",
        "registry_host": "ghcr.io",
        "image": "datahenge/erpnext-btu-v16",
        "tag": "production",
        "site": "erp.example.com",
    }
    values.update(overrides)
    return descriptor.Descriptor(**values)


@pytest.fixture
def held_at(tmp_path, monkeypatch):
    """Point the hold at a temp file, so no test touches /etc/cairn."""
    path = tmp_path / "hold"
    monkeypatch.setattr(hold, "HOLD_PATH", path)
    return path


@pytest.fixture
def stack(monkeypatch):
    """Record compose calls and neutralise the lock and the reconcile pass."""
    calls: list[list[str]] = []
    monkeypatch.setattr(
        reconcile, "compose_run", lambda desc, args, timeout, what: calls.append(args)
    )
    monkeypatch.setattr(
        reconcile,
        "run_locked",
        lambda desc, **kw: reconcile.Outcome(True, True, None, "Converged.", False),
    )
    return calls


# --- the hold itself (BR-DEPLOY-024) -----------------------------------------


def test_a_hold_is_its_presence_not_its_contents(held_at) -> None:
    """BR-DEPLOY-024: presence is the whole signal; contents are advisory.

    Failing open on an unreadable hold would resume deploys on a host somebody deliberately
    stopped, which is the one outcome the hold exists to prevent.
    """
    held_at.write_text("this is not parseable as anything\n")
    assert hold.is_held() is True
    assert hold.describe() is not None


def test_an_empty_hold_still_reports_something_useful(held_at) -> None:
    held_at.write_text("")
    assert "no detail" in hold.describe()


def test_placing_a_hold_twice_succeeds(held_at) -> None:
    """BR-CLI-029: `stop` is idempotent, so re-holding must not error."""
    hold.place("first")
    hold.place("second")
    assert "second" in held_at.read_text()


def test_release_reports_whether_there_was_one(held_at) -> None:
    """`restart` must say when it cleared somebody else's hold."""
    assert hold.release() is False
    hold.place()
    assert hold.release() is True
    assert not held_at.exists()


# --- reconcile honours the hold (BR-DEPLOY-024) ------------------------------


def test_reconcile_converges_nothing_while_held(held_at, monkeypatch) -> None:
    """BR-DEPLOY-024: held is a third outcome, neither converged nor failed."""
    hold.place("maintenance")

    def explode(*args, **kwargs):
        raise AssertionError("a held host must not inspect or converge")

    monkeypatch.setattr(reconcile, "inspect", explode)
    monkeypatch.setattr(reconcile, "run_locked", explode)

    outcome = reconcile.run(_descriptor())

    assert outcome.held is True
    assert outcome.converged is False
    assert outcome.changed is False


def test_reconcile_runs_normally_with_no_hold(held_at, monkeypatch) -> None:
    monkeypatch.setattr(
        reconcile,
        "run_locked",
        lambda desc, **kw: reconcile.Outcome(True, False, None, "Already running.", False),
    )
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)

    outcome = reconcile.run(_descriptor())

    assert outcome.held is False


# --- the verbs (BR-CLI-029) --------------------------------------------------


def test_stop_holds_before_it_stops(held_at, stack, monkeypatch) -> None:
    """BR-CLI-029: if the command dies between the steps, intent is already recorded."""
    order: list[str] = []
    monkeypatch.setattr(hold, "place", lambda reason=None, path=None: order.append("hold"))
    monkeypatch.setattr(
        reconcile, "compose_run", lambda desc, args, timeout, what: order.append("stop")
    )
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)

    lifecycle.stop(_descriptor())

    assert order == ["hold", "stop"]


def test_stop_keeps_containers_and_never_touches_volumes(held_at, stack, monkeypatch) -> None:
    """BR-DATA-005: `compose stop`, never `down` and never `-v`."""
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)
    lifecycle.stop(_descriptor())
    assert stack == [["stop"]]


def test_start_releases_the_hold_then_converges(held_at, stack, monkeypatch) -> None:
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)
    hold.place("maintenance")

    lifecycle.start(_descriptor())

    assert not held_at.exists()
    assert stack == []  # start carries no lifecycle logic of its own


def test_restart_clears_a_hold_and_leaves_none(held_at, stack, monkeypatch) -> None:
    """BR-CLI-029, Brian's two rules: clear what you find, set nothing of your own.

    A hold set for the interval would outlive a `restart` that crashed between down and up,
    freezing the host — the opposite of what the command means.
    """
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)
    hold.place("earlier maintenance")

    lifecycle.restart(_descriptor())

    assert not held_at.exists()
    assert stack == [["stop"]]


def test_restart_says_when_it_cleared_someone_elses_hold(held_at, stack, monkeypatch) -> None:
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)
    hold.place("someone else was here")
    said: list[str] = []

    lifecycle.restart(_descriptor(), report=said.append)

    assert any("hold" in line.lower() for line in said)


def test_restart_is_quiet_when_there_was_no_hold(held_at, stack, monkeypatch) -> None:
    monkeypatch.setattr(reconcile, "single_flight", _no_lock_cm)
    said: list[str] = []

    lifecycle.restart(_descriptor(), report=said.append)

    assert not any("cleared" in line.lower() for line in said)


# --- the deadlock hazard (BR-CLI-029) ----------------------------------------


@pytest.mark.parametrize("verb", [lifecycle.stop, lifecycle.start, lifecycle.restart])
def test_no_verb_reacquires_the_deploy_lock(held_at, stack, monkeypatch, verb) -> None:
    """BR-CLI-029: taking the lock twice in one process blocks against itself, forever.

    `reconcile.run` acquires the lock; `run_locked` does not. A verb that took the lock and
    then called `run` would hang with no output and no timeout — the worst possible failure
    for a command an operator reaches for when something is already wrong. Asserted by making
    a second acquisition fatal rather than by trusting the call sites to read correctly.
    """
    depth = {"n": 0}

    class _Once:
        def __enter__(self):
            depth["n"] += 1
            if depth["n"] > 1:
                raise AssertionError("the deploy lock was acquired twice in one command")
            return None

        def __exit__(self, *exc):
            depth["n"] -= 1
            return False

    monkeypatch.setattr(reconcile, "single_flight", lambda **kw: _Once())
    monkeypatch.setattr(reconcile, "_single_flight", lambda **kw: _Once())

    verb(_descriptor())


class _NoLock:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _no_lock(**kwargs):
    return _NoLock()


def _no_lock_cm(**kwargs):
    return _NoLock()
