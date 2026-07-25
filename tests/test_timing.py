"""Tests for start/end/duration and per-phase timing (BR-CLI-017)."""

from __future__ import annotations

import pytest

from cairn import build, timing
from cairn.config import App, Frappe, Manifest
from cairn.resolve import RefKind, Resolution, ResolvedRef


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0.42, "0.4s"),
        (6.14, "6.1s"),
        (59.9, "59.9s"),
        (60, "1m 00s"),
        (582, "9m 42s"),
        (3600, "1h 00m 00s"),
        (3792, "1h 03m 12s"),
    ],
)
def test_durations_read_like_a_stopwatch(seconds, expected):
    assert timing.format_duration(seconds) == expected


def test_phases_are_recorded_in_order():
    watch = timing.Stopwatch()
    with watch.phase("checks + ref resolution"):
        pass
    with watch.phase("image build"):
        pass

    assert [phase.name for phase in watch.phases] == ["checks + ref resolution", "image build"]


def test_a_failed_phase_is_still_recorded():
    """A failure report must show how far the command got, and how long that took."""
    watch = timing.Stopwatch()
    with pytest.raises(RuntimeError), watch.phase("image build"):
        raise RuntimeError("engine died")

    assert [phase.name for phase in watch.phases] == ["image build"]


def test_durations_use_the_monotonic_clock(monkeypatch):
    """A mid-build NTP step must not be able to produce a negative duration."""
    ticks = iter([100.0, 100.0, 105.5])
    monkeypatch.setattr(timing.time, "monotonic", lambda: next(ticks))

    watch = timing.Stopwatch()
    with watch.phase("image build"):
        pass

    assert watch.phases[0].seconds == pytest.approx(5.5)


def test_summary_reports_start_end_and_total():
    watch = timing.Stopwatch()
    with watch.phase("image build"):
        pass
    rendered = "\n".join(watch.summary())

    assert "image build" in rendered
    assert "started" in rendered
    assert "finished" in rendered
    assert "total" in rendered


def test_duration_never_reaches_provenance_labels(tmp_path):
    """Elapsed time is a property of a run, not of the image's inputs (BR-BUILD-013)."""
    manifest = Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "version-16"),),
    )
    resolution = Resolution(
        frappe=ResolvedRef(
            name="frappe",
            url="https://github.com/frappe/frappe",
            ref="version-16",
            kind=RefKind.BRANCH,
            commit="a" * 40,
        ),
        apps=(),
    )
    labels = build.provenance_labels(
        tmp_path, manifest, resolution, {"PYTHON_VERSION": "3.14.2"}, "v16-abcd1234", "latest"
    )

    joined = " ".join(labels).lower()
    assert "duration" not in joined
    assert "elapsed" not in joined
    assert "seconds" not in joined
