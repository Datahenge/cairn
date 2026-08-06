"""Tests for local image introspection (BR-CLI-005, `ADR-032`)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from cairn import images, registry
from cairn.errors import ImageQueryError, RegistryError

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
            images.RECIPE_COMMIT_LABEL: "cafe1234" + "0" * 32,
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

    assert "ghcr.io/x/y:v16-1bf0adf3823f" in rendered
    assert "input hash 1bf0adf3823f" in rendered
    assert "erpnext" in rendered and "a5de60c3" in rendered
    assert "btu" in rendered and "5d66f6d4" in rendered
    assert "built from recipe cafe1234" in rendered
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


# --- the ownership marker (BR-BUILD-018, ADR-061) ----------------------------


def test_is_owned_detects_the_marker_tag(monkeypatch):
    found, _ = _load(
        monkeypatch,
        [
            _inspection(
                "aaa" + "0" * 61,
                [
                    "ghcr.io/x/y:v16-1bf0adf3823f",
                    "ghcr.io/x/y:latest",
                    "ghcr.io/x/y:cairn-build-owned",
                ],
            ),
            _inspection("bbb" + "0" * 61, ["ghcr.io/x/y:someone-elses-tag"], minutes_old=2),
        ],
    )

    assert [image.is_owned for image in found] == [True, False]


def test_group_header_prefers_the_primary_tag_over_the_owned_marker(monkeypatch):
    """Neither `latest` nor the owned marker is the name an operator recognizes."""
    found, _ = _load(
        monkeypatch,
        [
            _inspection(
                "aaa" + "0" * 61,
                ["ghcr.io/x/y:cairn-build-owned", "ghcr.io/x/y:v16-1bf0adf3823f"],
            )
        ],
    )
    rendered = images.render(images.group(found), 0)

    assert rendered.startswith("ghcr.io/x/y:v16-1bf0adf3823f")


def test_footer_reports_owned_count_and_explains_it(monkeypatch):
    found, others = _load(
        monkeypatch,
        [
            _inspection(
                "aaa" + "0" * 61,
                ["ghcr.io/x/y:v16-1bf0adf3823f", "ghcr.io/x/y:cairn-build-owned"],
            )
        ],
    )
    rendered = images.render(images.group(found), others)

    assert "1 carry the 'cairn-build-owned' tag" in rendered
    assert "not pushed anywhere yet" in rendered


def test_footer_says_nothing_about_ownership_when_nothing_is_owned(monkeypatch):
    found, others = _load(
        monkeypatch, [_inspection("aaa" + "0" * 61, ["ghcr.io/x/y:v16-1bf0adf3823f"])]
    )
    rendered = images.render(images.group(found), others)

    assert "cairn-build-owned" not in rendered


def test_json_reports_owned_status(monkeypatch):
    found, others = _load(
        monkeypatch,
        [
            _inspection(
                "aaa" + "0" * 61,
                ["ghcr.io/x/y:v16-1bf0adf3823f", "ghcr.io/x/y:cairn-build-owned"],
            ),
            _inspection("bbb" + "0" * 61, [], minutes_old=2),
        ],
    )
    payload = json.loads(images.as_json(images.group(found), others))

    assert [image["owned"] for image in payload["groups"][0]["images"]] == [True, False]


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


# --- the registry report (cairn-registry images, BR-REG-005, BR-DEPLOY-005) -


def _remote_image(digest, labels, size=2_750_000_000):
    return registry.RemoteImage(
        ref=registry.parse_ref(f"ghcr.io/datahenge/erpnext-btu-v16:{digest[:6]}"),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=size,
        labels=labels,
    )


def _cairn_labels(input_hash="aaa111", created="2026-07-25T10:00:00Z"):
    return {
        images.INPUT_HASH_LABEL: input_hash,
        images.FRAPPE_REF_LABEL: "v16.0.1",
        images.FRAPPE_COMMIT_LABEL: "a" * 40,
        images.CREATED_LABEL: created,
    }


def _stub_registry(monkeypatch, tags, answers):
    base = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:latest")
    monkeypatch.setattr(registry, "tags", lambda ref: tags)

    def _inspect(ref):
        answer = answers[ref.tag]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(registry, "inspect", _inspect)
    return base


def test_tags_pointing_at_one_image_are_folded_together(monkeypatch):
    """Several tags routinely name one image — its primary tag, its moving tag, and every
    environment running it. Reporting it three times would make "what runs this" unanswerable.
    """
    same = "sha256:" + "1" * 64
    base = _stub_registry(
        monkeypatch,
        ["v16.0.1-aaa111", "v16", "production"],
        {
            tag: _remote_image(same, _cairn_labels())
            for tag in ("v16.0.1-aaa111", "v16", "production")
        },
    )

    found, others = images.inspect_registry(base)

    assert len(found) == 1
    assert found[0].tags == ("production", "v16", "v16.0.1-aaa111")
    assert others == 0


def test_images_cairn_did_not_build_are_counted_not_listed(monkeypatch):
    """The same rule as the local report: excluded, but never silently, so the listing is not
    mistaken for a complete inventory."""
    base = _stub_registry(
        monkeypatch,
        ["v16", "someone-elses"],
        {
            "v16": _remote_image("sha256:" + "1" * 64, _cairn_labels()),
            "someone-elses": _remote_image("sha256:" + "2" * 64, {}),
        },
    )

    found, others = images.inspect_registry(base)

    assert [image.short_digest for image in found] == ["111111111111"]
    assert others == 1


def test_an_unreadable_tag_does_not_prevent_reporting_the_rest(monkeypatch):
    """A repository shared with another tool may hold manifests cairn has no business
    understanding, and one of them must not fail the whole report."""
    base = _stub_registry(
        monkeypatch,
        ["v16", "broken"],
        {
            "v16": _remote_image("sha256:" + "1" * 64, _cairn_labels()),
            "broken": RegistryError("unsupported manifest type"),
        },
    )

    found, others = images.inspect_registry(base)

    assert len(found) == 1
    assert others == 1


def test_registry_images_are_ordered_by_their_own_creation_label(monkeypatch):
    """A registry reports no creation time — only the image does, via BR-BUILD-011. That
    label is the sole clock available, and tag order is explicitly not meaningful."""
    base = _stub_registry(
        monkeypatch,
        ["old", "new"],
        {
            "old": _remote_image(
                "sha256:" + "1" * 64, _cairn_labels(created="2026-07-01T00:00:00Z")
            ),
            "new": _remote_image(
                "sha256:" + "2" * 64, _cairn_labels(created="2026-07-25T00:00:00Z")
            ),
        },
    )

    found, _ = images.inspect_registry(base)

    assert [image.tags[0] for image in found] == ["new", "old"]


def test_an_image_without_a_creation_label_sorts_last(monkeypatch):
    labels = _cairn_labels()
    del labels[images.CREATED_LABEL]
    base = _stub_registry(
        monkeypatch,
        ["dated", "undated"],
        {
            "dated": _remote_image("sha256:" + "1" * 64, _cairn_labels()),
            "undated": _remote_image("sha256:" + "2" * 64, labels),
        },
    )

    found, _ = images.inspect_registry(base)

    assert [image.tags[0] for image in found] == ["dated", "undated"]


def test_registry_grouping_is_by_input_hash(monkeypatch):
    base = _stub_registry(
        monkeypatch,
        ["a", "b"],
        {
            "a": _remote_image("sha256:" + "1" * 64, _cairn_labels(input_hash="aaa111")),
            "b": _remote_image("sha256:" + "2" * 64, _cairn_labels(input_hash="bbb222")),
        },
    )
    found, _ = images.inspect_registry(base)

    grouped = images.group_registry(found)

    assert sorted(input_hash for input_hash, _ in grouped) == ["aaa111", "bbb222"]


def test_the_registry_report_says_sizes_are_download_sizes():
    """Registry sizes are compressed transfer sizes and local sizes are unpacked; the two
    legitimately differ and must never be read as a discrepancy."""
    base = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:latest")
    image = _remote_image("sha256:" + "1" * 64, _cairn_labels())
    image = images.RegistryImage(
        digest=image.digest, tags=("v16",), size=image.size, labels=image.labels
    )

    rendered = images.render_registry(base, [("aaa111", [image])], 0)

    assert "download size" in rendered
    assert "not unpacked size" in rendered


def test_an_empty_registry_says_so_plainly():
    base = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:latest")

    assert "No images cairn built" in images.render_registry(base, [], 0)
