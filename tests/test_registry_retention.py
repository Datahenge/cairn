"""Tests for the registry retention algorithm (`BR-REG-006`/`007`/`008`).

Structured like `test_prune.py` — the same three-part shape (`select` → `render` → act) exists
for the same reason: `--dry-run` must be able to stop after the report.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cairn import registry_retention as retention
from cairn.errors import RegistryError
from cairn.registry import ImageRef

BASE = ImageRef("localhost:5000", "erpnext-btu-v16", "")

NOW = datetime.now(UTC)


def _candidate(digest, tags, *, days_old=0, undated=False):
    created = None if undated else NOW - timedelta(days=days_old)
    return retention.Candidate(
        digest=f"sha256:{digest}" + "0" * (64 - len(digest)), tags=tuple(tags), created=created
    )


# --- tag-shape recognition (BR-REG-007) --------------------------------------


@pytest.mark.parametrize(
    "tag",
    ["v16-1b019793dc20", "erpnext_btu-aaaaaaaaaaaa", "16-0123456789ab"],
)
def test_content_hash_tags_are_recognized(tag):
    assert retention.CONTENT_HASH_TAG_RE.match(tag)


@pytest.mark.parametrize("tag", ["v16", "production", "staging", "latest", "dev"])
def test_plain_names_are_not_content_hash_tags(tag):
    assert not retention.CONTENT_HASH_TAG_RE.match(tag)


def test_a_candidate_with_any_non_hash_tag_is_protected():
    candidate = _candidate("aaa", ["v16-aaaaaaaaaaaa", "production"])
    assert candidate.is_protected


def test_a_candidate_with_only_hash_tags_is_not_protected():
    candidate = _candidate("aaa", ["v16-aaaaaaaaaaaa"])
    assert not candidate.is_protected


# --- select(): the floor (rollback headroom) ---------------------------------


def test_the_floor_keeps_the_newest_n_regardless_of_age():
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=200),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=1),
    ]

    plan = retention.select(items, keep_last=2, max_age_days=30)

    assert plan.is_empty
    assert {c.digest for c in plan.kept_by_floor} == {items[0].digest, items[1].digest}


def test_beyond_the_floor_and_beyond_max_age_is_deleted():
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=2),
        _candidate("c", ["v16-cccccccccccc"], days_old=200),
    ]

    plan = retention.select(items, keep_last=2, max_age_days=30)

    assert [c.digest for c in plan.deletions] == [items[2].digest]
    assert {c.digest for c in plan.kept_by_floor} == {items[0].digest, items[1].digest}


def test_beyond_the_floor_but_within_max_age_is_kept():
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=2),
        _candidate("c", ["v16-cccccccccccc"], days_old=5),
    ]

    plan = retention.select(items, keep_last=2, max_age_days=30)

    assert plan.is_empty
    assert [c.digest for c in plan.kept_by_age] == [items[2].digest]


def test_keep_last_below_one_is_rejected():
    with pytest.raises(ValueError):
        retention.select([_candidate("a", ["v16-aaaaaaaaaaaa"])], keep_last=0, max_age_days=30)


# --- select(): protection by tag shape (BR-REG-006/007) ----------------------


def test_an_environment_tagged_digest_is_never_deleted_however_old():
    """The core safety property: no `[cairn.environments]` was ever read to know this."""
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb", "production"], days_old=400),
    ]

    plan = retention.select(items, keep_last=1, max_age_days=30)

    assert plan.deletions == ()
    assert [c.digest for c in plan.protected] == [items[1].digest]


def test_the_moving_series_tag_is_never_deleted_however_old():
    items = [_candidate("a", ["v16-aaaaaaaaaaaa", "v16"], days_old=400)]

    plan = retention.select(items, keep_last=1, max_age_days=30)

    assert plan.is_empty
    assert [c.digest for c in plan.protected] == [items[0].digest]


def test_protected_digests_never_count_toward_the_floor():
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa", "production"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=400),
    ]

    plan = retention.select(items, keep_last=1, max_age_days=30)

    # b is the only eligible candidate, so it fills the floor by itself despite its age.
    assert plan.is_empty
    assert [c.digest for c in plan.kept_by_floor] == [items[1].digest]


# --- select(): an undated candidate is never deleted --------------------------


def test_an_undated_candidate_is_never_deleted():
    """cairn cannot verify how old it is, so the safe default is to keep it."""
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=2),
        _candidate("c", ["v16-cccccccccccc"], undated=True),
    ]

    plan = retention.select(items, keep_last=2, max_age_days=30)

    assert plan.deletions == ()
    assert [c.digest for c in plan.kept_by_age] == [items[2].digest]


def test_undated_candidates_rank_last_not_first():
    """An undated candidate must not be mistaken for the newest and fill the floor."""
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], undated=True),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=1),
    ]

    plan = retention.select(items, keep_last=1, max_age_days=30)

    assert [c.digest for c in plan.kept_by_floor] == [items[1].digest]


# --- render() ------------------------------------------------------------


def test_render_of_an_empty_plan_says_so():
    plan = retention.select([_candidate("a", ["v16-aaaaaaaaaaaa"])], keep_last=1, max_age_days=30)

    assert "Nothing to delete" in retention.render(plan)


def test_render_names_every_deletion():
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=200),
    ]
    plan = retention.select(items, keep_last=1, max_age_days=30)

    rendered = retention.render(plan)

    assert "Will delete 1 digest(s)" in rendered
    assert items[1].short_digest in rendered


def test_render_reports_protection_count():
    items = [_candidate("a", ["v16-aaaaaaaaaaaa", "production"], days_old=400)]
    plan = retention.select(items, keep_last=1, max_age_days=30)

    rendered = retention.render(plan)

    assert "1 digest(s) carry a moving or environment tag" in rendered


# --- delete() --------------------------------------------------------------


def test_delete_calls_delete_digest_for_every_deletion(monkeypatch):
    calls = []
    monkeypatch.setattr(retention, "delete_digest", lambda base, digest: calls.append(digest))
    items = [
        _candidate("a", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("b", ["v16-bbbbbbbbbbbb"], days_old=200),
    ]
    plan = retention.select(items, keep_last=1, max_age_days=30)

    deleted, failures = retention.delete(BASE, plan)

    assert calls == [items[1].digest]
    assert [c.digest for c in deleted] == [items[1].digest]
    assert failures == []


def test_one_deletion_failure_does_not_abort_the_rest(monkeypatch):
    def _delete(base, digest):
        if digest.startswith("sha256:aaa"):
            raise RegistryError("in use")

    monkeypatch.setattr(retention, "delete_digest", _delete)
    items = [
        _candidate("newest", ["v16-aaaaaaaaaaaa"], days_old=1),
        _candidate("aaa", ["v16-bbbbbbbbbbbb"], days_old=200),
        _candidate("ccc", ["v16-cccccccccccc"], days_old=200),
    ]
    plan = retention.select(items, keep_last=1, max_age_days=30)

    deleted, failures = retention.delete(BASE, plan)

    assert {c.digest for c in deleted} == {items[2].digest}
    assert failures == [f"{items[1].short_digest}: in use"]


# --- candidates(): built entirely from the registry's own tag list -----------


def test_candidates_merges_tags_sharing_one_digest(monkeypatch):
    monkeypatch.setattr(retention, "tags", lambda base: ["v16-aaaaaaaaaaaa", "production"])
    monkeypatch.setattr(retention, "digest_of", lambda ref: "sha256:" + "a" * 64)
    monkeypatch.setattr(
        retention,
        "inspect",
        lambda ref: type("R", (), {"labels": {}})(),
    )

    found = retention.candidates(BASE)

    assert len(found) == 1
    assert found[0].tags == ("production", "v16-aaaaaaaaaaaa")


def test_candidates_skips_the_label_fetch_for_protected_digests(monkeypatch):
    """A digest carrying a plain tag needs no age — its age is never relevant."""
    inspected = []
    monkeypatch.setattr(retention, "tags", lambda base: ["production"])
    monkeypatch.setattr(retention, "digest_of", lambda ref: "sha256:" + "a" * 64)

    def _inspect(ref):
        inspected.append(ref)
        raise AssertionError("inspect() must not be called for a protected digest")

    monkeypatch.setattr(retention, "inspect", _inspect)

    found = retention.candidates(BASE)

    assert not inspected
    assert found[0].created is None
    assert found[0].is_protected


def test_candidates_reads_the_creation_label_for_eligible_digests(monkeypatch):
    monkeypatch.setattr(retention, "tags", lambda base: ["v16-aaaaaaaaaaaa"])
    monkeypatch.setattr(retention, "digest_of", lambda ref: "sha256:" + "a" * 64)
    monkeypatch.setattr(
        retention,
        "inspect",
        lambda ref: type("R", (), {"labels": {retention.CREATED_LABEL: "2026-01-15T10:00:00Z"}})(),
    )

    found = retention.candidates(BASE)

    assert found[0].created == datetime(2026, 1, 15, 10, 0, 0, tzinfo=UTC)


def test_a_failed_label_read_leaves_the_candidate_undated(monkeypatch):
    monkeypatch.setattr(retention, "tags", lambda base: ["v16-aaaaaaaaaaaa"])
    monkeypatch.setattr(retention, "digest_of", lambda ref: "sha256:" + "a" * 64)

    def _inspect(ref):
        raise RegistryError("not found")

    monkeypatch.setattr(retention, "inspect", _inspect)

    found = retention.candidates(BASE)

    assert found[0].created is None


# --- timestamp parsing --------------------------------------------------------


def test_created_label_parsing_matches_what_build_py_writes():
    assert retention._parse_created("2026-08-03T12:00:00Z") == datetime(
        2026, 8, 3, 12, 0, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("value", [None, "", "not-a-date", "2026-08-03"])
def test_unparseable_or_absent_labels_are_none(value):
    assert retention._parse_created(value) is None
