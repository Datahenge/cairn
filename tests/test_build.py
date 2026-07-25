"""Tests for build planning, provenance, and invocation (BR-BUILD-009/010/011/012)."""

from __future__ import annotations

import json
import shlex
from pathlib import Path

import pytest

from cairn import build, vendor
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import BuildError, VendorDriftError
from cairn.resolve import RefKind, Resolution, ResolvedRef

CONTAINERFILE = """\
ARG PYTHON_VERSION=3.14.2
ARG DEBIAN_BASE=bookworm
ARG INSTALL_CHROMIUM=true
ARG NODE_VERSION=24.13.0
FROM python:${PYTHON_VERSION}-slim-${DEBIAN_BASE} AS base
ARG FRAPPE_BRANCH=version-16
ARG CACHE_BUST=""
ARG NO_DEFAULT
RUN echo hi
"""


@pytest.fixture
def containerfile(tmp_path):
    path = tmp_path / "Containerfile"
    path.write_text(CONTAINERFILE, encoding="utf-8")
    return path


def _manifest(build_knobs=None):
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "version-16"),),
        build=build_knobs if build_knobs is not None else {"python_version": "3.13.1"},
    )


def _resolution():
    return Resolution(
        frappe=ResolvedRef(
            "frappe", "https://github.com/frappe/frappe", "version-16", "a" * 40, RefKind.BRANCH
        ),
        apps=(
            ResolvedRef(
                "erpnext",
                "https://github.com/frappe/erpnext",
                "version-16",
                "b" * 40,
                RefKind.BRANCH,
            ),
        ),
    )


# --- effective build args (BR-BUILD-010) ------------------------------------


def test_containerfile_defaults_are_read_from_the_artifact(containerfile):
    """BR-BUILD-010: defaults come from the Containerfile, not a transcribed list."""
    defaults = vendor.containerfile_arg_defaults(containerfile)

    assert defaults["PYTHON_VERSION"] == "3.14.2"
    assert defaults["NODE_VERSION"] == "24.13.0"
    assert defaults["CACHE_BUST"] == ""
    assert "NO_DEFAULT" not in defaults  # an ARG with no default contributes no value


def test_manifest_knobs_override_defaults(containerfile):
    """BR-BUILD-010: effective value = Containerfile default, manifest knob on top."""
    args = build.effective_build_args(_manifest(), containerfile, _resolution())

    assert args["PYTHON_VERSION"] == "3.13.1"  # from the manifest
    assert args["NODE_VERSION"] == "24.13.0"  # from the Containerfile


def test_unset_knobs_still_recorded_from_defaults(containerfile):
    """The point of 'effective': what the build used, even when the manifest is silent."""
    args = build.effective_build_args(_manifest(build_knobs={}), containerfile, _resolution())

    assert args["PYTHON_VERSION"] == "3.14.2"
    assert args["DEBIAN_BASE"] == "bookworm"


def test_cache_bust_is_not_an_input(containerfile):
    """CACHE_BUST is derived from the resolution; recording it would restate the commits."""
    args = build.effective_build_args(_manifest(), containerfile, _resolution())

    assert build.CACHE_BUST_ARG not in args


def test_frappe_source_rides_build_args(containerfile):
    """BR-BUILD-004: Frappe goes via FRAPPE_*, never apps.json."""
    args = build.effective_build_args(_manifest(), containerfile, _resolution())

    assert args["FRAPPE_PATH"] == "https://github.com/frappe/frappe"
    assert args["FRAPPE_BRANCH"] == "version-16"


def test_toml_booleans_become_engine_strings(containerfile):
    args = build.effective_build_args(
        _manifest(build_knobs={"install_chromium": False}), containerfile, _resolution()
    )

    assert args["INSTALL_CHROMIUM"] == "false"


def test_passthrough_knob_is_upper_cased(containerfile):
    """BR-BUILD-002 grants [cairn.build] a passthrough for the long tail."""
    args = build.effective_build_args(
        _manifest(build_knobs={"wkhtmltopdf_version": "0.12.6.1-3"}), containerfile, _resolution()
    )

    assert args["WKHTMLTOPDF_VERSION"] == "0.12.6.1-3"


# --- provenance (BR-BUILD-011, ADR-030) -------------------------------------


def _labels(tmp_path):
    return build.provenance_labels(
        tmp_path, _manifest(), _resolution(), {"PYTHON_VERSION": "3.13.1"}, "v16-abc123", "latest"
    )


def test_labels_use_the_decided_namespaces(tmp_path):
    """ADR-030: cairn keys under com.datahenge.cairn.*, standard fields under OCI."""
    labels = _labels(tmp_path)

    assert labels["org.opencontainers.image.title"] == "erpnext-btu-v16"
    assert labels["org.opencontainers.image.version"] == "v16-abc123"
    assert labels["com.datahenge.cairn.input-hash"] == "abc123"


def test_vendor_label_is_not_set(tmp_path):
    """ADR-030: the distributing entity of the operator's image is theirs to declare."""
    assert "org.opencontainers.image.vendor" not in _labels(tmp_path)


def test_apps_label_is_json_in_manifest_order(tmp_path):
    """BR-BUILD-011 + BR-BUILD-003: apps travel with refs and commits, ordered."""
    apps = json.loads(_labels(tmp_path)["com.datahenge.cairn.apps"])

    assert apps == [
        {
            "name": "erpnext",
            "url": "https://github.com/frappe/erpnext",
            "ref": "version-16",
            "commit": "b" * 40,
        }
    ]


def test_vendor_pin_reads_ref_and_synced_commit(tmp_path):
    """The pin's halves live in two files by design (BR-VEND-002 / BR-VEND-003)."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.ventwig]\n[[tool.ventwig.sources]]\nname = "frappe_docker"\n'
        'local_path = "frappe_docker"\nref = "v3.2.1"\n',
        encoding="utf-8",
    )
    (tmp_path / build.LOCK_NAME).write_text(
        '[frappe_docker]\nsynced_commit = "d4a3100"\n', encoding="utf-8"
    )

    assert build.vendor_pin(tmp_path) == {"ref": "v3.2.1", "commit": "d4a3100"}


def test_missing_lock_degrades_to_empty(tmp_path):
    """Provenance is best-effort here; BR-VEND-005 is the check that actually gates."""
    (tmp_path / "pyproject.toml").write_text("[tool.ventwig]\n", encoding="utf-8")

    assert build.vendor_pin(tmp_path) == {"ref": "", "commit": ""}


# --- the command (BR-BUILD-006, BR-BUILD-009) -------------------------------


def _plan(**overrides):
    defaults = dict(
        image_base="ghcr.io/datahenge/erpnext-btu-v16",
        primary_tag="v16-abc123",
        moving_tag="latest",
        build_args={"PYTHON_VERSION": "3.13.1"},
        cache_bust="deadbeef",
        labels={"com.datahenge.cairn.input-hash": "abc123"},
        resolution=_resolution(),
        apps_json="[]\n",
        context=Path("/vendor/frappe_docker"),
        containerfile=Path("/vendor/frappe_docker/images/custom/Containerfile"),
        engine_name="podman",
    )
    return build.BuildPlan(**{**defaults, **overrides})


def test_apps_json_is_a_secret_never_a_build_arg():
    """BR-BUILD-006: a build-arg would be permanently readable via image history."""
    command = shlex.join(_plan().command(Path("/tmp/apps.json")))

    assert "--secret id=apps_json,src=/tmp/apps.json" in command
    assert "apps_json=" not in command.replace("id=apps_json", "")


def test_command_carries_cache_bust_and_both_tags():
    command = _plan().command(Path("/tmp/apps.json"))

    assert "CACHE_BUST=deadbeef" in command
    assert "ghcr.io/datahenge/erpnext-btu-v16:v16-abc123" in command
    assert "ghcr.io/datahenge/erpnext-btu-v16:latest" in command


def test_no_cache_is_opt_in():
    assert "--no-cache" not in _plan().command(Path("/x"))
    assert "--no-cache" in _plan(no_cache=True).command(Path("/x"))


def test_command_uses_the_selected_engine():
    assert _plan(engine_name="docker").command(Path("/x"))[0] == "docker"


def test_dry_run_render_shows_everything_without_building():
    """BR-BUILD-012: resolved apps.json, the exact command, tags, and intended provenance."""
    report = _plan().render()

    assert "apps.json" in report
    assert "ghcr.io/datahenge/erpnext-btu-v16:v16-abc123" in report
    assert "com.datahenge.cairn.input-hash=abc123" in report
    assert "podman build" in report
    assert "(moving)" in report  # branch pins are flagged, BR-BUILD-005


# --- preconditions and failure (BR-BUILD-009) -------------------------------


def test_plan_enforces_vendor_preconditions_before_resolving(monkeypatch, tmp_path):
    """BR-BUILD-009: drift is a hard stop, checked before any network work."""
    called: list[str] = []
    monkeypatch.setattr(build.resolve, "resolve_manifest", lambda m: called.append("resolved"))

    def _drifted(root):
        raise VendorDriftError("drifted")

    monkeypatch.setattr(build.vendor, "assert_clean", _drifted)

    with pytest.raises(VendorDriftError):
        build.plan(tmp_path, _manifest(), BuildConfig())

    assert called == []


def test_run_raises_with_the_command_on_failure(monkeypatch):
    """BR-CLI-015: a failed build reports the exact command, so it can be re-run by hand."""
    monkeypatch.setattr(build.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1})())

    with pytest.raises(BuildError, match="podman build failed with exit code 1"):
        build.run(_plan())


def test_run_succeeds_quietly(monkeypatch):
    captured: list[list[str]] = []

    def _run(command, **kwargs):
        captured.append(command)
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(build.subprocess, "run", _run)
    build.run(_plan())

    assert captured[0][0] == "podman"


# --- post-conditions and failure visibility (BR-CLI-011, BR-CLI-015) --------


def test_image_existence_is_verified_after_a_successful_exit(monkeypatch):
    """An engine that exits 0 without building must not be reported as success."""

    def _run(command, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no such image"})()

    monkeypatch.setattr(build.subprocess, "run", _run)

    with pytest.raises(BuildError, match=r"reported success but .* does not exist locally"):
        build.assert_image_exists(_plan())


def test_image_digest_is_returned_when_present(monkeypatch):
    def _run(command, **kwargs):
        return type("R", (), {"returncode": 0, "stdout": "sha256:abc\n", "stderr": ""})()

    monkeypatch.setattr(build.subprocess, "run", _run)

    assert build.assert_image_exists(_plan()) == "sha256:abc"


def test_missing_engine_binary_at_build_time_is_actionable(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("podman")

    monkeypatch.setattr(build.subprocess, "run", _raise)

    with pytest.raises(BuildError, match="not found on PATH"):
        build.run(_plan())
