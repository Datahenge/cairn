"""Tests for the back-off after a failed converge (BR-DEPLOY-027, ADR-083)."""

from __future__ import annotations

from cairn import backoff

DIGEST = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64
T0 = 1_800_000_000.0


def test_nothing_remembered_means_no_wait():
    assert backoff.waiting(DIGEST, now=T0) is None


def test_the_schedule_is_1_5_15_then_60_minutes():
    """BR-DEPLOY-027: each further failure of one digest waits longer, up to an hour."""
    waits = []
    for attempt in range(6):
        failure = backoff.record(DIGEST, "migrate failed", now=T0 + attempt)
        waits.append((failure.retry_at - failure.failed_at) / 60)

    assert waits == [1, 5, 15, 60, 60, 60]


def test_the_same_digest_waits_until_its_time():
    backoff.record(DIGEST, "migrate failed", now=T0)

    assert backoff.waiting(DIGEST, now=T0 + 59) is not None
    assert backoff.waiting(DIGEST, now=T0 + 60) is None


def test_a_different_digest_never_waits():
    """Pushing a fix is the operator's answer, and it goes ahead at once."""
    backoff.record(DIGEST, "migrate failed", now=T0)

    assert backoff.waiting(OTHER, now=T0 + 1) is None


def test_a_different_digest_failing_starts_its_own_count():
    backoff.record(DIGEST, "migrate failed", now=T0)
    backoff.record(DIGEST, "migrate failed", now=T0)

    assert backoff.record(OTHER, "health timeout", now=T0).attempts == 1


def test_clear_forgets():
    backoff.record(DIGEST, "migrate failed", now=T0)

    backoff.clear()

    assert backoff.waiting(DIGEST, now=T0) is None


def test_an_unreadable_record_means_no_wait(tmp_path):
    """Best effort: a damaged record must never stop a deploy."""
    backoff.STATE_PATH.write_text("{not json", encoding="utf-8")

    assert backoff.read() is None
    assert backoff.waiting(DIGEST, now=T0) is None


def test_an_unwritable_location_never_raises(tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("", encoding="utf-8")

    failure = backoff.record(DIGEST, "x", now=T0, path=blocked / "failed-deploy")

    assert failure.attempts == 1


def test_the_waiting_message_says_what_failed_and_how_to_go_on():
    failure = backoff.record(DIGEST, "Failed while running bench migrate", now=T0)

    message = backoff.describe(failure)

    assert DIGEST in message
    assert "Failed while running bench migrate" in message
    assert "once" in message
    assert "--retry-now" in message
