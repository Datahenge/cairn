"""Tests for target-machine pruning (BR-CLI-028, `ADR-072`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cairn import adopt_prune
from cairn.images import LocalImage


def _image(short, tags=(), *, minutes_old=0, size=2_750_000_000):
    return LocalImage(
        image_id="sha256:" + short + "0" * (64 - len(short)),
        tags=tuple(tags),
        created=datetime.now(UTC) - timedelta(minutes=minutes_old),
        size=size,
        labels={},
    )


# --- the running image is protected unconditionally (BR-DEPLOY-003b) -------


def test_the_running_image_is_never_removed_regardless_of_position():
    """A rollback can leave the running image older than one already superseded — recency
    alone must never decide this, only the container's actual, current image."""
    running = _image("bbb", minutes_old=5)
    images = [_image("aaa"), running, _image("ccc", minutes_old=10)]

    plan = adopt_prune.select(images, running_image_id=running.image_id, keep=1)

    assert plan.running is running
    assert running not in plan.removals
    assert running not in plan.kept


def test_no_running_image_falls_back_to_plain_recency():
    images = [_image("aaa"), _image("bbb", minutes_old=5), _image("ccc", minutes_old=10)]

    plan = adopt_prune.select(images, running_image_id=None, keep=1)

    assert plan.running is None
    assert [image.short_id for image in plan.kept] == ["aaa000000000"]
    assert [image.short_id for image in plan.removals] == [
        "bbb000000000",
        "ccc000000000",
    ]


# --- the grace window, applied to everything but the running image ---------


def test_keep_counts_the_newest_of_the_rest():
    running = _image("aaa")
    images = [running, _image("bbb", minutes_old=2), _image("ccc", minutes_old=5)]

    plan = adopt_prune.select(images, running_image_id=running.image_id, keep=1)

    assert [image.short_id for image in plan.kept] == ["bbb000000000"]
    assert [image.short_id for image in plan.removals] == ["ccc000000000"]


def test_keep_below_one_is_rejected():
    with pytest.raises(ValueError):
        adopt_prune.select([_image("aaa")], running_image_id=None, keep=0)


def test_nothing_beyond_keep_means_an_empty_plan():
    running = _image("aaa")
    plan = adopt_prune.select([running], running_image_id=running.image_id, keep=1)

    assert plan.is_empty


# --- reporting (BR-CLI-011) -------------------------------------------------


def test_report_names_the_running_image_as_never_removed():
    running = _image("aaa")
    images = [running, _image("bbb", minutes_old=5)]

    rendered = adopt_prune.render(adopt_prune.select(images, running.image_id, keep=1), others=0)

    assert "Currently running" in rendered
    assert "Never removed" in rendered


def test_report_when_nothing_is_running():
    images = [_image("aaa"), _image("bbb", minutes_old=5)]

    rendered = adopt_prune.render(adopt_prune.select(images, None, keep=1), others=0)

    assert "Nothing is currently running" in rendered


def test_report_explains_other_images_are_never_considered():
    running = _image("aaa")
    rendered = adopt_prune.render(adopt_prune.select([running], running.image_id, keep=1), others=3)

    assert "3 other image(s)" in rendered
    assert "cairn-build" in rendered


def test_empty_plan_still_explains_itself():
    running = _image("aaa")
    rendered = adopt_prune.render(adopt_prune.select([running], running.image_id, keep=1), others=0)

    assert "Nothing to remove" in rendered
