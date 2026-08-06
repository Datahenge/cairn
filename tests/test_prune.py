"""Tests for build-machine pruning (BR-CLI-018, `ADR-032`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from cairn import images, prune
from cairn.images import ImageGroup, LocalImage

OWNED = "ghcr.io/x/y:cairn-build-owned"


def _image(short, tags=(), *, input_hash="aaa111", minutes_old=0, size=2_750_000_000, cairn=True):
    labels = {images.INPUT_HASH_LABEL: input_hash} if cairn else {}
    return LocalImage(
        image_id="sha256:" + short + "0" * (64 - len(short)),
        tags=tuple(tags),
        created=datetime.now(UTC) - timedelta(minutes=minutes_old),
        size=size,
        labels=labels,
    )


def _group(*members, input_hash="aaa111"):
    return ImageGroup(input_hash=input_hash, images=tuple(members))


# --- restriction 3: keep the newest N per input hash ------------------------


@pytest.mark.parametrize(
    ("keep", "expected_removals", "expected_kept"),
    [
        (1, ["bbb000000000", "ccc000000000"], ["aaa000000000"]),
        # keep=2 leaves rollback headroom: one older build stays available to roll back to.
        (2, ["ccc000000000"], ["aaa000000000", "bbb000000000"]),
    ],
    ids=["keep-1", "keep-2"],
)
def test_keep_n_leaves_the_n_newest(keep, expected_removals, expected_kept):
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", minutes_old=2),
        _image("ccc", minutes_old=5),
    )
    plan = prune.select([group], keep=keep)

    assert [image.short_id for image in plan.removals] == expected_removals
    assert [image.short_id for image in plan.kept] == expected_kept
    assert plan.reclaimable == len(expected_removals) * 2_750_000_000


def test_keep_is_per_input_hash_not_global():
    """Images under different hashes are different images, not each other's history."""
    first = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", minutes_old=2),
        input_hash="aaa111",
    )
    second = _group(
        _image("ccc", ["ghcr.io/x/y:v16-ddd222"], input_hash="ddd222"),
        _image("ddd", minutes_old=4, input_hash="ddd222"),
        input_hash="ddd222",
    )
    plan = prune.select([first, second], keep=1)

    assert sorted(image.short_id for image in plan.removals) == [
        "bbb000000000",
        "ddd000000000",
    ]


def test_a_single_image_group_is_never_touched():
    plan = prune.select([_group(_image("aaa", ["ghcr.io/x/y:latest"]))], keep=1)

    assert plan.is_empty


def test_keep_below_one_is_rejected():
    """Keeping nothing would delete the image the manifest currently describes."""
    with pytest.raises(ValueError):
        prune.select([_group(_image("aaa"))], keep=0)


# --- restriction 2: never remove something still named ----------------------


def test_a_tagged_image_is_protected_even_when_beyond_keep():
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", ["ghcr.io/x/y:someone-elses-tag"], minutes_old=2),
        _image("ccc", minutes_old=5),
    )
    plan = prune.select([group], keep=1)

    assert [image.short_id for image in plan.removals] == ["ccc000000000"]
    assert [image.short_id for image in plan.protected] == ["bbb000000000"]


def test_protected_images_are_reported_not_silently_skipped():
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", ["ghcr.io/x/y:other"], minutes_old=2),
        _image("ccc", minutes_old=5),
    )
    rendered = prune.render(prune.select([group], keep=1), others=0)

    assert "1 older image(s) have already been pushed" in rendered


# --- restriction 2 revised: owned vs. shared (BR-BUILD-018, ADR-061) --------


def test_a_stale_but_still_owned_image_is_now_eligible():
    """Never pushed anywhere is not the same as safe to keep forever."""
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", ["ghcr.io/x/y:v16-bbb222", OWNED], minutes_old=5, input_hash="bbb222"),
    )
    plan = prune.select([group], keep=1)

    assert [image.short_id for image in plan.removals] == ["bbb000000000"]


def test_a_pushed_image_is_protected_even_if_it_once_carried_the_marker():
    """The marker is stripped on push; what remains is a real tag, and real tags protect."""
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", ["ghcr.io/x/y:v16-bbb222"], minutes_old=5, input_hash="bbb222"),
    )
    plan = prune.select([group], keep=1)

    assert plan.is_empty
    assert [image.short_id for image in plan.protected] == ["bbb000000000"]


def test_an_orphan_within_keep_is_still_grace_windowed_by_position():
    """`keep` counts positions in the group regardless of tag status — see
    test_keep_n_leaves_the_n_newest's keep=2 case for the untagged member this mirrors."""
    group = _group(
        _image("aaa", ["ghcr.io/x/y:v16-aaa111"]),
        _image("bbb", [], minutes_old=1),  # already lost every tag, including any marker
    )
    plan = prune.select([group], keep=2)

    assert plan.is_empty


# --- restriction 1: the build cache is out of reach -------------------------


def test_a_build_cache_stage_never_reaches_the_plan(monkeypatch):
    """The whole safety property: labels land at the final commit, so a stage lacks them.

    Modelled on the real machine — a 4.63 GB untagged `builder` stage sitting beside
    2.75 GB final builds. A prune written against danglingness would take it and make
    every later build cold; scoping to cairn's labels cannot reach it.
    """
    records = [
        {
            "Id": "sha256:" + "aaa" + "0" * 61,
            "RepoTags": ["ghcr.io/x/y:v16-aaa111"],
            "Created": "2026-07-25T15:28:53Z",
            "Size": 2_750_000_000,
            "Config": {"Labels": {images.INPUT_HASH_LABEL: "aaa111"}},
        },
        {  # the builder stage: untagged, larger, unlabelled
            "Id": "sha256:" + "e03" + "0" * 61,
            "RepoTags": [],
            "Created": "2026-07-25T15:20:00Z",
            "Size": 4_630_000_000,
            "Config": {"Labels": {}},
        },
    ]
    monkeypatch.setattr(images, "_list_ids", lambda engine: [r["Id"] for r in records])
    monkeypatch.setattr(images, "_inspect", lambda engine, ids: records)

    found, others = images.inspect_local("podman")
    plan = prune.select(images.group(found), keep=1)

    assert others == 1
    assert plan.is_empty
    assert all("e03" not in image.short_id for image in plan.removals)


def test_the_report_explains_what_is_being_left_alone():
    """The 4.63 GB builder stage disappearing from a listing must not look like an oversight."""
    group = _group(_image("aaa", ["ghcr.io/x/y:v16-aaa111"]), _image("bbb", minutes_old=2))
    rendered = prune.render(prune.select([group], keep=1), others=5)

    assert "5 image(s) cairn did not build are never considered" in rendered
    assert "build-cache" in rendered


def test_empty_plan_still_explains_itself():
    rendered = prune.render(prune.select([_group(_image("aaa", ["x:y"]))], keep=1), others=5)

    assert "Nothing to remove" in rendered
    assert "never considered" in rendered


# --- removal (BR-CLI-018) ---------------------------------------------------


@pytest.fixture
def capturing_run(monkeypatch):
    """A `subprocess.run` stub that always succeeds and records every command issued."""
    seen: list[list[str]] = []

    def _run(command, **kwargs):
        seen.append(command)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(prune.subprocess, "run", _run)
    return seen


def test_removal_never_forces(capturing_run):
    """A removal that needs forcing is one to report, not perform."""
    prune.remove("podman", (_image("aaa"), _image("bbb")))

    assert all("--force" not in command and "-f" not in command for command in capturing_run)
    assert [command[:3] for command in capturing_run] == [["podman", "image", "rm"]] * 2


def test_one_failure_does_not_abort_the_rest(monkeypatch):
    def _run(command, **kwargs):
        if command[-1].startswith("sha256:aaa"):
            return type("R", (), {"returncode": 1, "stdout": "", "stderr": "image is in use\n"})()
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(prune.subprocess, "run", _run)
    removed, failures = prune.remove("podman", (_image("aaa"), _image("bbb")))

    assert [image.short_id for image in removed] == ["bbb000000000"]
    assert failures == ["aaa000000000: image is in use"]


def test_volumes_and_containers_are_never_named(capturing_run):
    prune.remove("podman", (_image("aaa"),))

    flattened = " ".join(" ".join(command) for command in capturing_run)
    assert "volume" not in flattened
    assert "container" not in flattened
    assert "system" not in flattened


# --- removing a still-owned, multiply-tagged image (BR-BUILD-018, ADR-061) --


def test_a_multiply_tagged_image_is_removed_tag_by_tag(capturing_run):
    """Engines refuse `image rm <id>` on a multiply-tagged image without --force; removing
    each reference individually avoids ever needing it."""
    doomed = _image("aaa", [f"ghcr.io/x/y:v16-{'a' * 12}", "ghcr.io/x/y:latest", OWNED])

    removed, failures = prune.remove("podman", (doomed,))

    assert failures == []
    assert [image.short_id for image in removed] == ["aaa000000000"]
    assert [command[-1] for command in capturing_run] == [
        f"ghcr.io/x/y:v16-{'a' * 12}",
        "ghcr.io/x/y:latest",
        OWNED,
    ]


def test_a_failure_partway_through_a_multi_tag_removal_stops_that_image(monkeypatch):
    """The remaining tags are left alone rather than force-removed — a later prune finishes
    the job once whatever is blocking the middle tag clears."""
    calls: list[str] = []

    def _run(command, **kwargs):
        calls.append(command[-1])
        ok = command[-1] != "ghcr.io/x/y:latest"
        return type("R", (), {"returncode": 0 if ok else 1, "stdout": "", "stderr": "busy\n"})()

    monkeypatch.setattr(prune.subprocess, "run", _run)
    doomed = _image("aaa", [f"ghcr.io/x/y:v16-{'a' * 12}", "ghcr.io/x/y:latest", OWNED])

    removed, failures = prune.remove("podman", (doomed,))

    assert removed == []
    assert failures == ["aaa000000000: busy"]
    # stopped at the failing tag rather than continuing on to the marker
    assert calls == [f"ghcr.io/x/y:v16-{'a' * 12}", "ghcr.io/x/y:latest"]
