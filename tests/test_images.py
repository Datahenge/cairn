"""Tests for local image introspection (BR-CLI-005, `ADR-032`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from cairn import images
from cairn.errors import ImageQueryError

APPS = json.dumps(
    [
        {
            "name": "erpnext",
            "url": "https://github.com/frappe/erpnext",
            "ref": "version-16",
            "commit": "a5de60c3" + "0" * 32,
        },
        {
            "name": "btu",
            "url": "https://github.com/Datahenge/btu",
            "ref": "version-16",
            "commit": "5d66f6d4" + "0" * 32,
        },
    ]
)


def _inspection(image_id, tags, *, minutes_old=0, size=2_952_790_016, cairn=True):
    """One engine inspection record, shaped the way docker reports them."""
    labels = {}
    if cairn:
        labels = {
            images.INPUT_HASH_LABEL: "1bf0adf3823f",
            images.APPS_LABEL: APPS,
            images.FRAPPE_REF_LABEL: "version-16",
            images.FRAPPE_COMMIT_LABEL: "be4728af" + "0" * 32,
            images.PIN_REF_LABEL: "v3.2.1",
        }
    created = datetime.now(UTC) - timedelta(minutes=minutes_old)
    return {
        "Id": f"sha256:{image_id}",
        "RepoTags": list(tags),
        "Created": created.isoformat().replace("+00:00", "Z"),
        "Size": size,
        "Config": {"Labels": labels},
    }


def _load(monkeypatch, records):
    monkeypatch.setattr(images, "_list_ids", lambda engine: [r["Id"] for r in records])
    monkeypatch.setattr(images, "_inspect", lambda engine, ids: records)
    return images.inspect_local("podman")


# --- identifying cairn's own images (BR-CLI-005) ----------------------------


def test_only_labelled_images_are_cairns(monkeypatch):
    """Labels land at the final commit only, so this also excludes build-cache stages."""
    found, others = _load(
        monkeypatch,
        [
            _inspection("aaa" + "0" * 61, ["ghcr.io/x/y:v16-1bf0adf3823f"]),
            _inspection("bbb" + "0" * 61, [], cairn=False),  # a stage image, or unrelated
            _inspection("ccc" + "0" * 61, [], cairn=False),
        ],
    )

    assert [image.short_id for image in found] == ["aaa000000000"]
    assert others == 2


def test_uncounted_images_are_never_silently_hidden(monkeypatch):
    """A listing mistaken for a full inventory is worse than no listing."""
    _, others = _load(monkeypatch, [_inspection("aaa" + "0" * 61, [], cairn=False)])
    rendered = images.render([], others)

    assert "1 other image(s)" in rendered
    assert "must not be deleted" in rendered


# --- grouping by input hash (BR-CLI-005, BR-BUILD-014) ----------------------


def test_repeat_builds_group_under_one_input_hash(monkeypatch):
    """Several images under one hash *are* the duplication BR-BUILD-014 prevents."""
    found, _ = _load(
        monkeypatch,
        [
            _inspection("aaa" + "0" * 61, ["ghcr.io/x/y:v16-1bf0adf3823f", "ghcr.io/x/y:latest"]),
            _inspection("bbb" + "0" * 61, [], minutes_old=2),
            _inspection("ccc" + "0" * 61, [], minutes_old=5),
        ],
    )
    groups = images.group(found)

    assert len(groups) == 1
    assert groups[0].input_hash == "1bf0adf3823f"
    assert groups[0].newest.short_id == "aaa000000000"
    assert [image.short_id for image in groups[0].superseded] == ["bbb000000000", "ccc000000000"]


def test_reclaimable_counts_only_the_untagged(monkeypatch):
    found, _ = _load(
        monkeypatch,
        [
            _inspection("aaa" + "0" * 61, ["ghcr.io/x/y:latest"], size=100),
            _inspection("bbb" + "0" * 61, [], minutes_old=2, size=100),
        ],
    )

    assert images.group(found)[0].reclaimable == 100


def test_report_names_the_inputs_and_marks_supersession(monkeypatch):
    """The whole point: an untagged image explains why it exists."""
    found, others = _load(
        monkeypatch,
        [
            _inspection("aaa" + "0" * 61, ["ghcr.io/x/y:v16-1bf0adf3823f"]),
            _inspection("bbb" + "0" * 61, [], minutes_old=2),
        ],
    )
    rendered = images.render(images.group(found), others)

    assert "input hash 1bf0adf3823f" in rendered
    assert "erpnext" in rendered and "a5de60c3" in rendered
    assert "btu" in rendered and "5d66f6d4" in rendered
    assert "frappe_docker v3.2.1" in rendered
    assert "superseded" in rendered


def test_json_output_is_machine_readable(monkeypatch):
    found, others = _load(
        monkeypatch,
        [
            _inspection("aaa" + "0" * 61, ["ghcr.io/x/y:latest"]),
            _inspection("bbb" + "0" * 61, [], minutes_old=2),
        ],
    )
    payload = json.loads(images.as_json(images.group(found), others))

    assert payload["other_images"] == 0
    assert len(payload["groups"][0]["images"]) == 2
    assert [image["superseded"] for image in payload["groups"][0]["images"]] == [False, True]


# --- engine differences (ADR-027) -------------------------------------------


def test_podman_style_top_level_labels_are_read():
    """podman reports labels at the top level; docker nests them under Config."""
    record = {
        "Id": "sha256:" + "a" * 64,
        "RepoTags": [],
        "Created": "2026-07-25T15:28:53.123456789Z",
        "Size": 10,
        "Labels": {images.INPUT_HASH_LABEL: "abc123abc123"},
    }

    assert images._from_inspection(record).input_hash == "abc123abc123"


@pytest.mark.parametrize(
    "value",
    [
        "2026-07-25T15:28:53Z",
        "2026-07-25T15:28:53.123456789Z",  # nanoseconds: fromisoformat rejects these
        "2026-07-25T15:28:53.123456+00:00",
        1784000000,
    ],
)
def test_engine_timestamps_are_parsed(value):
    assert images._parse_timestamp(value) is not None


def test_unparseable_timestamp_degrades_rather_than_failing():
    """An unreadable date must not cost the whole listing."""
    assert images._parse_timestamp("not a date") is None
    assert images.format_age(None) == "?"


def test_undated_images_sort_last_rather_than_vanishing(monkeypatch):
    records = [_inspection("aaa" + "0" * 61, [])]
    records[0]["Created"] = "unparseable"
    records.append(_inspection("bbb" + "0" * 61, [], minutes_old=5))
    found, _ = _load(monkeypatch, records)

    assert [image.short_id for image in found] == ["bbb000000000", "aaa000000000"]


def test_malformed_apps_label_does_not_crash_the_report():
    record = {
        "Id": "sha256:" + "a" * 64,
        "RepoTags": [],
        "Created": "2026-07-25T15:28:53Z",
        "Size": 10,
        "Config": {"Labels": {images.INPUT_HASH_LABEL: "abc", images.APPS_LABEL: "{not json"}},
    }

    assert images._from_inspection(record).apps == []


def test_engine_failure_is_reported_not_swallowed(monkeypatch):
    def _fail(command):
        raise ImageQueryError("engine unavailable")

    monkeypatch.setattr(images, "_run", _fail)

    with pytest.raises(ImageQueryError):
        images.inspect_local("podman")


def test_sizes_render_in_the_units_the_engine_uses():
    """Decimal, not binary: this listing is read next to `podman image list`.

    The bug this pins: 2.75 GB of image reported as 2.56 GB, because the divisor was 1024.
    """
    assert images.format_size(2_750_000_000) == "2.75 GB"
    assert images.format_size(4_630_000_000) == "4.63 GB"
    assert images.format_size(443_000_000) == "443 MB"
    assert images.format_size(4_700_000) == "4.7 MB"
    assert images.format_size(512) == "512 B"
