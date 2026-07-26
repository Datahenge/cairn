"""Tests for the command surface — exit codes and flag plumbing (BR-CLI-012, BR-CLI-015).

This file covers only what `cli.py` itself decides:

* the exit code every command leaves behind, which is `_run_in_project`'s whole job
  (BR-CLI-012: systemd and CI detect outcomes from it), and
* that each flag reaches the module that acts on it.

The work behind the flags is tested where it lives — build planning in `test_build.py`,
transcript policy in `test_transcript.py`, prune selection in `test_prune.py`, image
reporting in `test_images.py`. Where a module function is pure it is used for real here
rather than stubbed; only the boundaries that shell out are replaced.

The gap this closes: `transcript.wanted` and `prune.select` were thoroughly tested at the
module level while nothing verified the CLI passed the right arguments into them, so
tested logic sat behind untested wiring.
"""

from __future__ import annotations

import json
import runpy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairn import (
    adopt,
    build,
    cli,
    config,
    doctor,
    engine,
    images,
    prune,
    push,
    reconcile,
    registry,
    vendor,
)
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import (
    BuildError,
    ManifestNotFoundError,
    PushError,
    ReconcileError,
    RegistryError,
)
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
        frappe=ResolvedRef(
            "frappe", "https://github.com/frappe/frappe", "v16.0.1", "a" * 40, kind
        ),
        apps=(
            ResolvedRef(
                "erpnext", "https://github.com/frappe/erpnext", "v16.0.1", "b" * 40, kind
            ),
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
def project(tmp_path, monkeypatch):
    """A discovered project root, so no test needs a real vendored repo on disk."""
    monkeypatch.setattr(cli, "find_project_root", lambda: tmp_path)
    return tmp_path


@dataclass
class BuildStubs:
    """What the CLI handed each stubbed boundary, and what those boundaries hand back."""

    root: Path
    manifest_path: Path
    seen: dict = field(default_factory=dict)
    held: str | None = None  #: what `build.existing_image` finds already built
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
    monkeypatch.setattr(build, "run", _run_stub)
    monkeypatch.setattr(build, "assert_image_exists", lambda build_plan: DIGEST)
    monkeypatch.setattr(build, "tag_cache_stage", _tag_cache_stage)
    monkeypatch.setattr(
        push,
        "assert_registry_configured",
        lambda build_config: state.seen.__setitem__("registry_checked", True),
    )
    monkeypatch.setattr(
        push, "push", lambda image, engine_name: state.seen["pushed"].append(image)
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


def _manifest_with_environments(**environments):
    base = _manifest()
    return Manifest(
        image_name=base.image_name,
        frappe=base.frappe,
        apps=base.apps,
        build=base.build,
        environments=environments or {"production": "production", "staging": "staging"},
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
    monkeypatch.setattr(
        config, "find_manifest", lambda explicit=None: explicit or manifest_path
    )
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest_with_environments())
    monkeypatch.setattr(
        config,
        "load_build_config",
        lambda path=None: BuildConfig(registry="ghcr.io", namespace="datahenge"),
    )
    return manifest_path


@dataclass
class PointerStubs:
    """What the registry was asked to do, and what it reported back."""

    seen: dict = field(default_factory=dict)
    current: str | None = None  #: digest the environment's tag resolves to now
    catalog: list = field(default_factory=list)


@pytest.fixture
def pointers(registry_repo, monkeypatch) -> PointerStubs:
    state = PointerStubs(catalog=[_remote("aaa111", tags=("v16",))])

    def _digest_of(ref):
        if state.current is None:
            raise RegistryError(f"{ref} does not exist in the registry.")
        return state.current

    def _retag(source, tag):
        state.seen["retag"] = (str(source), tag)
        return source_digest(source)

    def source_digest(source):
        return next(
            (image.digest for image in state.catalog if source.tag in image.tags),
            "sha256:" + "f" * 64,
        )

    def _inspect(ref):
        return registry.RemoteImage(
            ref=ref,
            digest=source_digest(ref),
            media_type="application/vnd.oci.image.manifest.v1+json",
            size=2_750_000_000,
            labels={images.INPUT_HASH_LABEL: "aaa111"},
        )

    monkeypatch.setattr(registry, "digest_of", _digest_of)
    monkeypatch.setattr(registry, "retag", _retag)
    monkeypatch.setattr(registry, "inspect", _inspect)
    monkeypatch.setattr(images, "inspect_registry", lambda base: (state.catalog, 0))
    return state


# --- exit codes through `_run_in_project` (BR-CLI-012, BR-CLI-015) ----------


def test_success_exits_zero(project, monkeypatch):
    monkeypatch.setattr(doctor, "run", lambda preferred_engine=None, manifest_path=None: 0)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0


def test_exit_code_is_the_actions_own_return_value(project, monkeypatch):
    """BR-CLI-012: a failed check must be detectable, so the code is forwarded, not flattened."""
    monkeypatch.setattr(doctor, "run", lambda preferred_engine=None, manifest_path=None: 1)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1


def test_cairn_error_is_a_clean_message_not_a_traceback(project, monkeypatch):
    """BR-CLI-015: an expected failure names the fix; exit 2 distinguishes it from a check
    that merely reported a problem."""

    def _fail(preferred_engine=None, manifest_path=None):
        raise PushError("No registry configured, so images remain local.")

    monkeypatch.setattr(doctor, "run", _fail)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 2
    assert "Error: No registry configured" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.exception is None or isinstance(result.exception, SystemExit)


def test_interrupt_exits_130(project, monkeypatch):
    """The shell's convention for SIGINT — a cancelled build is not a failed build."""

    def _interrupt(preferred_engine=None, manifest_path=None):
        raise KeyboardInterrupt

    monkeypatch.setattr(doctor, "run", _interrupt)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 130
    assert "Interrupted." in result.stderr


def test_unexpected_exception_is_named_and_reraised(project, monkeypatch):
    """An internal error must never be mistaken for silent success, so it is announced
    and then allowed to print its traceback."""

    def _bug(preferred_engine=None, manifest_path=None):
        raise ValueError("off by one")

    monkeypatch.setattr(doctor, "run", _bug)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code != 0
    assert "Internal error (ValueError): off by one" in result.stderr
    assert isinstance(result.exception, ValueError)


def test_doctor_needs_no_project_root(tmp_path, monkeypatch):
    """The vendored tree is package-relative now — doctor works from anywhere."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "run", lambda preferred_engine=None, manifest_path=None: 0)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0


def test_vendor_status_outside_a_project_exits_two(tmp_path, monkeypatch):
    """Unlike every other command, `vendor status`/`sync` shell out to ventwig itself,
    which needs a real checkout — project discovery failing there is an ordinary,
    actionable error, not a traceback."""
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["vendor", "status"])

    assert result.exit_code == 2
    assert "No cairn project found" in result.stderr


# --- build (BR-CLI-002, BR-CLI-016, BR-CLI-017) -----------------------------


def test_dry_run_reports_the_plan_and_builds_nothing(stubs):
    result = runner.invoke(cli.app, ["build", "--dry-run"])

    assert result.exit_code == 0
    assert "build command:" in result.stdout
    assert "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20" in result.stdout
    assert "run" not in stubs.seen
    assert "Timing" not in result.stderr  # nothing took time; nothing to report


def test_dry_run_writes_no_transcript(stubs, tmp_path):
    """A transcript records a build. `--dry-run` performs none, so an explicitly named
    file must still not appear (BR-CLI-016)."""
    destination = tmp_path / "logs" / "dry.log"

    result = runner.invoke(cli.app, ["build", "--dry-run", "--transcript", str(destination)])

    assert result.exit_code == 0
    assert not destination.exists()


def test_no_cache_reaches_the_plan(stubs):
    result = runner.invoke(cli.app, ["build", "--no-cache"])

    assert result.exit_code == 0
    assert stubs.seen["plan"]["no_cache"] is True
    assert stubs.seen["run"]["plan"].no_cache is True


def test_manifest_flag_reaches_discovery(stubs, tmp_path):
    elsewhere = tmp_path / "other" / "cairn.toml"
    elsewhere.parent.mkdir()
    elsewhere.touch()

    result = runner.invoke(cli.app, ["build", "--dry-run", "--manifest", str(elsewhere)])

    assert result.exit_code == 0
    assert stubs.seen["manifest_flag"] == elsewhere


def test_contradictory_transcript_flags_are_rejected(stubs, tmp_path):
    """Asking for a transcript and refusing one is a mistake worth naming, not resolving."""
    result = runner.invoke(
        cli.app, ["build", "--transcript", str(tmp_path / "t.log"), "--no-transcript"]
    )

    assert result.exit_code == 2
    assert "run" not in stubs.seen


def test_push_checks_the_registry_before_building(stubs, monkeypatch):
    """A long build must not succeed only to fail at the last step, so the check is up
    front — and when it fails, nothing has been built."""

    def _refuse(build_config):
        raise PushError("No registry configured, so images remain local.")

    monkeypatch.setattr(push, "assert_registry_configured", _refuse)

    result = runner.invoke(cli.app, ["build", "--push"])

    assert result.exit_code == 2
    assert "run" not in stubs.seen


def test_push_uploads_every_reference(stubs):
    result = runner.invoke(cli.app, ["build", "--push"])

    assert result.exit_code == 0
    assert stubs.seen["registry_checked"] is True
    assert stubs.seen["pushed"] == [
        "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20",
        "ghcr.io/datahenge/erpnext-btu-v16:v16",
    ]


def test_already_built_inputs_are_not_rebuilt(stubs):
    """The input-hash short-circuit: rebuilding identical inputs would leave the existing
    image nameless for no gain."""
    stubs.held = DIGEST

    result = runner.invoke(cli.app, ["build"])

    assert result.exit_code == 0
    assert "Already built" in result.stdout
    assert "run" not in stubs.seen


def test_rebuild_builds_anyway(stubs):
    stubs.held = DIGEST

    result = runner.invoke(cli.app, ["build", "--rebuild"])

    assert result.exit_code == 0
    assert "run" in stubs.seen
    assert "Built ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20" in result.stdout


def test_the_cache_stage_is_named_unless_declined(stubs):
    """Naming the reusable layers is what stops them being mistaken for garbage, so it is
    the default; `--no-cache-tag` is the opt-out."""
    named = runner.invoke(cli.app, ["build"])
    assert named.exit_code == 0
    assert stubs.seen["cache_tag"] == "cairn-cache/erpnext-btu-v16:builder"

    del stubs.seen["cache_tag"]
    declined = runner.invoke(cli.app, ["build", "--no-cache-tag"])

    assert declined.exit_code == 0
    assert "cache_tag" not in stubs.seen


def test_transcript_records_the_run_and_says_where_twice(stubs, tmp_path):
    """The path is printed on the way in and again on the way out, because the first
    mention scrolled past minutes of engine output (BR-CLI-016)."""
    destination = tmp_path / "logs" / "build.log"

    result = runner.invoke(cli.app, ["build", "--transcript", str(destination)])

    assert result.exit_code == 0
    assert stubs.seen["run"]["sink"] is not None  # engine output is teed into the file
    assert result.stderr.count(f"Transcript {destination}") == 2
    assert "Built ghcr.io/datahenge/erpnext-btu-v16:v16" in destination.read_text(
        encoding="utf-8"
    )


def test_timing_is_reported_even_when_the_build_fails(stubs):
    """BR-CLI-017: "it failed after nine minutes" is as worth knowing as a success time."""
    stubs.fails = BuildError("the engine exited 1")

    result = runner.invoke(cli.app, ["build"])

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

    result = runner.invoke(cli.app, ["build"])

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

    result = runner.invoke(cli.app, ["build", "--dry-run"])

    assert result.exit_code == 0
    assert "moving branch(es): frappe@v16.0.1, erpnext@v16.0.1" in result.stderr


# --- images (BR-CLI-005, BR-CLI-013) ---------------------------------------


def test_registry_mode_needs_a_manifest_to_know_the_repository(local):
    """Which repository to read comes from the manifest; without one there is no question
    to ask, and guessing a repository would read someone else's images."""
    result = runner.invoke(cli.app, ["images"])

    assert result.exit_code == 2
    assert "--manifest" in result.stderr


def test_registry_mode_needs_a_configured_registry(registry_repo, monkeypatch):
    """Absent a registry, images stay local and there is nothing remote to read — saying so
    beats reporting an empty registry as though it were the answer."""
    monkeypatch.setattr(config, "load_build_config", lambda path=None: BuildConfig())

    result = runner.invoke(cli.app, ["images"])

    assert result.exit_code == 2
    assert "--local" in result.stderr


def test_registry_mode_reads_tags_without_pulling(registry_repo, monkeypatch):
    remote = _remote("aaa111", tags=("v16.0.1-aaa111", "v16", "production"))
    monkeypatch.setattr(images, "inspect_registry", lambda base: ([remote], 2))

    result = runner.invoke(cli.app, ["images"])

    assert result.exit_code == 0
    assert "input hash aaa111" in result.stdout
    assert "production" in result.stdout
    assert "2 other tag(s)" in result.stdout


def test_registry_json_is_parseable(registry_repo, monkeypatch):
    remote = _remote("aaa111", tags=("v16",))
    monkeypatch.setattr(images, "inspect_registry", lambda base: ([remote], 0))

    result = runner.invoke(cli.app, ["images", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repository"] == "ghcr.io/datahenge/erpnext-btu-v16"
    assert payload["groups"][0]["images"][0]["tags"] == ["v16"]


def test_local_images_are_reported_for_people_by_default(local, monkeypatch):
    monkeypatch.setattr(images, "inspect_local", lambda engine_name: ([_image("aaa")], 3))

    result = runner.invoke(cli.app, ["images", "--local"])

    assert result.exit_code == 0
    assert "input hash aaa111" in result.stdout


def test_json_output_is_parseable(local, monkeypatch):
    """BR-CLI-013: `--json` exists for CI, so stdout must be JSON and nothing else —
    progress belongs on stderr."""
    monkeypatch.setattr(images, "inspect_local", lambda engine_name: ([_image("aaa")], 3))

    result = runner.invoke(cli.app, ["images", "--local", "--json"])

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
    result = runner.invoke(cli.app, ["prune", "--dry-run"])

    assert result.exit_code == 0
    assert "doomed" not in prunable


def test_declining_the_confirmation_removes_nothing(prunable):
    """The only destructive verb cairn has, so the default answer is no."""
    result = runner.invoke(cli.app, ["prune"], input="n\n")

    assert result.exit_code == 0
    assert "doomed" not in prunable
    assert "Nothing was removed." in result.stderr


def test_yes_skips_the_confirmation(prunable):
    result = runner.invoke(cli.app, ["prune", "--yes"])

    assert result.exit_code == 0
    assert [image.short_id for image in prunable["doomed"]] == ["bbb000000000"]
    assert "Removed 1 image(s), reclaiming 2.75 GB." in result.stdout


def test_keep_reaches_the_selection(prunable):
    """`--keep 2` leaves the current image plus one predecessor, so nothing is superseded."""
    result = runner.invoke(cli.app, ["prune", "--keep", "2", "--yes"])

    assert result.exit_code == 0
    assert "doomed" not in prunable
    assert "Nothing to remove" in result.stdout


def test_keep_below_one_is_rejected(prunable):
    """`--keep 0` would delete the image in use; the floor is enforced by the option."""
    result = runner.invoke(cli.app, ["prune", "--keep", "0", "--yes"])

    assert result.exit_code == 2
    assert "doomed" not in prunable


def test_a_failed_removal_exits_nonzero_without_aborting_the_rest(prunable):
    """BR-CLI-018: one failure must not abort the others, but must still be detectable."""
    prunable["failures"] = ["bbb000000000"]

    result = runner.invoke(cli.app, ["prune", "--yes"])

    assert result.exit_code == 1
    assert "Could not remove bbb000000000" in result.stderr


# --- pointer verbs (BR-CLI-004, BR-CLI-009, BR-CLI-010, BR-DEPLOY-004) -----


def test_new_tag_creates_the_pointer(pointers):
    result = runner.invoke(cli.app, ["new-tag", "staging", "--latest"])

    assert result.exit_code == 0
    assert pointers.seen["retag"] == ("ghcr.io/datahenge/erpnext-btu-v16:v16", "staging")
    assert "staging now points at" in result.stdout


def test_new_tag_refuses_an_undeclared_environment(pointers):
    """No auto-vivification: a typo must not quietly create an environment."""
    result = runner.invoke(cli.app, ["new-tag", "stagng", "--latest"])

    assert result.exit_code == 2
    assert "No such environment 'stagng'" in result.stderr
    assert "production, staging" in result.stderr
    assert "retag" not in pointers.seen


def test_new_tag_refuses_a_pointer_that_already_exists(pointers):
    """Creating over a live pointer would be a deploy wearing the word 'new'."""
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["new-tag", "staging", "--latest"])

    assert result.exit_code == 2
    assert "already exists" in result.stderr
    assert "retag" not in pointers.seen


def test_retag_refuses_a_pointer_that_does_not_exist(pointers):
    result = runner.invoke(cli.app, ["retag", "staging", "--latest"])

    assert result.exit_code == 2
    assert "does not exist" in result.stderr
    assert "new-tag" in result.stderr
    assert "retag" not in pointers.seen


def test_retag_moves_an_existing_pointer(pointers):
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "staging", "--latest"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "staging"


def test_dry_run_moves_nothing(pointers):
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "staging", "--latest", "--dry-run"])

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert "environment  staging" in result.stdout


def test_a_pointer_already_on_the_image_is_reported_not_rewritten(pointers):
    """A retag that changes nothing still writes a manifest; saying so beats a cheerful
    success message that hides it."""
    pointers.current = pointers.catalog[0].digest

    result = runner.invoke(cli.app, ["retag", "staging", "--latest"])

    assert result.exit_code == 0
    assert "already points at" in result.stdout
    assert "retag" not in pointers.seen


def test_production_asks_before_moving(pointers):
    """BR-CLI-010: the production gate, and the default answer is no."""
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "production", "--latest"], input="n\n")

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert "The pointer was not moved." in result.stderr


def test_production_moves_when_confirmed(pointers):
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "production", "--latest"], input="y\n")

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "production"


def test_yes_skips_the_production_gate_for_automation(pointers):
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "production", "--latest", "--yes"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][1] == "production"


def test_non_production_is_not_gated(pointers):
    """The gate is deliberately narrow — every environment confirming would train the habit
    of confirming without reading."""
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "staging", "--latest"])

    assert result.exit_code == 0
    assert "retag" in pointers.seen


def test_a_selector_is_required(pointers):
    result = runner.invoke(cli.app, ["retag", "staging"])

    assert result.exit_code == 2
    assert "--latest" in result.stderr


def test_selectors_are_mutually_exclusive(pointers):
    result = runner.invoke(cli.app, ["retag", "staging", "--latest", "--previous"])

    assert result.exit_code == 2
    assert "only one of" in result.stderr.lower()


def test_from_promotes_whatever_another_environment_runs(pointers):
    """Promotion reads the *source* environment's pointer, not the newest image."""
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "staging", "--from", "production"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][0] == "ghcr.io/datahenge/erpnext-btu-v16:production"


def test_id_points_at_a_named_tag(pointers):
    pointers.current = "sha256:" + "9" * 64

    result = runner.invoke(cli.app, ["retag", "staging", "--id", "v16.0.1-aaa111"])

    assert result.exit_code == 0
    assert pointers.seen["retag"][0].endswith(":v16.0.1-aaa111")


def test_retire_touches_nothing_and_warns_the_tag_persists(pointers):
    result = runner.invoke(cli.app, ["retire", "staging"])

    assert result.exit_code == 0
    assert "retag" not in pointers.seen
    assert 'staging = "staging"' in result.stdout
    assert "will still exist" in result.stderr


def test_retire_refuses_an_undeclared_environment(pointers):
    result = runner.invoke(cli.app, ["retire", "nope"])

    assert result.exit_code == 2
    assert "No such environment 'nope'" in result.stderr


# --- reconcile (BR-CLI-008, BR-DEPLOY-003) ---------------------------------


@pytest.fixture
def target(tmp_path, monkeypatch):
    """A target host: a descriptor on disk, and a stubbed convergence."""
    path = tmp_path / "environment.toml"
    path.write_text(
        "\n".join(
            [
                'environment = "production"',
                'image = "ghcr.io/datahenge/erpnext-btu-v16"',
                'tag = "production"',
                'site = "erp.example.com"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return path


def test_reconcile_needs_no_project(target, monkeypatch):
    """A target has no manifest and no vendored tree — only the descriptor."""
    state = reconcile.State(desired_digest="sha256:aaa", running_digest=None, stack_up=False)
    monkeypatch.setattr(
        reconcile,
        "run",
        lambda desc, dry_run=False, report=None: reconcile.Outcome(
            converged=True, changed=True, state=state, detail="Converged to sha256:aaa."
        ),
    )

    result = runner.invoke(cli.app, ["reconcile", "--descriptor", str(target)])

    assert result.exit_code == 0
    assert "Converged to sha256:aaa." in result.stdout


def test_reconcile_reports_a_no_change_run_without_claiming_a_deploy(target, monkeypatch):
    """The common case under a timer. It must not read as a deployment having happened."""
    state = reconcile.State(
        desired_digest="sha256:aaa", running_digest="sha256:aaa", stack_up=True
    )
    monkeypatch.setattr(
        reconcile,
        "run",
        lambda desc, dry_run=False, report=None: reconcile.Outcome(
            converged=True, changed=False, state=state, detail="Already running sha256:aaa."
        ),
    )

    result = runner.invoke(cli.app, ["reconcile", "--descriptor", str(target)])

    assert result.exit_code == 0
    assert "Already running" in result.stderr
    assert "Converged" not in result.stdout


def test_reconcile_halts_and_reports_on_failure(target, monkeypatch):
    """BR-DEPLOY-018: it stops rather than rolling back, and the exit code says so."""

    def _fail(desc, dry_run=False, report=None):
        raise ReconcileError("Failed while running bench migrate (exit code 1).")

    monkeypatch.setattr(reconcile, "run", _fail)

    result = runner.invoke(cli.app, ["reconcile", "--descriptor", str(target)])

    assert result.exit_code == 2
    assert "Error: Failed while running bench migrate" in result.stderr
    assert "Timing" in result.stderr  # how long it ran before failing still matters


def test_a_missing_descriptor_names_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["reconcile", "--descriptor", str(tmp_path / "absent.toml")])

    assert result.exit_code == 2
    assert "absent.toml" in result.stderr


# --- systemd units (BR-CLI-019) --------------------------------------------


def test_systemd_units_are_printed_to_stdout():
    """Printed, never installed — so stdout must be the units themselves."""
    result = runner.invoke(cli.app, ["systemd-units"])

    assert result.exit_code == 0
    assert "[Timer]" in result.stdout
    assert "Type=oneshot" in result.stdout
    assert "cairn-reconcile.service" in result.stdout


def test_systemd_units_report_what_they_assumed(monkeypatch):
    """BR-CLI-019: a host-specific guess must be visible before installation, not after."""
    result = runner.invoke(cli.app, ["systemd-units", "--interval", "15min", "--user", "cairn"])

    assert result.exit_code == 0
    assert "interval     15min" in result.stderr
    assert "user         cairn" in result.stderr
    assert "OnUnitInactiveSec=15min" in result.stdout
    assert "User=cairn" in result.stdout


# --- adopt (BR-CLI-020) ----------------------------------------------------


def _survey(sites=("erp.acme.test",), apps=("frappe", "erpnext"), image="localhost:5000/erp"):
    return adopt.Survey(
        project="erp-acme",
        directory=Path("/opt/frappe_docker"),
        overrides=("mariadb", "redis"),
        sites=tuple(sites),
        apps=tuple(apps),
        image=image,
        tag="test",
    )


def test_adopt_needs_no_project_and_prints_a_descriptor(tmp_path, monkeypatch):
    """A host being adopted has neither a cairn project nor a manifest yet."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey())

    result = runner.invoke(cli.app, ["adopt", "--environment", "test"])

    assert result.exit_code == 0
    assert 'environment = "test"' in result.stdout
    assert 'site        = "erp.acme.test"' in result.stdout


def test_adopt_writes_nothing(tmp_path, monkeypatch):
    """BR-CLI-020: it reads and prints. The descriptor goes to stdout, never to disk."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey())

    runner.invoke(cli.app, ["adopt"])

    assert list(tmp_path.iterdir()) == []


def test_adopt_refuses_a_multi_site_host(tmp_path, monkeypatch):
    """Converging it would drop the other sites from the proxy config, so this is a stop."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        adopt, "survey", lambda project=None: _survey(sites=("a.test", "b.test"))
    )

    result = runner.invoke(cli.app, ["adopt"])

    assert result.exit_code == 2
    assert "serves 2 sites" in result.stderr
    assert "environment =" not in result.stdout


def test_adopt_reports_what_it_could_not_determine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    incomplete = adopt.Survey(
        findings=[adopt.Finding("compose project", "`docker compose ls` did not answer")]
    )
    monkeypatch.setattr(adopt, "survey", lambda project=None: incomplete)

    result = runner.invoke(cli.app, ["adopt"])

    assert result.exit_code == 2
    assert "did not answer" in result.stderr
    assert "Not enough could be determined" in result.stderr


def test_adopt_cross_checks_the_manifest_when_given_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey(apps=("frappe", "erpnext")))
    manifest = tmp_path / "cairn.toml"
    manifest.touch()
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest())

    result = runner.invoke(cli.app, ["adopt", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "Manifest matches" in result.stderr


def test_adopt_forwards_the_project_name(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        adopt, "survey", lambda project=None: (seen.update(project=project), _survey())[1]
    )

    runner.invoke(cli.app, ["adopt", "--project", "erp-other"])

    assert seen["project"] == "erp-other"

# --- push (BR-CLI-003) -----------------------------------------------------


def test_id_pushes_that_tag_without_resolving_refs(stubs, monkeypatch):
    monkeypatch.setattr(
        engine, "detect", lambda preferred=None: engine.BuildEngine(engine.DOCKER, "27.3.1")
    )

    def _no_planning(*args, **kwargs):
        raise AssertionError("--id names a tag directly; no ref resolution should happen")

    monkeypatch.setattr(build, "plan", _no_planning)

    result = runner.invoke(cli.app, ["push", "--id", "v16.0.1"])

    assert result.exit_code == 0
    assert stubs.seen["pushed"] == ["ghcr.io/datahenge/erpnext-btu-v16:v16.0.1"]


def test_without_id_the_manifests_own_tags_are_pushed(stubs, monkeypatch):
    """So that what is pushed is exactly what `cairn build` would have produced."""
    monkeypatch.setattr(
        engine, "detect", lambda preferred=None: engine.BuildEngine(engine.DOCKER, "27.3.1")
    )

    result = runner.invoke(cli.app, ["push"])

    assert result.exit_code == 0
    assert stubs.seen["pushed"] == [
        "ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-1b019793dc20",
        "ghcr.io/datahenge/erpnext-btu-v16:v16",
    ]


def test_a_missing_manifest_is_an_actionable_error(project, monkeypatch):
    def _missing(explicit=None):
        raise ManifestNotFoundError("No cairn.toml found at or above here.")

    monkeypatch.setattr(config, "find_manifest", _missing)

    result = runner.invoke(cli.app, ["push"])

    assert result.exit_code == 2
    assert "Error: No cairn.toml found" in result.stderr


# --- vendor (BR-CLI-006) ---------------------------------------------------


def test_vendor_status_forwards_the_source_and_its_exit_code(project, monkeypatch):
    """A thin wrapper: ventwig's exit code is authoritative and must survive the trip."""
    seen: dict = {}

    def _status(root, source=None):
        seen["args"] = (root, source)
        return 1

    monkeypatch.setattr(vendor, "status", _status)

    result = runner.invoke(cli.app, ["vendor", "status", "frappe_docker"])

    assert result.exit_code == 1
    assert seen["args"] == (project, "frappe_docker")


def test_vendor_sync_defaults_to_every_source(project, monkeypatch):
    seen: dict = {}

    def _sync(root, source=None):
        seen["args"] = (root, source)
        return 0

    monkeypatch.setattr(vendor, "sync", _sync)

    result = runner.invoke(cli.app, ["vendor", "sync"])

    assert result.exit_code == 0
    assert seen["args"] == (project, None)


# --- surfaces every command shares (BR-CLI-015) ----------------------------


@pytest.mark.parametrize(
    "command",
    [
        ["build"],
        ["push"],
        ["images"],
        ["prune"],
        ["doctor"],
        ["vendor", "status"],
        ["vendor", "sync"],
    ],
)
def test_every_command_has_help(command):
    """BR-CLI-015: `--help` everywhere, and it must not need a project to answer."""
    result = runner.invoke(cli.app, [*command, "--help"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_no_arguments_shows_help_rather_than_failing():
    """Typing `cairn` alone is a question, not an error."""
    result = runner.invoke(cli.app, [])

    assert "Usage" in result.stdout


def test_version_is_reported_without_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("cairn ")


def test_the_console_script_entry_point_runs_the_app(monkeypatch):
    """`pyproject.toml` points the `cairn` command at this function; if it stopped invoking
    the app, an installed cairn would do nothing and no other test would notice."""
    invoked = []
    monkeypatch.setattr(cli, "app", lambda: invoked.append(True))

    cli.run()

    assert invoked == [True]


def test_python_dash_m_cairn_runs_the_app(monkeypatch):
    """`python -m cairn` is a documented invocation, so its module guard must actually fire."""
    invoked = []
    monkeypatch.setattr(cli, "run", lambda: invoked.append(True))

    runpy.run_module("cairn", run_name="__main__")

    assert invoked == [True]
