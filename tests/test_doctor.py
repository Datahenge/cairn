"""Tests for the `cairn-build doctor` / `cairn-adopt doctor` preflight checks
(BR-CLI-007, BR-CLI-012).

Engine detection lives in ``test_engine.py`` and config parsing in ``test_config.py``;
these tests cover how doctor composes, reports, and exits.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn import config as config_module
from cairn import doctor, engine
from cairn.descriptor import Descriptor
from cairn.errors import (
    BuildEngineError,
    DescriptorError,
    ManifestInvalidError,
    ManifestNotFoundError,
    RefResolutionError,
    RegistryError,
    VendorDriftError,
)

DOCKER = engine.BuildEngine(name="docker", version="27.3.1")
PODMAN = engine.BuildEngine(name="podman", version="5.4.2")


@pytest.fixture
def all_vendor_checks_pass(monkeypatch):
    monkeypatch.setattr(doctor.vendor, "assert_clean", lambda: None)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", lambda: None)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", lambda: None)


@pytest.fixture
def config_ok(monkeypatch):
    """A discoverable, valid manifest with all-default build config."""
    _stub_config(monkeypatch, config_module.BuildConfig())


@pytest.fixture(autouse=True)
def git_present(monkeypatch):
    """Composition tests must not depend on the host having git installed."""
    monkeypatch.setattr(doctor.resolve, "git_version", lambda: "2.47.1")


@pytest.fixture
def shared_config_ok(monkeypatch):
    """Composition tests must not depend on whether /etc/cairn exists on the test host."""
    monkeypatch.setattr(
        doctor,
        "check_shared_config_dir",
        lambda: doctor.CheckResult.of("shared config", True, "ok"),
    )


@pytest.fixture
def known_manifests_ok(monkeypatch):
    """Composition tests must not depend on whether /srv/cairn exists on the test host."""
    monkeypatch.setattr(
        doctor,
        "check_known_manifests",
        lambda: doctor.CheckResult.of("known manifests", True, "none found under /srv/cairn"),
    )


@pytest.fixture
def disk_ok(monkeypatch):
    """Composition tests must not depend on how much free disk the test host has."""
    monkeypatch.setattr(
        doctor, "check_disk", lambda selected: doctor.CheckResult.of("free disk", True, "ok")
    )


@pytest.fixture
def memory_ok(monkeypatch):
    """Composition tests must not depend on how much memory the test host has."""
    monkeypatch.setattr(
        doctor, "check_memory", lambda: doctor.CheckResult.of("available memory", True, "ok")
    )


def _stub_config(monkeypatch, build_config, apps=()):
    monkeypatch.setattr(doctor.config, "find_manifest", lambda explicit=None: Path("cairn.toml"))
    monkeypatch.setattr(
        doctor.config,
        "load_manifest",
        lambda path: config_module.Manifest("x", config_module.Frappe("u", "r"), apps),
    )
    monkeypatch.setattr(doctor.config, "load_build_config", lambda path: build_config)


def _boom():
    raise VendorDriftError("nope")


# --- config check (BR-CFG-012; missing manifest warns, malformed fails) ------


def test_missing_manifest_warns_rather_than_fails(monkeypatch):
    """doctor is a machine preflight — legitimately run before a manifest exists."""

    def _missing(explicit=None):
        raise ManifestNotFoundError("No manifest given. Pass --manifest <path>.")

    monkeypatch.setattr(doctor.config, "find_manifest", _missing)

    result, build_config = doctor.check_config()

    assert result.status is doctor.Status.WARN
    assert build_config is None


def test_malformed_manifest_fails(monkeypatch):
    """A manifest that exists but is wrong is a hard failure, not a warning."""
    monkeypatch.setattr(doctor.config, "find_manifest", lambda explicit=None: Path("cairn.toml"))

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
        config_module.BuildConfig(sources=("/etc/cairn/builder.toml",)),
        apps=(config_module.App("erpnext", "u", "r"),),
    )

    result, build_config = doctor.check_config()

    assert result.status is doctor.Status.OK
    assert "1 app(s)" in result.detail
    assert "builder.toml" in result.detail
    assert build_config is not None


# --- shared config dir (BR-CFG-015, ADR-043) --------------------------------


def test_shared_config_dir_warns_when_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "SHARED_CONFIG_DIR", tmp_path / "does-not-exist")

    result = doctor.check_shared_config_dir()

    assert result.status is doctor.Status.WARN
    assert "does not exist" in result.detail


def test_shared_config_dir_reports_group_mode_and_membership(monkeypatch, tmp_path):
    """Purely informational (ADR-043): reports the facts, never changes them."""
    import grp
    import os

    shared = tmp_path / "cairn"
    shared.mkdir()
    os.chmod(shared, 0o2775)
    monkeypatch.setattr(doctor, "SHARED_CONFIG_DIR", shared)

    result = doctor.check_shared_config_dir()

    own_group = grp.getgrgid(os.getgid()).gr_name
    assert result.status is doctor.Status.OK
    assert own_group in result.detail
    assert "setgid" in result.detail
    assert "group-writable" in result.detail
    assert "current user is a member" in result.detail


def test_shared_config_dir_reports_not_group_writable(monkeypatch, tmp_path):
    import os

    shared = tmp_path / "cairn"
    shared.mkdir()
    os.chmod(shared, 0o755)
    monkeypatch.setattr(doctor, "SHARED_CONFIG_DIR", shared)

    result = doctor.check_shared_config_dir()

    assert result.status is doctor.Status.OK
    assert "not group-writable" in result.detail


# --- known manifests (BR-CLI-022, ADR-047) ----------------------------------


def test_known_manifests_ok_when_srv_cairn_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "MANIFEST_ROOT", tmp_path / "does-not-exist")

    result = doctor.check_known_manifests()

    assert result.status is doctor.Status.OK
    assert "none found" in result.detail


def test_known_manifests_lists_client_directories(monkeypatch, tmp_path):
    """Informational only — this listing is never used to select a manifest for a command
    to act on (`BR-CLI-014` is unchanged)."""
    root = tmp_path / "cairn"
    (root / "acme").mkdir(parents=True)
    (root / "acme" / "cairn.toml").touch()
    (root / "contoso").mkdir(parents=True)
    (root / "contoso" / "cairn.toml").touch()
    (root / "no-manifest-yet").mkdir(parents=True)
    monkeypatch.setattr(doctor, "MANIFEST_ROOT", root)

    result = doctor.check_known_manifests()

    assert result.status is doctor.Status.OK
    assert "acme" in result.detail
    assert "contoso" in result.detail
    assert "no-manifest-yet" not in result.detail


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


# --- disk & memory (the same floors `setup`'s preflight gates a build on) --


def test_check_disk_reads_the_docker_data_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "_run", lambda command: _completed(0, stdout=f"{tmp_path}\n"))
    monkeypatch.setattr(
        doctor.shutil, "disk_usage", lambda path: type("U", (), {"free": 999_000_000_000})()
    )

    result = doctor.check_disk(DOCKER)

    assert result.status is doctor.Status.OK
    assert str(tmp_path) in result.detail
    assert "999 GB" in result.detail


def test_check_disk_reads_the_podman_graph_root(monkeypatch, tmp_path):
    seen: list[list[str]] = []

    def _run(command):
        seen.append(command)
        return _completed(0, stdout=f"{tmp_path}\n")

    monkeypatch.setattr(doctor, "_run", _run)
    monkeypatch.setattr(
        doctor.shutil, "disk_usage", lambda path: type("U", (), {"free": 999_000_000_000})()
    )

    doctor.check_disk(PODMAN)

    assert seen == [["podman", "info", "--format", "{{.Store.GraphRoot}}"]]


def test_check_disk_falls_back_to_root_when_the_probe_fails(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda command: None)
    seen: list[Path] = []

    def _disk_usage(path):
        seen.append(path)
        return type("U", (), {"free": 999_000_000_000})()

    monkeypatch.setattr(doctor.shutil, "disk_usage", _disk_usage)

    doctor.check_disk(None)

    assert seen == [Path("/")]


def test_check_disk_fails_below_the_minimum(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda command: None)
    monkeypatch.setattr(
        doctor.shutil, "disk_usage", lambda path: type("U", (), {"free": 1_000_000_000})()
    )

    result = doctor.check_disk(None)

    assert result.status is doctor.Status.FAIL
    assert "needs" in result.detail


def test_check_disk_fails_when_undeterminable(monkeypatch):
    monkeypatch.setattr(doctor, "_run", lambda command: None)

    def _raise(path):
        raise OSError("no such filesystem")

    monkeypatch.setattr(doctor.shutil, "disk_usage", _raise)

    result = doctor.check_disk(None)

    assert result.status is doctor.Status.FAIL
    assert "cannot be determined" in result.detail


def test_check_memory_reports_available_gb(monkeypatch):
    monkeypatch.setattr(doctor, "read_available_memory_gb", lambda meminfo: 8.5)

    result = doctor.check_memory()

    assert result.status is doctor.Status.OK
    assert "8.5 GB" in result.detail


def test_check_memory_fails_below_the_minimum(monkeypatch):
    monkeypatch.setattr(doctor, "read_available_memory_gb", lambda meminfo: 1.0)

    result = doctor.check_memory()

    assert result.status is doctor.Status.FAIL
    assert "OOM" in result.detail


def test_check_memory_fails_when_undeterminable(monkeypatch):
    monkeypatch.setattr(doctor, "read_available_memory_gb", lambda meminfo: None)

    result = doctor.check_memory()

    assert result.status is doctor.Status.FAIL
    assert "/proc/meminfo" in result.detail


# --- check composition (ADR-027) --------------------------------------------


def test_buildx_checked_only_for_docker(
    monkeypatch,
    all_vendor_checks_pass,
    config_ok,
    shared_config_ok,
    known_manifests_ok,
    disk_ok,
    memory_ok,
):
    """ADR-027: a docker machine is checked for the buildx plugin."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: DOCKER)
    monkeypatch.setattr(
        doctor, "check_buildx", lambda: doctor.CheckResult.of("docker buildx", True, "x")
    )

    labels = [r.label for r in doctor.run_build_checks()]

    assert labels == [
        "config",
        "build engine",
        "docker buildx",
        "free disk",
        "available memory",
        "git",
        "vendored tree",
        "vendor .git",
        "build inputs",
        "shared config",
        "known manifests",
    ]


def test_buildx_not_checked_for_podman(
    monkeypatch,
    all_vendor_checks_pass,
    config_ok,
    shared_config_ok,
    known_manifests_ok,
    disk_ok,
    memory_ok,
):
    """ADR-027: a podman machine is never told to install a Docker plugin it won't use."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)

    labels = [r.label for r in doctor.run_build_checks()]

    assert "docker buildx" not in labels
    assert labels == [
        "config",
        "build engine",
        "free disk",
        "available memory",
        "git",
        "vendored tree",
        "vendor .git",
        "build inputs",
        "shared config",
        "known manifests",
    ]


def test_configured_engine_reaches_detection(
    monkeypatch, all_vendor_checks_pass, shared_config_ok, disk_ok, memory_ok
):
    """BR-CFG-008: `engine =` from build config drives detection with no flag."""
    seen: list[str | None] = []
    _stub_config(monkeypatch, config_module.BuildConfig(engine="podman"))

    def _detect(preferred):
        seen.append(preferred)
        return PODMAN

    monkeypatch.setattr(doctor.engine, "detect", _detect)

    doctor.run_build_checks()

    assert seen == ["podman"]


def test_explicit_engine_overrides_configured_one(
    monkeypatch, all_vendor_checks_pass, shared_config_ok, disk_ok, memory_ok
):
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

    doctor.run_build_checks(preferred_engine="docker")

    assert seen == ["docker"]


def test_all_checks_run_even_after_a_failure(
    monkeypatch, config_ok, shared_config_ok, known_manifests_ok, disk_ok, memory_ok
):
    """BR-CLI-007: one invocation reports the full picture; no short-circuit."""
    monkeypatch.setattr(doctor.engine, "detect", lambda preferred: PODMAN)
    monkeypatch.setattr(doctor.vendor, "assert_clean", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_no_nested_git", _boom)
    monkeypatch.setattr(doctor.vendor, "assert_build_inputs", _boom)

    results = doctor.run_build_checks()

    assert [r.status for r in results] == [
        doctor.Status.OK,  # config
        doctor.Status.OK,  # build engine
        doctor.Status.OK,  # free disk
        doctor.Status.OK,  # available memory
        doctor.Status.OK,  # git
        doctor.Status.FAIL,
        doctor.Status.FAIL,
        doctor.Status.FAIL,
        doctor.Status.OK,  # shared config
        doctor.Status.OK,  # known manifests
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


@pytest.mark.parametrize(
    ("results", "expected_code"),
    [
        (
            # a warning still exits 0 — only failures are non-zero.
            [
                doctor.CheckResult("config", doctor.Status.WARN, "no cairn.toml"),
                doctor.CheckResult.of("build engine", True, "podman v5.4.2"),
            ],
            0,
        ),
        ([doctor.CheckResult.of("a", True, "ok"), doctor.CheckResult.of("b", True, "ok")], 0),
        # any failed check makes the exit code non-zero, so systemd/CI notice.
        ([doctor.CheckResult.of("a", True, "ok"), doctor.CheckResult.of("b", False, "bad")], 1),
    ],
    ids=["warning-only", "all-pass", "any-failure"],
)
def test_report_exit_code(results, expected_code):
    """BR-CLI-012: only failures are non-zero; a warning still exits 0."""
    assert doctor.report(results) == expected_code


# --- two fixed entry points, no role detection (`ADR-046`) -------------------


def test_run_build_reports_and_returns_the_exit_code(monkeypatch):
    """`cairn-build doctor` always runs the build checks — nothing to detect."""
    monkeypatch.setattr(
        doctor, "run_build_checks", lambda preferred_engine=None, manifest_path=None: []
    )
    monkeypatch.setattr(doctor, "report", lambda results: 0)

    assert doctor.run_build() == 0


def test_run_target_reports_and_returns_the_exit_code(monkeypatch):
    """`cairn-adopt doctor` always runs the target checks — nothing to detect."""
    monkeypatch.setattr(doctor, "run_target_checks", lambda: [])
    monkeypatch.setattr(doctor, "report", lambda results: 1)

    assert doctor.run_target() == 1


# --- target checks (`ADR-028`) ------------------------------------------------


def _descriptor(**overrides):
    defaults = dict(
        environment="production",
        image="ghcr.io/datahenge/erpnext-btu-v16",
        tag="production",
        site="erp.example.com",
    )
    return Descriptor(**{**defaults, **overrides})


def _completed(returncode: int, stdout: str = "", stderr: str = ""):
    return type("R", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr})()


def test_check_descriptor_reports_environment_site_and_reference(monkeypatch):
    monkeypatch.setattr(doctor.descriptor, "load", lambda: _descriptor())

    result, loaded = doctor.check_descriptor()

    assert result.status is doctor.Status.OK
    assert "production" in result.detail
    assert "erp.example.com" in result.detail
    assert "ghcr.io/datahenge/erpnext-btu-v16:production" in result.detail
    assert loaded is not None


def test_check_descriptor_fails_when_it_does_not_parse(monkeypatch):
    def _raise():
        raise DescriptorError("not valid TOML")

    monkeypatch.setattr(doctor.descriptor, "load", _raise)

    result, loaded = doctor.check_descriptor()

    assert result.status is doctor.Status.FAIL
    assert loaded is None


def test_check_docker_reuses_engine_detection(monkeypatch):
    monkeypatch.setattr(doctor.engine, "check", lambda name: DOCKER)

    result = doctor.check_docker()

    assert result.status is doctor.Status.OK
    assert "docker" in result.detail


def test_check_docker_fails_when_daemon_unreachable(monkeypatch):
    def _raise(name):
        raise BuildEngineError("Docker daemon not reachable")

    monkeypatch.setattr(doctor.engine, "check", _raise)

    result = doctor.check_docker()

    assert result.status is doctor.Status.FAIL
    assert "not reachable" in result.detail


@pytest.mark.parametrize(
    ("run_stub", "expected_status", "expected_detail"),
    [
        (lambda command: _completed(0, stdout="Docker Compose v2.29.0"), doctor.Status.OK, "Compose"),
        (lambda command: _completed(1, stderr="unknown command"), doctor.Status.FAIL, "unknown command"),
        (lambda command: None, doctor.Status.FAIL, None),
    ],
    ids=["plugin-answers", "nonzero-exit", "docker-absent"],
)
def test_check_compose(monkeypatch, run_stub, expected_status, expected_detail):
    monkeypatch.setattr(doctor, "_run", run_stub)

    result = doctor.check_compose()

    assert result.status is expected_status
    if expected_detail is not None:
        assert expected_detail in result.detail


@pytest.mark.parametrize(
    ("run_stub", "expected_status", "expected_detail"),
    [
        (lambda command: _completed(0, stdout="active\n"), doctor.Status.OK, None),
        # not a failure: legitimately true before the first manual reconcile.
        (lambda command: _completed(3, stdout="inactive\n"), doctor.Status.WARN, "inactive"),
        (lambda command: None, doctor.Status.WARN, "not available"),
    ],
    ids=["active", "inactive", "systemd-absent"],
)
def test_check_reconcile_timer(monkeypatch, run_stub, expected_status, expected_detail):
    monkeypatch.setattr(doctor, "_run", run_stub)

    result = doctor.check_reconcile_timer()

    assert result.status is expected_status
    if expected_detail is not None:
        assert expected_detail in result.detail


def test_check_registry_reachable_reads_the_descriptors_own_reference(monkeypatch):
    seen = {}

    def _digest_of(ref):
        seen["ref"] = ref
        return "sha256:" + "a" * 64

    monkeypatch.setattr(doctor.registry, "digest_of", _digest_of)

    result = doctor.check_registry_reachable(_descriptor())

    assert result.status is doctor.Status.OK
    assert str(seen["ref"]) == "ghcr.io/datahenge/erpnext-btu-v16:production"


def test_check_registry_reachable_fails_with_the_registrys_own_message(monkeypatch):
    def _raise(ref):
        raise RegistryError("not permitted to read ghcr.io/datahenge/erpnext-btu-v16")

    monkeypatch.setattr(doctor.registry, "digest_of", _raise)

    result = doctor.check_registry_reachable(_descriptor())

    assert result.status is doctor.Status.FAIL
    assert "not permitted" in result.detail


def test_run_target_checks_skips_the_registry_when_the_descriptor_fails(
    monkeypatch, shared_config_ok
):
    def _raise():
        raise DescriptorError("nope")

    monkeypatch.setattr(doctor.descriptor, "load", _raise)
    monkeypatch.setattr(doctor, "check_docker", lambda: doctor.CheckResult.of("docker", True, "ok"))
    monkeypatch.setattr(
        doctor, "check_compose", lambda: doctor.CheckResult.of("docker compose", True, "ok")
    )
    monkeypatch.setattr(
        doctor,
        "check_reconcile_timer",
        lambda: doctor.CheckResult.of("reconcile timer", True, "ok"),
    )

    results = doctor.run_target_checks()

    assert [r.label for r in results] == [
        "descriptor",
        "docker",
        "docker compose",
        "reconcile timer",
        "shared config",
    ]


def test_run_target_checks_includes_the_registry_when_the_descriptor_loads(
    monkeypatch, shared_config_ok
):
    monkeypatch.setattr(doctor.descriptor, "load", lambda: _descriptor())
    monkeypatch.setattr(doctor, "check_docker", lambda: doctor.CheckResult.of("docker", True, "ok"))
    monkeypatch.setattr(
        doctor, "check_compose", lambda: doctor.CheckResult.of("docker compose", True, "ok")
    )
    monkeypatch.setattr(
        doctor,
        "check_reconcile_timer",
        lambda: doctor.CheckResult.of("reconcile timer", True, "ok"),
    )
    monkeypatch.setattr(doctor.registry, "digest_of", lambda ref: "sha256:" + "a" * 64)

    results = doctor.run_target_checks()

    assert [r.label for r in results] == [
        "descriptor",
        "docker",
        "docker compose",
        "reconcile timer",
        "registry",
        "shared config",
    ]
