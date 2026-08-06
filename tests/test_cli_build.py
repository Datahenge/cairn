"""Tests for the `cairn-build` command surface — exit codes and flag plumbing
(BR-CLI-012, BR-CLI-015).

This file covers only what `cli_build.py` itself decides:

* the exit code every command leaves behind, which is `cli_support.run`'s whole job
  (BR-CLI-012: systemd and CI detect outcomes from it), and
* that each flag reaches the module that acts on it.

The work behind the flags is tested where it lives — build planning in `test_build.py`,
transcript policy in `test_transcript.py`, prune selection in `test_prune.py`, image
reporting in `test_images.py`. Where a module function is pure it is used for real here
rather than stubbed; only the boundaries that shell out are replaced.
"""

from __future__ import annotations

import json
import runpy
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairn import (
    build,
    cli_build,
    config,
    doctor,
    engine,
    images,
    prune,
    push,
    registry,
)
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import BuildError, ManifestNotFoundError, PushError, RegistryError
from cairn.images import LocalImage
from cairn.resolve import RefKind, Resolution, ResolvedRef

runner = CliRunner()

DIGEST = "sha256:" + "d" * 64


# --- builders ---------------------------------------------------------------


def _manifest():
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "v16.0.1"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "v16.0.1"),),
        build={},
    )


def _resolution(kind=RefKind.TAG):
    return Resolution(
        frappe=ResolvedRef("frappe", "https://github.com/frappe/frappe", "v16.0.1", "a" * 40, kind),
        apps=(
            ResolvedRef("erpnext", "https://github.com/frappe/erpnext", "v16.0.1", "b" * 40, kind),
        ),
    )


def _plan(root: Path, *, resolution=None, no_cache=False, engine_name=engine.DOCKER):
    return build.BuildPlan(
        image_base="ghcr.io/datahenge/erpnext-btu-v16",
        primary_tag="v16.0.1-1b019793dc20",
        moving_tag="v16",
        build_args={"PYTHON_VERSION": "3.13.1"},
        cache_bust="cafe1234",
        labels={images.INPUT_HASH_LABEL: "1b019793dc20"},
        resolution=resolution if resolution is not None else _resolution(),
        apps_json='[{"url": "https://github.com/frappe/erpnext", "branch": "v16.0.1"}]',
        context=root / "frappe_docker",
        containerfile=root / "frappe_docker" / "images" / "custom" / "Containerfile",
        engine_name=engine_name,
        no_cache=no_cache,
    )


def _image(short, tags=(), *, input_hash="aaa111", minutes_old=0, size=2_750_000_000):
    return LocalImage(
        image_id="sha256:" + short + "0" * (64 - len(short)),
        tags=tuple(tags),
        created=datetime.now(UTC) - timedelta(minutes=minutes_old),
        size=size,
        labels={
            images.INPUT_HASH_LABEL: input_hash,
            images.FRAPPE_REF_LABEL: "v16.0.1",
            images.FRAPPE_COMMIT_LABEL: "a" * 40,
        },
    )


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def project(tmp_path) -> Path:
    """A scratch directory standing in for a manifest's working directory."""
    return tmp_path


@dataclass
class BuildStubs:
    """What the CLI handed each stubbed boundary, and what those boundaries hand back."""

    root: Path
    manifest_path: Path
    seen: dict = field(default_factory=dict)
    held: str | None = None  #: what `build.existing_image` finds already built
    remote: object | None = None  #: what `build.existing_in_registry` finds, or None
    fails: Exception | None = None  #: what `build.run` raises, if anything


@pytest.fixture
def stubs(project, monkeypatch) -> BuildStubs:
    """Replace every boundary the build path shells out to, recording its arguments."""
    state = BuildStubs(root=project, manifest_path=project / "cairn.toml")
    state.manifest_path.touch()
    state.seen["pushed"] = []

    def _find_manifest(explicit=None):
        state.seen["manifest_flag"] = explicit
        return explicit or state.manifest_path

    def _plan_stub(manifest, build_config, *, no_cache=False, plain_progress=False):
        state.seen["plan"] = {
            "no_cache": no_cache,
            "plain_progress": plain_progress,
        }
        return _plan(state.root, no_cache=no_cache)

    def _run_stub(build_plan, sink=None):
        state.seen["run"] = {"plan": build_plan, "sink": sink}
        if state.fails is not None:
            raise state.fails

    def _tag_cache_stage(build_plan):
        state.seen["cache_tag"] = build_plan.cache_stage_reference
        return build_plan.cache_stage_reference

    monkeypatch.setattr(config, "find_manifest", _find_manifest)
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest())
    monkeypatch.setattr(
        config,
        "load_build_config",
        lambda path=None: BuildConfig(registry="ghcr.io", namespace="datahenge"),
    )
    monkeypatch.setattr(build, "plan", _plan_stub)
    monkeypatch.setattr(build, "existing_image", lambda build_plan: state.held)
    monkeypatch.setattr(
        build, "existing_in_registry", lambda build_plan, build_config: state.remote
    )
    monkeypatch.setattr(build, "run", _run_stub)
    monkeypatch.setattr(build, "assert_image_exists", lambda build_plan: DIGEST)
    monkeypatch.setattr(build, "tag_cache_stage", _tag_cache_stage)
    monkeypatch.setattr(
        push,
        "assert_registry_configured",
        lambda build_config: state.seen.__setitem__("registry_checked", True),
    )
    monkeypatch.setattr(push, "push", lambda image, engine_name: state.seen["pushed"].append(image))
    state.seen["released"] = []
    monkeypatch.setattr(
        push,
        "release_ownership",
        lambda image_base, engine_name: state.seen["released"].append(image_base),
    )
    return state


@pytest.fixture
def local(project, monkeypatch):
    """Machine-scoped commands: a detected engine and a fixed set of local images."""
    monkeypatch.setattr(config, "find_manifest_or_none", lambda explicit=None: None)
    monkeypatch.setattr(config, "load_build_config", lambda path=None: BuildConfig())
    monkeypatch.setattr(
        engine, "detect", lambda preferred=None: engine.BuildEngine(engine.PODMAN, "5.4.2")
    )
    return project


def _manifest_with_environment(environment="staging"):
    base = _manifest()
    return Manifest(
        image_name=base.image_name,
        frappe=base.frappe,
        apps=base.apps,
        build=base.build,
        environment=environment,
    )


def _remote(input_hash, *, tags=("v16",), size=2_750_000_000, minutes_old=0, digest=None):
    created = datetime.now(UTC) - timedelta(minutes=minutes_old)
    return images.RegistryImage(
        digest=digest or ("sha256:" + input_hash + "0" * (64 - len(input_hash))),
        tags=tuple(tags),
        size=size,
        labels={
            images.INPUT_HASH_LABEL: input_hash,
            images.FRAPPE_REF_LABEL: "v16.0.1",
            images.FRAPPE_COMMIT_LABEL: "a" * 40,
            images.CREATED_LABEL: created.strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    )


@pytest.fixture
def registry_repo(project, monkeypatch):
    """A configured registry and a discovered manifest, for the registry-side commands."""
    manifest_path = project / "cairn.toml"
    manifest_path.touch()
    monkeypatch.setattr(config, "find_manifest_or_none", lambda explicit=None: manifest_path)
    monkeypatch.setattr(config, "find_manifest", lambda explicit=None: explicit or manifest_path)
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment())
    monkeypatch.setattr(
        config,
        "load_build_config",
        lambda path=None: BuildConfig(registry="ghcr.io", namespace="datahenge"),
    )
    return manifest_path


#: The primary tag `_plan()` computes — what `environments.check()` asks the registry about.
_PRIMARY_REF = "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20"


def _found(digest):
    """What `build.existing_in_registry` returns when a matching image exists."""
    return registry.RemoteImage(
        ref=registry.parse_ref(_PRIMARY_REF),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=2_750_000_000,
        labels={images.INPUT_HASH_LABEL: "1b019793dc20"},
    )


@dataclass
class PointerStubs:
    """What `assign-tag` was asked to do, and what it reported back."""

    seen: dict = field(default_factory=dict)
    environment: str | None = "staging"  #: this manifest's declared environment
    current: str | None = None  #: digest the environment's tag resolves to now
    found: registry.RemoteImage | None = None  #: what `build.existing_in_registry` finds


@pytest.fixture
def pointers(project, monkeypatch) -> PointerStubs:
    state = PointerStubs()
    manifest_path = project / "cairn.toml"
    manifest_path.touch()

    def _load_manifest(path):
        return _manifest_with_environment(state.environment)

    def _digest_of(ref):
        if state.current is None:
            raise RegistryError(f"{ref} does not exist in the registry.")
        return state.current

    def _retag(source, tag):
        state.seen["retag"] = (str(source), tag)
        return "sha256:" + "f" * 64

    monkeypatch.setattr(config, "find_manifest", lambda explicit=None: explicit or manifest_path)
    monkeypatch.setattr(config, "load_manifest", _load_manifest)
    monkeypatch.setattr(
        config,
        "load_build_config",
        lambda path=None: BuildConfig(registry="ghcr.io", namespace="datahenge"),
    )
    monkeypatch.setattr(build, "plan", lambda manifest, build_config: _plan(project))
    monkeypatch.setattr(build, "existing_in_registry", lambda plan, build_config: state.found)
    monkeypatch.setattr(registry, "digest_of", _digest_of)
    monkeypatch.setattr(registry, "retag", _retag)
    return state


# --- exit codes through `run` (BR-CLI-012, BR-CLI-015) ----------------------


def test_success_exits_zero(project, monkeypatch):
    monkeypatch.setattr(doctor, "run_build", lambda preferred_engine=None, manifest_path=None: 0)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code == 0


def test_exit_code_is_the_actions_own_return_value(project, monkeypatch):
    """BR-CLI-012: a failed check must be detectable, so the code is forwarded, not flattened."""
    monkeypatch.setattr(doctor, "run_build", lambda preferred_engine=None, manifest_path=None: 1)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code == 1


def test_cairn_error_is_a_clean_message_not_a_traceback(project, monkeypatch):
    """BR-CLI-015: an expected failure names the fix; exit 2 distinguishes it from a check
    that merely reported a problem."""

    def _fail(preferred_engine=None, manifest_path=None):
        raise PushError("No registry configured, so images remain local.")

    monkeypatch.setattr(doctor, "run_build", _fail)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code == 2
    assert "Error: No registry configured" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_interrupt_exits_130(project, monkeypatch):
    """The shell's convention for SIGINT — a cancelled build is not a failed build."""

    def _interrupt(preferred_engine=None, manifest_path=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(doctor, "run_build", _interrupt)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code == 130
    assert "Interrupted." in result.stderr


def test_unexpected_exception_is_named_and_reraised(project, monkeypatch):
    """An internal error must never be mistaken for silent success, so it is announced
    and then allowed to print its traceback."""

    def _bug(preferred_engine=None, manifest_path=None):
        raise ValueError("off by one")

    monkeypatch.setattr(doctor, "run_build", _bug)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code != 0
    assert "Internal error (ValueError): off by one" in result.stderr
    assert isinstance(result.exception, ValueError)


def test_doctor_needs_no_project_root(tmp_path, monkeypatch):
    """The recipe tree is package-relative — doctor works from anywhere."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "run_build", lambda preferred_engine=None, manifest_path=None: 0)

    result = runner.invoke(cli_build.app, ["doctor"])

    assert result.exit_code == 0


# --- build (BR-CLI-002, BR-CLI-016, BR-CLI-017) -----------------------------


def test_dry_run_reports_the_plan_and_builds_nothing(stubs):
    result = runner.invoke(cli_build.app, ["build", "--dry-run"])

    assert result.exit_code == 0
    assert "build command:" in result.stdout
    assert "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20" in result.stdout
    assert "run" not in stubs.seen
    assert "Timing" not in result.stderr  # nothing took time; nothing to report


def test_dry_run_writes_no_transcript(stubs, tmp_path):
    """A transcript records a build. `--dry-run` performs none, so an explicitly named
    file must still not appear (BR-CLI-016)."""
    destination = tmp_path / "logs" / "dry.log"

    result = runner.invoke(cli_build.app, ["build", "--dry-run", "--transcript", str(destination)])

    assert result.exit_code == 0
    assert not destination.exists()


def test_no_cache_reaches_the_plan(stubs):
    result = runner.invoke(cli_build.app, ["build", "--no-cache"])

    assert result.exit_code == 0
    assert stubs.seen["plan"]["no_cache"] is True
    assert stubs.seen["run"]["plan"].no_cache is True


def test_manifest_flag_reaches_discovery(stubs, tmp_path):
    elsewhere = tmp_path / "other" / "cairn.toml"
    elsewhere.parent.mkdir()
    elsewhere.touch()

    result = runner.invoke(cli_build.app, ["build", "--dry-run", "--manifest", str(elsewhere)])

    assert result.exit_code == 0
    assert stubs.seen["manifest_flag"] == elsewhere


def test_contradictory_transcript_flags_are_rejected(stubs, tmp_path):
    """Asking for a transcript and refusing one is a mistake worth naming, not resolving."""
    result = runner.invoke(
        cli_build.app, ["build", "--transcript", str(tmp_path / "t.log"), "--no-transcript"]
    )

    assert result.exit_code == 2
    assert "run" not in stubs.seen


def test_push_checks_the_registry_before_building(stubs, monkeypatch):
    """A long build must not succeed only to fail at the last step, so the check is up
    front — and when it fails, nothing has been built."""

    def _refuse(build_config):
        raise PushError("No registry configured, so images remain local.")

    monkeypatch.setattr(push, "assert_registry_configured", _refuse)

    result = runner.invoke(cli_build.app, ["build", "--push"])

    assert result.exit_code == 2
    assert "run" not in stubs.seen


def test_push_uploads_every_reference(stubs):
    result = runner.invoke(cli_build.app, ["build", "--push"])

    assert result.exit_code == 0
    assert stubs.seen["registry_checked"] is True
    assert stubs.seen["pushed"] == [
        "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20",
        "ghcr.io/datahenge/erpnext-btu-v16:v16",
    ]


def test_a_successful_push_releases_ownership(stubs):
    """BR-BUILD-018: the marker is stripped once every real tag has uploaded — never itself."""
    result = runner.invoke(cli_build.app, ["build", "--push"])

    assert result.exit_code == 0
    assert stubs.seen["released"] == ["ghcr.io/datahenge/erpnext-btu-v16"]
    assert all("cairn-build-owned" not in ref for ref in stubs.seen["pushed"])


def test_a_build_only_run_never_releases_ownership(stubs):
    """No `--push`: nothing was shared, so the marker has nothing to be released from."""
    result = runner.invoke(cli_build.app, ["build"])

    assert result.exit_code == 0
    assert stubs.seen["released"] == []


def test_already_built_inputs_are_not_rebuilt(stubs):
    """The input-hash short-circuit: rebuilding identical inputs would leave the existing
    image nameless for no gain."""
    stubs.held = DIGEST

    result = runner.invoke(cli_build.app, ["build"])

    assert result.exit_code == 0
    assert "Already built" in result.stdout
    assert "run" not in stubs.seen


def test_rebuild_builds_anyway(stubs):
    stubs.held = DIGEST

    result = runner.invoke(cli_build.app, ["build", "--rebuild"])

    assert result.exit_code == 0
    assert "run" in stubs.seen
    assert "Built ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20" in result.stdout


def test_the_cache_stage_is_named_unless_declined(stubs):
    """Naming the reusable layers is what stops them being mistaken for garbage, so it is
    the default; `--no-cache-tag` is the opt-out."""
    named = runner.invoke(cli_build.app, ["build"])
    assert named.exit_code == 0
    assert stubs.seen["cache_tag"] == "cairn-cache/erpnext-btu-v16:builder"

    del stubs.seen["cache_tag"]
    declined = runner.invoke(cli_build.app, ["build", "--no-cache-tag"])

    assert declined.exit_code == 0
    assert "cache_tag" not in stubs.seen


def test_transcript_records_the_run_and_says_where_twice(stubs, tmp_path):
    """The path is printed on the way in and again on the way out, because the first
    mention scrolled past minutes of engine output (BR-CLI-016)."""
    destination = tmp_path / "logs" / "build.log"

    result = runner.invoke(cli_build.app, ["build", "--transcript", str(destination)])

    assert result.exit_code == 0
    assert stubs.seen["run"]["sink"] is not None  # engine output is teed into the file
    assert result.stderr.count(f"Transcript {destination}") == 2
    assert "Built ghcr.io/datahenge/erpnext-btu-v16:v16" in destination.read_text(encoding="utf-8")


def test_timing_is_reported_even_when_the_build_fails(stubs):
    """BR-CLI-017: "it failed after nine minutes" is as worth knowing as a success time."""
    stubs.fails = BuildError("the engine exited 1")

    result = runner.invoke(cli_build.app, ["build"])

    assert result.exit_code == 2
    assert "Timing" in result.stderr
    assert "Error: the engine exited 1" in result.stderr


def test_failing_to_name_the_cache_stage_does_not_fail_the_build(stubs, monkeypatch):
    """The image is already built and verified, so a missing courtesy name is not a reason
    to fail — but it is a reason to say so, since the protection expected is then absent."""
    monkeypatch.setattr(
        build,
        "plan",
        lambda manifest, build_config, **kwargs: _plan(stubs.root, engine_name=engine.PODMAN),
    )
    monkeypatch.setattr(build, "tag_cache_stage", lambda build_plan: None)

    result = runner.invoke(cli_build.app, ["build"])

    assert result.exit_code == 0
    assert "Built ghcr.io/datahenge/erpnext-btu-v16:v16" in result.stdout
    assert "Could not name the reusable build layers" in result.stderr


def test_a_moving_branch_is_warned_about(stubs, monkeypatch):
    """A branch still builds, but the image is not reproducible from the manifest alone."""
    monkeypatch.setattr(
        build,
        "plan",
        lambda manifest, build_config, **kwargs: _plan(
            stubs.root, resolution=_resolution(RefKind.BRANCH)
        ),
    )

    result = runner.invoke(cli_build.app, ["build", "--dry-run"])

    assert result.exit_code == 0
    assert "moving branch(es): frappe@v16.0.1, erpnext@v16.0.1" in result.stderr


# --- images (BR-CLI-005, BR-CLI-013) ---------------------------------------


def test_registry_mode_needs_a_manifest_to_know_the_repository(local):
    """Which repository to read comes from the manifest; without one there is no question
    to ask, and guessing a repository would read someone else's images."""
    result = runner.invoke(cli_build.app, ["images"])

    assert result.exit_code == 2
    assert "--manifest" in result.stderr


def test_registry_mode_needs_a_configured_registry(registry_repo, monkeypatch):
    """Absent a registry, images stay local and there is nothing remote to read — saying so
    beats reporting an empty registry as though it were the answer."""
    monkeypatch.setattr(config, "load_build_config", lambda path=None: BuildConfig())

    result = runner.invoke(cli_build.app, ["images"])

    assert result.exit_code == 2
    assert "--local" in result.stderr


def test_registry_mode_reads_tags_without_pulling(registry_repo, monkeypatch):
    remote = _remote("aaa111", tags=("v16.0.1-aaa111", "v16", "production"))
    monkeypatch.setattr(images, "inspect_registry", lambda base: ([remote], 2))

    result = runner.invoke(cli_build.app, ["images"])

    assert result.exit_code == 0
    assert "input hash aaa111" in result.stdout
    assert "production" in result.stdout
    assert "2 other tag(s)" in result.stdout


def test_registry_json_is_parseable(registry_repo, monkeypatch):
    remote = _remote("aaa111", tags=("v16",))
    monkeypatch.setattr(images, "inspect_registry", lambda base: ([remote], 0))

    result = runner.invoke(cli_build.app, ["images", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repository"] == "ghcr.io/datahenge/erpnext-btu-v16"
    assert payload["groups"][0]["images"][0]["tags"] == ["v16"]


def test_local_images_are_reported_for_people_by_default(local, monkeypatch):
    monkeypatch.setattr(images, "inspect_local", lambda engine_name: ([_image("aaa")], 3))

    result = runner.invoke(cli_build.app, ["images", "--local"])

    assert result.exit_code == 0
    assert "input hash aaa111" in result.stdout


def test_json_output_is_parseable(local, monkeypatch):
    """BR-CLI-013: `--json` exists for CI, so stdout must be JSON and nothing else —
    progress belongs on stderr."""
    monkeypatch.setattr(images, "inspect_local", lambda engine_name: ([_image("aaa")], 3))

    result = runner.invoke(cli_build.app, ["images", "--local", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["groups"][0]["input_hash"] == "aaa111"


# --- prune (BR-CLI-018) ----------------------------------------------------


@pytest.fixture
def prunable(local, monkeypatch):
    """Two images under one input hash: the tagged current one, and a superseded one."""
    current = _image("aaa", ["ghcr.io/datahenge/erpnext-btu-v16:v16"])
    superseded = _image("bbb", minutes_old=5)
    monkeypatch.setattr(images, "inspect_local", lambda engine_name: ([current, superseded], 2))
    removals: dict = {}

    def _remove(engine_name, doomed):
        removals["doomed"] = doomed
        return list(doomed), removals.get("failures", [])

    monkeypatch.setattr(prune, "remove", _remove)
    return removals


def test_dry_run_removes_nothing(prunable):
    result = runner.invoke(cli_build.app, ["prune", "--dry-run"])

    assert result.exit_code == 0
    assert "doomed" not in prunable


def test_declining_the_confirmation_removes_nothing(prunable):
    """The only destructive verb cairn-build has, so the default answer is no."""
    result = runner.invoke(cli_build.app, ["prune"], input="n\n")

    assert result.exit_code == 0
    assert "doomed" not in prunable
    assert "Nothing was removed." in result.stderr


def test_yes_skips_the_confirmation(prunable):
    result = runner.invoke(cli_build.app, ["prune", "--yes"])

    assert result.exit_code == 0
    assert [image.short_id for image in prunable["doomed"]] == ["bbb000000000"]
    assert "Removed 1 image(s), reclaiming 2.75 GB." in result.stdout


def test_keep_reaches_the_selection(prunable):
    """`--keep 2` leaves the current image plus one predecessor, so nothing is superseded."""
    result = runner.invoke(cli_build.app, ["prune", "--keep", "2", "--yes"])

    assert result.exit_code == 0
    assert "doomed" not in prunable
    assert "Nothing to remove" in result.stdout


def test_keep_below_one_is_rejected(prunable):
    """`--keep 0` would delete the image in use; the floor is enforced by the option."""
    result = runner.invoke(cli_build.app, ["prune", "--keep", "0", "--yes"])

    assert result.exit_code == 2
    assert "doomed" not in prunable


def test_a_failed_removal_exits_nonzero_without_aborting_the_rest(prunable):
    """BR-CLI-018: one failure must not abort the others, but must still be detectable."""
    prunable["failures"] = ["bbb000000000"]

    result = runner.invoke(cli_build.app, ["prune", "--yes"])

    assert result.exit_code == 1
    assert "Could not remove bbb000000000" in result.stderr


# --- assign-tag (BR-CLI-004, BR-CLI-009, BR-CLI-010, BR-DEPLOY-004, ADR-052) -----


def test_assign_tag_creates_the_pointer_when_a_match_exists(pointers):
    """The first run against a brand-new environment creates its pointer, proven by a
    matching image already in the registry — no separate 'new-tag' step, no refusal."""
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 0
    assert pointers.seen["retag"] == (_PRIMARY_REF, "staging")
    assert "did not exist — created it" in result.stdout


def test_assign_tag_refuses_a_manifest_with_no_environment(pointers):
    """No auto-vivification: a manifest with nothing declared is refused, not guessed."""
    pointers.environment = None

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 2
    assert "declares no environment" in result.stderr
    assert "retag" not in pointers.seen


def test_assign_tag_moves_an_existing_pointer(pointers):
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "staging"
    assert "moved to" in result.stdout


def test_assign_tag_reports_nothing_found_and_writes_nothing(pointers):
    """Proof, not assertion (ADR-052): with no matching image, assign-tag does nothing —
    it never triggers a build."""
    pointers.found = None

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 0
    assert "nothing in the registry matches" in result.stdout
    assert "retag" not in pointers.seen


def test_dry_run_moves_nothing(pointers):
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag", "--dry-run"])

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert "environment  staging" in result.stdout


def test_a_pointer_already_on_the_image_is_reported_not_rewritten(pointers):
    """An assign-tag that changes nothing still writes a manifest; saying so beats a
    cheerful success message that hides it."""
    pointers.found = _found("sha256:same")
    pointers.current = "sha256:same"

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 0
    assert "already points at" in result.stdout
    assert "retag" not in pointers.seen


def test_production_asks_before_moving(pointers):
    """BR-CLI-010: the production gate, and the default answer is no."""
    pointers.environment = "production"
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"], input="n\n")

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert "The pointer was not moved." in result.stderr


def test_production_gate_applies_to_creation_too(pointers):
    """Creating production's pointer for the first time is at least as consequential as
    moving it, so the gate must not be conditioned on which of the two this is."""
    pointers.environment = "production"
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"], input="n\n")

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert "Create 'production'" in result.stdout


def test_production_moves_when_confirmed(pointers):
    pointers.environment = "production"
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"], input="y\n")

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "production"


def test_yes_skips_the_production_gate_for_automation(pointers):
    pointers.environment = "production"
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag", "--yes"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "production"


def test_non_production_is_not_gated(pointers):
    """The gate is deliberately narrow — every environment confirming would train the habit
    of confirming without reading."""
    pointers.current = "sha256:" + "9" * 64
    pointers.found = _found("sha256:built")

    result = runner.invoke(cli_build.app, ["assign-tag"])

    assert result.exit_code == 0
    assert "retag" in pointers.seen


def test_retire_touches_nothing_and_warns_the_tag_persists(pointers):
    result = runner.invoke(cli_build.app, ["retire"])

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert 'environment = "staging"' in result.stdout
    assert "will still exist" in result.stderr


def test_retire_refuses_a_manifest_with_no_environment(pointers):
    pointers.environment = None

    result = runner.invoke(cli_build.app, ["retire"])

    assert result.exit_code == 2
    assert "declares no environment" in result.stderr


# --- build --assign-tag (BR-CLI-002a, ADR-052) -------------------------------


def _raise_not_found(ref):
    raise RegistryError(f"{ref} does not exist in the registry.")


def test_build_assign_tag_requires_push(stubs):
    result = runner.invoke(cli_build.app, ["build", "--assign-tag"])

    assert result.exit_code == 2
    assert "--push" in result.stderr


def test_build_assign_tag_retags_after_a_fresh_build(stubs, monkeypatch):
    """Reuses the digest `build` already resolved — no second resolve-and-check."""
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("staging"))
    monkeypatch.setattr(registry, "digest_of", _raise_not_found)
    seen = {}
    monkeypatch.setattr(
        registry, "retag", lambda source, tag: seen.setdefault("retag", (str(source), tag))
    )

    result = runner.invoke(cli_build.app, ["build", "--push", "--assign-tag", "--yes"])

    assert result.exit_code == 0
    assert seen["retag"][1] == "staging"
    assert "created it" in result.stdout


def test_build_assign_tag_gates_production(stubs, monkeypatch):
    monkeypatch.setattr(
        config, "load_manifest", lambda path: _manifest_with_environment("production")
    )
    monkeypatch.setattr(registry, "digest_of", _raise_not_found)
    seen = {}
    monkeypatch.setattr(registry, "retag", lambda source, tag: seen.setdefault("retag", tag))

    result = runner.invoke(cli_build.app, ["build", "--push", "--assign-tag"], input="n\n")

    assert result.exit_code == 0
    assert "retag" not in seen


# --- build --push defaults to --assign-tag (ADR-066) --------------------------


def test_build_push_assigns_by_default_when_an_environment_is_declared(stubs, monkeypatch):
    """`--push` alone, with no `--assign-tag`/`--no-assign-tag` given, now also retags —
    the whole point of `ADR-066`."""
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("staging"))
    monkeypatch.setattr(registry, "digest_of", _raise_not_found)
    seen = {}
    monkeypatch.setattr(
        registry, "retag", lambda source, tag: seen.setdefault("retag", (str(source), tag))
    )

    result = runner.invoke(cli_build.app, ["build", "--push", "--yes"])

    assert result.exit_code == 0
    assert seen["retag"][1] == "staging"


def test_build_push_skips_assignment_silently_with_no_declared_environment(stubs):
    """A manifest declaring no environment is the common case, not a mistake — the implicit
    default MUST NOT raise `BR-CLI-009`'s "declares no environment" error the way an explicit
    `--assign-tag` would (`ADR-066`)."""
    result = runner.invoke(cli_build.app, ["build", "--push"])

    assert result.exit_code == 0
    assert "add `[cairn] environment" not in result.stderr
    assert "nothing to point" in result.stderr


def test_build_no_assign_tag_opts_out_of_the_default(stubs, monkeypatch):
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("staging"))
    seen = {}
    monkeypatch.setattr(registry, "retag", lambda source, tag: seen.setdefault("retag", tag))

    result = runner.invoke(cli_build.app, ["build", "--push", "--no-assign-tag"])

    assert result.exit_code == 0
    assert "retag" not in seen


def test_build_no_assign_tag_without_push_is_not_a_contradiction(stubs):
    """Unlike explicit `--assign-tag`, `--no-assign-tag` alone is always consistent — it's
    the same as doing nothing extra, whether or not `--push` was given."""
    result = runner.invoke(cli_build.app, ["build", "--no-assign-tag"])

    assert result.exit_code == 0


# --- push (BR-CLI-003) -----------------------------------------------------


def test_id_pushes_that_tag_without_resolving_refs(stubs, monkeypatch):
    monkeypatch.setattr(
        engine, "detect", lambda preferred=None: engine.BuildEngine(engine.DOCKER, "27.3.1")
    )

    def _no_planning(*args, **kwargs):
        raise AssertionError("--id names a tag directly; no ref resolution should happen")

    monkeypatch.setattr(build, "plan", _no_planning)

    result = runner.invoke(cli_build.app, ["push", "--id", "v16.0.1"])

    assert result.exit_code == 0
    assert stubs.seen["pushed"] == ["ghcr.io/datahenge/erpnext-btu-v16:v16.0.1"]
    # BR-BUILD-018: --id names an explicit tag, not necessarily this manifest's current
    # build, so it must never touch the ownership marker.
    assert stubs.seen["released"] == []


def test_without_id_the_manifests_own_tags_are_pushed(stubs, monkeypatch):
    """So that what is pushed is exactly what `cairn-build build` would have produced."""
    monkeypatch.setattr(
        engine, "detect", lambda preferred=None: engine.BuildEngine(engine.DOCKER, "27.3.1")
    )

    result = runner.invoke(cli_build.app, ["push"])

    assert result.exit_code == 0
    assert stubs.seen["pushed"] == [
        "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20",
        "ghcr.io/datahenge/erpnext-btu-v16:v16",
    ]
    assert stubs.seen["released"] == ["ghcr.io/datahenge/erpnext-btu-v16"]


def test_a_missing_manifest_is_an_actionable_error(project, monkeypatch):
    def _missing(explicit=None):
        raise ManifestNotFoundError("No cairn.toml found at or above here.")

    monkeypatch.setattr(config, "find_manifest", _missing)

    result = runner.invoke(cli_build.app, ["push"])

    assert result.exit_code == 2
    assert "Error: No cairn.toml found" in result.stderr


# --- setup (BR-CLI-021) -----------------------------------------------------


def test_setup_is_root_gated(tmp_path, monkeypatch):
    """Exits reporting the shortfall rather than attempting a partial run (`BR-DEPLOY-021`)."""
    monkeypatch.chdir(tmp_path)
    from cairn import setup_runner

    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )

    result = runner.invoke(
        cli_build.app, ["setup", "--client", "acme", "--environment", "test", "--dry-run"]
    )

    assert result.exit_code == 2
    assert "root" in result.stderr


def test_setup_only_runs_the_named_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cairn import engine, provision, setup_runner

    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(
        provision.engine, "detect", lambda: engine.BuildEngine(name="docker", version="27.3.1")
    )

    def check_ok(runner, label, command):
        return setup_runner.Check(label, True, "ok")

    monkeypatch.setattr(setup_runner, "check_command", check_ok)
    monkeypatch.setattr(provision, "check_command", check_ok)
    monkeypatch.setattr(
        setup_runner, "check_memory", lambda: setup_runner.Check("memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )

    result = runner.invoke(
        cli_build.app,
        ["setup", "--client", "acme", "--environment", "test", "--only", "preflight", "--dry-run"],
    )

    assert result.exit_code == 0
    assert "[preflight]" in result.stderr
    assert "[admin-group]" not in result.stderr


def test_setup_requires_a_client_name(tmp_path, monkeypatch):
    """No default client (`BR-CLI-022`) — omitting it is a usage error, not a guess."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli_build.app, ["setup", "--environment", "test", "--dry-run"])

    assert result.exit_code != 0
    assert "--client" in result.stderr


def test_setup_requires_an_environment_name(tmp_path, monkeypatch):
    """A manifest declares at most one environment (`ADR-052`) — the scaffolded file needs
    to know which, up front, not as an afterthought edit."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli_build.app, ["setup", "--client", "acme", "--dry-run"])

    assert result.exit_code != 0
    assert "--environment" in result.stderr


# --- setup-timer (BR-CLI-023, ADR-047, ADR-052) ------------------------------


def test_setup_timer_is_root_gated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cairn import setup_runner

    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("test"))
    manifest_path = tmp_path / "cairn_test.toml"
    manifest_path.touch()

    result = runner.invoke(
        cli_build.app, ["setup-timer", "--manifest", str(manifest_path), "--dry-run"]
    )

    assert result.exit_code == 2
    assert "root" in result.stderr


def test_setup_timer_requires_a_manifest_with_an_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest())  # environment=None
    manifest_path = tmp_path / "cairn_test.toml"
    manifest_path.touch()

    result = runner.invoke(
        cli_build.app, ["setup-timer", "--manifest", str(manifest_path), "--dry-run"]
    )

    assert result.exit_code != 0
    assert "declares no environment" in result.stderr


def test_setup_timer_runs_only_the_timer_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cairn import provision, setup_runner

    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(provision, "find_executable", lambda name: tmp_path / name)
    monkeypatch.setattr(provision, "MANIFEST_ROOT", tmp_path / "srv" / "cairn")
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("test"))
    manifest_path = tmp_path / "srv" / "cairn" / "acme" / "cairn_test.toml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.touch()

    result = runner.invoke(
        cli_build.app, ["setup-timer", "--manifest", str(manifest_path), "--dry-run"]
    )

    assert result.exit_code == 0
    assert "[timers]" in result.stderr
    assert "[preflight]" not in result.stderr
    assert "[admin-group]" not in result.stderr


def test_setup_timer_requires_the_manifest_under_a_client_directory(tmp_path, monkeypatch):
    """A manifest outside `MANIFEST_ROOT/<client>/` can't yield a safe, collision-free unit
    name (`ADR-052`, `ADR-062`), so `setup-timer` stops rather than guessing."""
    monkeypatch.chdir(tmp_path)
    from cairn import provision, setup_runner

    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(provision, "find_executable", lambda name: tmp_path / name)
    monkeypatch.setattr(provision, "MANIFEST_ROOT", tmp_path / "srv" / "cairn")
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environment("test"))
    manifest_path = tmp_path / "cairn_test.toml"
    manifest_path.touch()

    result = runner.invoke(
        cli_build.app, ["setup-timer", "--manifest", str(manifest_path), "--dry-run"]
    )

    assert result.exit_code == 2
    assert "srv" in result.stderr and "cairn" in result.stderr


# --- surfaces every command shares (BR-CLI-015) ----------------------------


@pytest.mark.parametrize(
    "command",
    [
        ["build"],
        ["push"],
        ["images"],
        ["prune"],
        ["doctor"],
        ["setup"],
    ],
)
def test_every_command_has_help(command):
    """BR-CLI-015: `--help` everywhere, and it must not need a project to answer."""
    result = runner.invoke(cli_build.app, [*command, "--help"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_no_arguments_shows_help_rather_than_failing():
    """Typing `cairn-build` alone is a question, not an error."""
    result = runner.invoke(cli_build.app, [])

    assert "Usage" in result.stdout


def test_version_is_reported_without_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli_build.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("cairn-build ")


def test_the_console_script_entry_point_runs_the_app(monkeypatch):
    """`pyproject.toml` points the `cairn-build` command at this function; if it stopped
    invoking the app, an installed cairn-build would do nothing and no other test would
    notice."""
    invoked = []
    monkeypatch.setattr(cli_build, "app", lambda: invoked.append(True))

    cli_build.main()

    assert invoked == [True]


def test_python_dash_m_cairn_build_runs_the_app(monkeypatch):
    """`python -m cairn.cli_build` is a documented invocation, so its module guard must
    actually fire — proven by letting it really run `--help` and checking it exits 0,
    since a fresh `runpy` execution has its own module namespace to monkeypatch into."""
    monkeypatch.setattr(sys, "argv", ["cairn-build", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("cairn.cli_build", run_name="__main__")

    assert excinfo.value.code == 0
