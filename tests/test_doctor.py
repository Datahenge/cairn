"""Tests for the ``cairn doctor`` preflight checks (BR-CLI-007, BR-CLI-012).

Engine detection itself is covered by ``test_engine.py``; these tests cover how doctor
composes, reports, and exits.
"""

from __future__ import annotations

import pytest

from cairn import doctor, engine
from cairn.errors import BuildEngineError, VendorDriftError

DOCKER = engine.BuildEngine(name="docker", version="27.3.1")
PODMAN = engine.BuildEngine(name="podman", version="5.4.2")


@pytest.fixture
def all_vendor_checks_pass(monkeypatch):
    monkeypatch.setattr(doctor.vendor, "assert_clean", lambda root: None)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", lambda root: None)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", lambda root: None)


def _boom(root):
    raise VendorDriftError("nope")


# --- engine reporting -------------------------------------------------------


def test_reports_selected_engine_and_version(monkeypatch):
    """ADR-027: doctor names which engine it resolved, not merely that one exists."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)

    result, selected = doctor.check_build_engine()

    assert result.ok and result.detail == "podman v5.4.2"
    assert selected is PODMAN


def test_engine_failure_is_reported_not_raised(monkeypatch):
    """Doctor reports; it does not abort partway through the check list."""
    monkeypatch.setattr(
        doctor.engine,
        "detect",
        lambda preferred: (_ for _ in ()).throw(BuildEngineError("no bueno")),
    )

    result, selected = doctor.check_build_engine()

    assert not result.ok and selected is None


# --- check composition (ADR-027) -------------------------------------------


def test_buildx_checked_only_for_docker(monkeypatch, tmp_path, all_vendor_checks_pass):
    """ADR-027: a docker machine is checked for the buildx plugin."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: DOCKER)
    monkeypatch.setattr(
        doctor, "check_buildx", lambda: doctor.CheckResult("docker buildx", True, "x")
    )

    labels = [r.label for r in doctor.run_checks(tmp_path)]

    assert labels == [
        "build engine",
        "docker buildx",
        "vendored tree",
        "vendor .git",
        "build inputs",
    ]


def test_buildx_not_checked_for_podman(monkeypatch, tmp_path, all_vendor_checks_pass):
    """ADR-027: a podman machine is never told to install a Docker plugin it won't use."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)

    labels = [r.label for r in doctor.run_checks(tmp_path)]

    assert "docker buildx" not in labels
    assert labels == ["build engine", "vendored tree", "vendor .git", "build inputs"]


def test_preferred_engine_is_passed_through(monkeypatch, tmp_path, all_vendor_checks_pass):
    """BR-CFG-008: the configured engine preference reaches detection."""
    seen: list[str | None] = []

    def _detect(preferred):
        seen.append(preferred)
        return PODMAN

    monkeypatch.setattr(doctor.engine, "detect", _detect)

    doctor.run_checks(tmp_path, preferred_engine="podman")

    assert seen == ["podman"]


def test_all_checks_run_even_after_a_failure(monkeypatch, tmp_path):
    """BR-CLI-007: one invocation reports the full picture; no short-circuit."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)
    monkeypatch.setattr(doctor.vendor, "assert_clean", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", _boom)

    results = doctor.run_checks(tmp_path)

    assert [r.ok for r in results] == [True, False, False, False]


# --- vendored-tree guards ---------------------------------------------------


def test_guard_reports_failure_without_raising():
    """BR-VEND-005: doctor reports drift rather than aborting, so all checks still run."""

    def _drifted():
        raise VendorDriftError("Vendored tree has drifted from .ventwig.lock;\nsecond line")

    result = doctor._guard("vendored tree", _drifted, "matches .ventwig.lock")

    assert not result.ok
    assert result.detail == "Vendored tree has drifted from .ventwig.lock;"


def test_guard_reports_success():
    result = doctor._guard("vendored tree", lambda: None, "matches .ventwig.lock")

    assert result.ok and result.detail == "matches .ventwig.lock"


# --- exit codes (BR-CLI-012) ------------------------------------------------


def test_report_exit_code_zero_when_all_pass():
    results = [doctor.CheckResult("a", True, "ok"), doctor.CheckResult("b", True, "ok")]

    assert doctor.report(results) == 0


def test_report_exit_code_nonzero_on_any_failure():
    """BR-CLI-012: any failed check makes the exit code non-zero, so systemd/CI notice."""
    results = [doctor.CheckResult("a", True, "ok"), doctor.CheckResult("b", False, "bad")]

    assert doctor.report(results) == 1
