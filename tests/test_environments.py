"""Tests for environment pointers (BR-CLI-004, BR-CLI-009, BR-DEPLOY-004/009a, ADR-052).

The registry transport is stubbed; what is under test is the declaration model — at most one
environment per manifest — and the resolve/check/retag sequence that replaces the old
selector menu.

Boundaries: the CLI's flag handling and the production prompt live in `test_cli_build.py`; the
manifest's own parsing of `[cairn] environment` lives in `test_config.py`; `build.plan()`'s own
resolution logic lives in `test_build.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cairn import build, environments, registry
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import RegistryError, UnknownEnvironmentError
from cairn.images import INPUT_HASH_LABEL

CONFIG = BuildConfig(registry="ghcr.io", namespace="datahenge")


def _manifest(environment="production"):
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "v16.0.1"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "v16.0.1"),),
        environment=environment,
    )


def _remote(digest, tag="v16"):
    return registry.RemoteImage(
        ref=registry.parse_ref(f"ghcr.io/datahenge/erpnext-btu-v16:{tag}"),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=2_750_000_000,
        labels={INPUT_HASH_LABEL: "aaa111"},
    )


def _plan():
    return build.BuildPlan(
        image_base="ghcr.io/datahenge/erpnext-btu-v16",
        primary_tag="v16-aaa111",
        moving_tag="latest",
        build_args={},
        cache_bust="x",
        labels={},
        resolution=None,  # not read by check()
        apps_json="[]",
        context=Path("/tmp"),
        containerfile=Path("/tmp/Containerfile"),
        engine_name="docker",
    )


# --- the declared environment (BR-DEPLOY-009a) ------------------------------


def test_a_declared_environment_resolves_to_a_repository_reference():
    """The environment's tag is composed onto the same base `cairn build` pushes to, so the
    pointer and the images it may point at cannot end up in different repositories."""
    declared = environments.declared(_manifest(), CONFIG)

    assert declared is not None
    assert declared.name == "production"
    assert str(declared.ref) == "ghcr.io/datahenge/erpnext-btu-v16:production"


def test_a_manifest_declaring_none_has_none():
    """Absent `[cairn] environment`, no environment exists — a fact the commands act on, not
    a gap to fill."""
    manifest = Manifest(
        image_name="erpnext-btu-v16", frappe=Frappe("u", "v16.0.1"), apps=(), environment=None
    )

    assert environments.declared(manifest, CONFIG) is None


def test_requiring_a_manifest_with_no_environment_is_refused():
    manifest = Manifest(image_name="x", frappe=Frappe("u", "v16"), apps=(), environment=None)

    with pytest.raises(UnknownEnvironmentError, match=re.escape("declares no environment")):
        environments.require(manifest, CONFIG)


def test_production_is_matched_on_the_name_case_insensitively():
    """The confirmation quotes the name back, so that is what must decide the gate."""
    assert environments.declared(_manifest("production"), CONFIG).is_production is True
    assert environments.declared(_manifest("staging"), CONFIG).is_production is False
    assert environments.declared(_manifest("PRODUCTION"), CONFIG).is_production is True


# --- Assignment: the shared retag mechanics (ADR-052) -----------------------


def test_check_known_reads_the_current_pointer_itself(monkeypatch):
    """`build --assign-tag` (`BR-CLI-002a`) supplies the digest it already resolved, but
    still needs `check_known` to read what the environment's tag *currently* points at."""
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:previous")
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")

    assignment = environments.check_known(environment, source_ref, "sha256:new")

    assert assignment.digest == "sha256:new"
    assert assignment.previous_digest == "sha256:previous"


def test_check_known_reports_creation_when_no_pointer_exists_yet():
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")
    assignment = environments.Assignment(
        environment=environment,
        source_ref=source_ref,
        digest="sha256:" + "a" * 64,
        previous_digest=None,
    )

    assert assignment.found is True
    assert assignment.is_noop is False


def test_check_known_reports_a_noop_when_already_pointing_there():
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")
    assignment = environments.Assignment(
        environment=environment,
        source_ref=source_ref,
        digest="sha256:" + "a" * 64,
        previous_digest="sha256:" + "a" * 64,
    )

    assert assignment.is_noop is True


def test_check_known_reports_a_move_when_pointing_elsewhere():
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")
    assignment = environments.Assignment(
        environment=environment,
        source_ref=source_ref,
        digest="sha256:" + "a" * 64,
        previous_digest="sha256:" + "9" * 64,
    )

    assert assignment.found is True
    assert assignment.is_noop is False


def test_render_names_the_environment_and_digest():
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")
    assignment = environments.Assignment(
        environment=environment,
        source_ref=source_ref,
        digest="sha256:" + "a" * 64,
        previous_digest="sha256:old",
    )

    rendered = assignment.render()

    assert "environment  production" in rendered
    assert "sha256:" + "a" * 64 in rendered
    assert "currently    sha256:old" in rendered


def test_render_when_nothing_matches_says_so_without_a_digest():
    environment = environments.declared(_manifest(), CONFIG)
    assignment = environments.Assignment(
        environment=environment, source_ref=None, digest=None, previous_digest=None
    )

    assert "nothing in the registry matches" in assignment.render()


# --- apply(): the server-side write (BR-DEPLOY-004) -------------------------


def test_apply_retags_server_side(monkeypatch):
    """No rebuild and no pull: the whole of deploy, promote, and rollback."""
    seen: dict = {}
    monkeypatch.setattr(
        registry,
        "retag",
        lambda source, tag: (seen.update(source=str(source), tag=tag), "sha256:done")[1],
    )
    environment = environments.declared(_manifest(), CONFIG)
    source_ref = registry.parse_ref("ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111")
    assignment = environments.Assignment(
        environment=environment, source_ref=source_ref, digest="sha256:a", previous_digest=None
    )

    digest = environments.apply(assignment)

    assert digest == "sha256:done"
    assert seen == {
        "source": "ghcr.io/datahenge/erpnext-btu-v16:v16-aaa111",
        "tag": "production",
    }


def test_apply_refuses_to_write_nothing():
    environment = environments.declared(_manifest(), CONFIG)
    assignment = environments.Assignment(
        environment=environment, source_ref=None, digest=None, previous_digest=None
    )

    with pytest.raises(AssertionError):
        environments.apply(assignment)


# --- check(): resolve, then check the registry (ADR-052) --------------------


def test_check_finds_a_match_and_reports_the_current_pointer(monkeypatch):
    """`check` reuses `build.plan()`'s own resolution, so the tag it looks for is exactly
    the one a real build of this manifest would produce."""
    monkeypatch.setattr(build, "plan", lambda manifest, build_config: _plan())
    monkeypatch.setattr(
        build, "existing_in_registry", lambda plan, build_config: _remote("sha256:found")
    )
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:old")

    assignment = environments.check(_manifest(), CONFIG)

    assert assignment.found is True
    assert assignment.digest == "sha256:found"
    assert assignment.previous_digest == "sha256:old"


def test_check_reports_nothing_found_without_touching_the_registry_tag(monkeypatch):
    monkeypatch.setattr(build, "plan", lambda manifest, build_config: _plan())
    monkeypatch.setattr(build, "existing_in_registry", lambda plan, build_config: None)

    def _absent(ref):
        raise RegistryError("does not exist")

    monkeypatch.setattr(registry, "digest_of", _absent)
    retagged = []
    monkeypatch.setattr(registry, "retag", lambda source, tag: retagged.append(tag))

    assignment = environments.check(_manifest(), CONFIG)

    assert assignment.found is False
    assert retagged == []


# --- retire (BR-CLI-009) -----------------------------------------------------


def test_retire_validates_but_removes_nothing():
    """cairn deletes no tag and edits no manifest; retirement is the operator's edit."""
    retiring = environments.retire(_manifest("staging"), CONFIG)

    assert retiring.name == "staging"


def test_retiring_a_manifest_with_no_environment_is_refused():
    manifest = Manifest(image_name="x", frappe=Frappe("u", "v16"), apps=(), environment=None)

    with pytest.raises(UnknownEnvironmentError):
        environments.retire(manifest, CONFIG)
