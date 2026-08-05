"""Tests for build planning, provenance, and invocation (BR-BUILD-009/010/011/012)."""

from __future__ import annotations

import io
import json
import shlex
from pathlib import Path

import pytest

from cairn import __version__, build, github_auth, registry, transcript, vendor
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import BuildError, VendorInputsMissingError
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


def _labels(monkeypatch, recipe_commit="d4a3100"):
    monkeypatch.setattr(vendor, "recipe_commit", lambda: recipe_commit)
    return build.provenance_labels(
        _manifest(), _resolution(), {"PYTHON_VERSION": "3.13.1"}, "v16-abc123", "latest"
    )


def test_labels_use_the_decided_namespaces(monkeypatch):
    """ADR-030: cairn keys under com.datahenge.cairn.*, standard fields under OCI."""
    labels = _labels(monkeypatch)

    assert labels["org.opencontainers.image.title"] == "erpnext-btu-v16"
    assert labels["org.opencontainers.image.version"] == "v16-abc123"
    assert labels["com.datahenge.cairn.input-hash"] == "abc123"


def test_vendor_label_is_not_set(monkeypatch):
    """ADR-030: the distributing entity of the operator's image is theirs to declare."""
    assert "org.opencontainers.image.vendor" not in _labels(monkeypatch)


def test_apps_label_is_json_in_manifest_order(monkeypatch):
    """BR-BUILD-011 + BR-BUILD-003: apps travel with refs and commits, ordered."""
    apps = json.loads(_labels(monkeypatch)["com.datahenge.cairn.apps"])

    assert apps == [
        {
            "name": "erpnext",
            "url": "https://github.com/frappe/erpnext",
            "ref": "version-16",
            "commit": "b" * 40,
        }
    ]


def test_recipe_provenance_reaches_the_labels(monkeypatch):
    """BR-BUILD-011: the owned recipe's provenance (ADR-030, ADR-059) comes from
    vendor.recipe_commit() and cairn's own version — there is no separate upstream pin."""
    labels = _labels(monkeypatch, recipe_commit="d4a3100")

    assert labels["com.datahenge.cairn.frappe-docker.ref"] == __version__
    assert labels["com.datahenge.cairn.frappe-docker.commit"] == "d4a3100"


def test_missing_recipe_commit_degrades_to_empty(monkeypatch):
    """recipe_commit() is best-effort (empty in an installed wheel); provenance follows."""
    labels = _labels(monkeypatch, recipe_commit="")

    assert labels["com.datahenge.cairn.frappe-docker.commit"] == ""


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
        context=Path("/recipe/frappe_docker"),
        containerfile=Path("/recipe/frappe_docker/images/custom/Containerfile"),
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


def test_attended_docker_builds_request_plain_progress():
    """BR-CLI-016: BuildKit's TTY display redraws lines, ruining scrollback and any file."""
    assert "--progress=plain" not in _plan(engine_name="docker").command(Path("/x"))
    assert "--progress=plain" in _plan(engine_name="docker", plain_progress=True).command(
        Path("/x")
    )


def test_podman_is_never_given_a_progress_flag():
    """podman builds with buildah, which has no --progress and is already append-only."""
    assert "--progress=plain" not in _plan(engine_name="podman", plain_progress=True).command(
        Path("/x")
    )


def test_dry_run_render_shows_everything_without_building():
    """BR-BUILD-012: resolved apps.json, the exact command, tags, and intended provenance."""
    report = _plan().render()

    assert "apps.json" in report
    assert "ghcr.io/datahenge/erpnext-btu-v16:v16-abc123" in report
    assert "com.datahenge.cairn.input-hash=abc123" in report
    assert "podman build" in report
    assert "(moving)" in report  # branch pins are flagged, BR-BUILD-005


# --- private github.com apps (BR-BUILD-016) ----------------------------------


def test_apps_json_secret_is_unchanged_without_a_token(monkeypatch):
    monkeypatch.delenv(github_auth.GITHUB_TOKEN_ENV_VAR, raising=False)
    plan = _plan(apps_json='[{"url": "https://github.com/clientorg/btu", "branch": "main"}]\n')

    assert plan.apps_json_secret == plan.apps_json


def test_apps_json_secret_authenticates_a_github_app(monkeypatch):
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    plan = _plan(apps_json='[{"url": "https://github.com/clientorg/btu", "branch": "main"}]\n')

    assert "ghp_secret@github.com" in plan.apps_json_secret
    assert "ghp_secret" not in plan.apps_json, "the plain field must never carry the token"


def test_apps_json_secret_leaves_a_non_github_app_alone(monkeypatch):
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    plan = _plan(apps_json='[{"url": "https://gitlab.com/clientorg/btu", "branch": "main"}]\n')

    assert "ghp_secret" not in plan.apps_json_secret


def test_dry_run_render_never_shows_the_token(monkeypatch):
    """`--dry-run` (BR-BUILD-012) prints `apps_json`, never `apps_json_secret`."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    plan = _plan(apps_json='[{"url": "https://github.com/clientorg/btu", "branch": "main"}]\n')

    assert "ghp_secret" not in plan.render()


def test_run_writes_the_authenticated_apps_json_to_the_real_secret_file(monkeypatch):
    """The one place `apps_json_secret` actually matters: what bench reads during the build."""
    monkeypatch.setenv(github_auth.GITHUB_TOKEN_ENV_VAR, "ghp_secret")
    contents: dict[str, str] = {}

    def _run(command, **kwargs):
        secret_flag = next(part for part in command if part.startswith("id=apps_json"))
        path = Path(secret_flag.split("src=", 1)[1])
        contents["apps_json"] = path.read_text(encoding="utf-8")
        return type("R", (), {"returncode": 0})()

    monkeypatch.setattr(build.subprocess, "run", _run)
    plan = _plan(apps_json='[{"url": "https://github.com/clientorg/btu", "branch": "main"}]\n')
    build.run(plan)

    assert "ghp_secret@github.com" in contents["apps_json"]


# --- preconditions and failure (BR-BUILD-009) -------------------------------


def test_plan_enforces_vendor_preconditions_before_resolving(monkeypatch):
    """BR-BUILD-009: missing build inputs are a hard stop, checked before any network work."""
    called: list[str] = []
    monkeypatch.setattr(build.resolve, "resolve_manifest", lambda m: called.append("resolved"))

    def _incomplete():
        raise VendorInputsMissingError("missing")

    monkeypatch.setattr(build.vendor, "assert_build_inputs", _incomplete)

    with pytest.raises(VendorInputsMissingError):
        build.plan(_manifest(), BuildConfig())

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


def test_engine_output_is_teed_to_terminal_and_transcript(monkeypatch, capsys, tmp_path):
    """BR-CLI-016: the transcript is *in addition to* live output, never instead of it."""
    engine_output = "#1 [base 1/3] FROM python:3.14.2\n#2 DONE 0.1s\n"

    class _Process:
        def __init__(self, *args, **kwargs):
            self.stdout = io.StringIO(engine_output)

        def wait(self):
            return 0

    monkeypatch.setattr(build.subprocess, "Popen", _Process)

    path = tmp_path / "build.log"
    with transcript.recording(path) as recorder:
        build.run(_plan(), recorder)

    assert capsys.readouterr().err == engine_output  # still live on the terminal
    assert path.read_text(encoding="utf-8") == engine_output  # and saved


def test_a_teed_build_still_fails_on_a_nonzero_exit(monkeypatch, tmp_path):
    class _Process:
        def __init__(self, *args, **kwargs):
            self.stdout = io.StringIO("")

        def wait(self):
            return 7

    monkeypatch.setattr(build.subprocess, "Popen", _Process)

    path = tmp_path / "build.log"
    with pytest.raises(BuildError, match="exit code 7"), transcript.recording(path) as recorder:
        build.run(_plan(), recorder)


# --- one image per input hash (BR-BUILD-014, ADR-032) -----------------------


def test_an_existing_primary_tag_is_reported_not_rebuilt(monkeypatch):
    """The tag is a function of every resolved input, so its presence proves them unchanged."""

    def _run(command, **kwargs):
        assert command[:3] == ["podman", "image", "inspect"]
        return type("R", (), {"returncode": 0, "stdout": "sha256:abc\n", "stderr": ""})()

    monkeypatch.setattr(build.subprocess, "run", _run)

    assert build.existing_image(_plan()) == "sha256:abc"


def test_a_missing_primary_tag_reads_as_nothing_built(monkeypatch):
    def _run(command, **kwargs):
        return type("R", (), {"returncode": 1, "stdout": "", "stderr": "no such image"})()

    monkeypatch.setattr(build.subprocess, "run", _run)

    assert build.existing_image(_plan()) is None


def test_the_existence_check_asks_about_the_primary_tag(monkeypatch):
    """Not `latest`: the moving tag says nothing about which inputs produced it."""
    seen: list[str] = []

    def _run(command, **kwargs):
        seen.append(command[-1])
        return type("R", (), {"returncode": 0, "stdout": "sha256:abc\n", "stderr": ""})()

    monkeypatch.setattr(build.subprocess, "run", _run)
    build.existing_image(_plan())

    assert seen == ["ghcr.io/datahenge/erpnext-btu-v16:v16-abc123"]


# --- registry-side fallback (BR-BUILD-014a, ADR-052) -------------------------


def test_existing_in_registry_finds_a_remote_match(monkeypatch):
    """The primary tag is exactly as deterministic remotely as it is locally, so a cold
    local cache costs a registry read instead of a rebuild."""
    monkeypatch.setattr(registry, "inspect_or_none", lambda ref: _remote_image("sha256:remote"))

    found = build.existing_in_registry(_plan(), BuildConfig(registry="ghcr.io"))

    assert found is not None
    assert found.digest == "sha256:remote"


def test_existing_in_registry_reports_nothing_without_a_configured_registry():
    """Nothing to check against — asking would be a request to a registry the operator
    never chose (`BR-CFG-009`)."""
    assert build.existing_in_registry(_plan(), BuildConfig()) is None


def test_existing_in_registry_checks_the_primary_tag(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(
        registry,
        "inspect_or_none",
        lambda ref: (seen.append(str(ref)), None)[1],
    )

    build.existing_in_registry(_plan(), BuildConfig(registry="ghcr.io"))

    assert seen == ["ghcr.io/datahenge/erpnext-btu-v16:v16-abc123"]


def _remote_image(digest):
    return registry.RemoteImage(
        ref=registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-abc123"),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=1,
        labels={},
    )


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


# --- naming the build-cache stage (BR-BUILD-015, ADR-027 amended) ------------


def test_cache_stage_is_named_under_a_self_explaining_repository():
    assert _plan().cache_stage_reference == "cairn-cache/erpnext-btu-v16:builder"


def test_cache_stage_pass_targets_the_builder_stage():
    command = _plan().cache_stage_command(Path("/tmp/apps.json"))

    assert command[:4] == ["podman", "build", "--target", "builder"]
    assert "--tag" in command
    assert "cairn-cache/erpnext-btu-v16:builder" in command


def test_cache_stage_pass_never_ignores_the_cache():
    """It exists to name what the build just produced; --no-cache would rebuild it."""
    command = _plan(no_cache=True).cache_stage_command(Path("/x"))

    assert "--no-cache" not in command


def test_cache_stage_pass_carries_no_labels():
    """Labels belong to a finished image, and a stage is not one."""
    command = _plan().cache_stage_command(Path("/x"))

    assert "--label" not in command


def test_cache_stage_pass_keeps_the_build_args_that_key_the_cache():
    command = _plan().cache_stage_command(Path("/x"))

    assert "PYTHON_VERSION=3.13.1" in command
    assert "CACHE_BUST=deadbeef" in command


def test_docker_is_never_asked_to_materialize_a_stage(monkeypatch):
    """BuildKit has no stage image; --target would create GB that otherwise never exist."""
    called: list[list[str]] = []
    monkeypatch.setattr(build.subprocess, "run", lambda c, **k: called.append(c))

    assert build.tag_cache_stage(_plan(engine_name="docker")) is None
    assert called == []


def test_tagging_reports_the_reference_on_success(monkeypatch):
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda c, **k: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    assert build.tag_cache_stage(_plan()) == "cairn-cache/erpnext-btu-v16:builder"


def test_a_failed_tagging_pass_does_not_fail_the_build(monkeypatch):
    """The image is already built and verified; a courtesy name is not worth failing over."""
    monkeypatch.setattr(
        build.subprocess,
        "run",
        lambda c, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": "boom"})(),
    )

    assert build.tag_cache_stage(_plan()) is None


def test_a_hung_tagging_pass_is_abandoned_not_awaited(monkeypatch):
    """A cold cache here means a full bench init — bound it rather than wear it."""

    def _timeout(command, **kwargs):
        raise build.subprocess.TimeoutExpired(command, build.CACHE_TAG_TIMEOUT_SECONDS)

    monkeypatch.setattr(build.subprocess, "run", _timeout)

    assert build.tag_cache_stage(_plan()) is None


# --- the legible tag half reaches the plan (BR-BUILD-008, `ADR-032`) ---------


def test_a_declared_series_names_the_built_image(monkeypatch, containerfile, tmp_path):
    """The manifest's series must actually reach the tag; otherwise it is a setting that
    validates, documents itself, and does nothing."""
    plan = _planned(monkeypatch, containerfile, tmp_path, series="v16")

    assert plan.primary_tag.startswith("v16-")


def test_without_a_series_the_ref_still_names_the_image(monkeypatch, containerfile, tmp_path):
    """The fallback keeps a manifest predating `series` producing the names it always did."""
    plan = _planned(monkeypatch, containerfile, tmp_path, series=None)

    assert plan.primary_tag.startswith("v16-")  # derived from "version-16"


def test_the_series_does_not_change_the_cache_bust(monkeypatch, containerfile, tmp_path):
    """Renaming a line of images is not a reason to re-clone every app."""
    named = _planned(monkeypatch, containerfile, tmp_path, series="v16")
    renamed = _planned(monkeypatch, containerfile, tmp_path, series="erpnext16")

    assert named.cache_bust == renamed.cache_bust
    assert named.primary_tag.rpartition("-")[2] == renamed.primary_tag.rpartition("-")[2]
    assert named.primary_tag != renamed.primary_tag


def _planned(monkeypatch, containerfile, tmp_path, *, series):
    """Build a real BuildPlan with the vendor and resolve boundaries stubbed."""
    manifest = Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "version-16"),),
        build={},
        series=series,
    )
    monkeypatch.setattr(vendor, "assert_build_inputs", lambda: None)
    monkeypatch.setattr(vendor, "containerfile_path", lambda: containerfile)
    monkeypatch.setattr(vendor, "build_context", lambda: tmp_path)
    monkeypatch.setattr(vendor, "recipe_commit", lambda: "d4a3100")
    monkeypatch.setattr(build.resolve, "resolve_manifest", lambda m: _resolution())
    return build.plan(manifest, BuildConfig(), engine_name="docker")
