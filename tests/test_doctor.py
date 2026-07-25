"""Tests for the ``cairn doctor`` preflight checks (BR-CLI-007, BR-CLI-012).

Engine detection lives in ``test_engine.py`` and config parsing in ``test_config.py``;
these tests cover how doctor composes, reports, and exits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn import config as config_module
from cairn import doctor, engine
from cairn.errors import (
    BuildEngineError,
    ManifestInvalidError,
    ManifestNotFoundError,
    RefResolutionError,
    VendorDriftError,
)

DOCKER = engine.BuildEngine(name="docker", version="27.3.1")
PODMAN = engine.BuildEngine(name="podman", version="5.4.2")


@pytest.fixture
def all_vendor_checks_pass(monkeypatch):
    monkeypatch.setattr(doctor.vendor, "assert_clean", lambda root: None)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", lambda root: None)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", lambda root: None)


@pytest.fixture
def config_ok(monkeypatch):
    """A discoverable, valid manifest with all-default build config."""
    _stub_config(monkeypatch, config_module.BuildConfig())


@pytest.fixture(autouse=True)
def git_present(monkeypatch):
    """Composition tests must not depend on the host having git installed."""
    monkeypatch.setattr(doctor.resolve, "git_version", lambda: "2.47.1")


def _stub_config(monkeypatch, build_config, apps=()):
    monkeypatch.setattr(doctor.config, "find_manifest", lambda: Path("cairn.toml"))
    monkeypatch.setattr(
        doctor.config,
        "load_manifest",
        lambda path: config_module.Manifest("x", config_module.Frappe("u", "r"), apps),
    )
    monkeypatch.setattr(doctor.config, "load_build_config", lambda path: build_config)


def _boom(root):
    raise VendorDriftError("nope")


# --- config check (BR-CFG-012; missing manifest warns, malformed fails) ------


def test_missing_manifest_warns_rather_than_fails(monkeypatch):
    """doctor is a machine preflight — legitimately run before a manifest exists."""

    def _missing():
        raise ManifestNotFoundError("No cairn.toml found at or above /tmp. Use --manifest.")

    monkeypatch.setattr(doctor.config, "find_manifest", _missing)

    result, build_config = doctor.check_config()

    assert result.status is doctor.Status.WARN
    assert build_config is None


def test_malformed_manifest_fails(monkeypatch):
    """A manifest that exists but is wrong is a hard failure, not a warning."""
    monkeypatch.setattr(doctor.config, "find_manifest", lambda: Path("cairn.toml"))

    def _invalid(path):
        raise ManifestInvalidError("cairn.toml: [cairn] has unknown key(s) imagename")

    monkeypatch.setattr(doctor.config, "load_manifest", _invalid)

    result, build_config = doctor.check_config()

    assert result.status is doctor.Status.FAIL
    assert "unknown key" in result.detail
    assert build_config is None


def test_valid_config_reports_app_count_and_sources(monkeypatch):
    _stub_config(
        monkeypatch,
        config_module.BuildConfig(sources=(Path("/home/u/.config/cairn/config.toml"),)),
        apps=(config_module.App("erpnext", "u", "r"),),
    )

    result, build_config = doctor.check_config()

    assert result.status is doctor.Status.OK
    assert "1 app(s)" in result.detail
    assert "config.toml" in result.detail
    assert build_config is not None


def test_warning_does_not_affect_exit_code(monkeypatch):
    """BR-CLI-012: only failures are non-zero; a warning still exits 0."""
    results = [
        doctor.CheckResult("config", doctor.Status.WARN, "no cairn.toml"),
        doctor.CheckResult.of("build engine", True, "podman v5.4.2"),
    ]

    assert doctor.report(results) == 0


# --- git (BR-CLI-007, BR-BUILD-005) -----------------------------------------


def test_git_present_is_reported_with_version(monkeypatch):
    monkeypatch.setattr(doctor.resolve, "git_version", lambda: "2.47.1")

    assert doctor.check_git() == doctor.CheckResult.of("git", True, "v2.47.1")


def test_missing_git_fails_the_preflight(monkeypatch):
    """BR-CLI-007: without git, ref resolution would fail well into a build."""

    def _absent():
        raise RefResolutionError("`git` not found on PATH; cairn resolves every manifest ref…")

    monkeypatch.setattr(doctor.resolve, "git_version", _absent)

    result = doctor.check_git()

    assert result.status is doctor.Status.FAIL
    assert "not found on PATH" in result.detail


# --- engine reporting -------------------------------------------------------


def test_reports_selected_engine_and_version(monkeypatch):
    """ADR-027: doctor names which engine it resolved, not merely that one exists."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)

    result, selected = doctor.check_build_engine()

    assert result.status is doctor.Status.OK and result.detail == "podman v5.4.2"
    assert selected is PODMAN


def test_engine_failure_is_reported_not_raised(monkeypatch):
    """Doctor reports; it does not abort partway through the check list."""

    def _detect(preferred):
        raise BuildEngineError("no bueno")

    monkeypatch.setattr(doctor.engine, "detect", _detect)

    result, selected = doctor.check_build_engine()

    assert result.status is doctor.Status.FAIL and selected is None


# --- check composition (ADR-027) --------------------------------------------


def test_buildx_checked_only_for_docker(monkeypatch, tmp_path, all_vendor_checks_pass, config_ok):
    """ADR-027: a docker machine is checked for the buildx plugin."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: DOCKER)
    monkeypatch.setattr(
        doctor, "check_buildx", lambda: doctor.CheckResult.of("docker buildx", True, "x")
    )

    labels = [r.label for r in doctor.run_checks(tmp_path)]

    assert labels == [
        "config",
        "build engine",
        "docker buildx",
        "git",
        "vendored tree",
        "vendor .git",
        "build inputs",
    ]


def test_buildx_not_checked_for_podman(monkeypatch, tmp_path, all_vendor_checks_pass, config_ok):
    """ADR-027: a podman machine is never told to install a Docker plugin it won't use."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)

    labels = [r.label for r in doctor.run_checks(tmp_path)]

    assert "docker buildx" not in labels
    assert labels == [
        "config",
        "build engine",
        "git",
        "vendored tree",
        "vendor .git",
        "build inputs",
    ]


def test_configured_engine_reaches_detection(monkeypatch, tmp_path, all_vendor_checks_pass):
    """BR-CFG-008: `engine =` from build config drives detection with no flag."""
    seen: list[str | None] = []
    _stub_config(monkeypatch, config_module.BuildConfig(engine="podman"))

    def _detect(preferred):
        seen.append(preferred)
        return PODMAN

    monkeypatch.setattr(doctor.engine, "detect", _detect)

    doctor.run_checks(tmp_path)

    assert seen == ["podman"]


def test_explicit_engine_overrides_configured_one(monkeypatch, tmp_path, all_vendor_checks_pass):
    """An explicit argument wins over the configured preference."""
    seen: list[str | None] = []
    _stub_config(monkeypatch, config_module.BuildConfig(engine="podman"))

    def _detect(preferred):
        seen.append(preferred)
        return DOCKER

    monkeypatch.setattr(doctor.engine, "detect", _detect)
    monkeypatch.setattr(
        doctor, "check_buildx", lambda: doctor.CheckResult.of("docker buildx", True, "x")
    )

    doctor.run_checks(tmp_path, preferred_engine="docker")

    assert seen == ["docker"]


def test_all_checks_run_even_after_a_failure(monkeypatch, tmp_path, config_ok):
    """BR-CLI-007: one invocation reports the full picture; no short-circuit."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)
    monkeypatch.setattr(doctor.vendor, "assert_clean", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", _boom)

    results = doctor.run_checks(tmp_path)

    assert [r.status for r in results] == [
        doctor.Status.OK,  # config
        doctor.Status.OK,  # build engine
        doctor.Status.OK,  # git
        doctor.Status.FAIL,
        doctor.Status.FAIL,
        doctor.Status.FAIL,
    ]


# --- vendored-tree guards ---------------------------------------------------


def test_guard_reports_failure_without_raising():
    """BR-VEND-005: doctor reports drift rather than aborting, so all checks still run."""

    def _drifted():
        raise VendorDriftError("Vendored tree has drifted from .ventwig.lock;\nsecond line")

    result = doctor._guard("vendored tree", _drifted, "matches .ventwig.lock")

    assert result.status is doctor.Status.FAIL
    assert result.detail == "Vendored tree has drifted from .ventwig.lock;"


def test_guard_reports_success():
    result = doctor._guard("vendored tree", lambda: None, "matches .ventwig.lock")

    assert result.status is doctor.Status.OK and result.detail == "matches .ventwig.lock"


# --- exit codes (BR-CLI-012) ------------------------------------------------


def test_report_exit_code_zero_when_all_pass():
    results = [doctor.CheckResult.of("a", True, "ok"), doctor.CheckResult.of("b", True, "ok")]

    assert doctor.report(results) == 0


def test_report_exit_code_nonzero_on_any_failure():
    """BR-CLI-012: any failed check makes the exit code non-zero, so systemd/CI notice."""
    results = [doctor.CheckResult.of("a", True, "ok"), doctor.CheckResult.of("b", False, "bad")]

    assert doctor.report(results) == 1
