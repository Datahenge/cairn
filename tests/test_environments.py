"""Tests for environment pointers (BR-CLI-004, BR-CLI-009, BR-DEPLOY-004/009a).

The registry transport is stubbed; what is under test is the declaration model — which
environments exist, which pointer moves are permitted, and how a selector chooses an image.

Boundaries: the CLI's flag handling and the production prompt live in `test_cli.py`; the
manifest's own parsing of `[cairn.environments]` lives in `test_config.py`.
"""

from __future__ import annotations

import re

import pytest

from cairn import environments, registry
from cairn.config import App, BuildConfig, Frappe, Manifest
from cairn.errors import EnvironmentExistsError, RegistryError, UnknownEnvironmentError
from cairn.images import INPUT_HASH_LABEL

CONFIG = BuildConfig(registry="ghcr.io", namespace="datahenge")


def _manifest(**environments_):
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "v16.0.1"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "v16.0.1"),),
        environments=environments_ or {"production": "production", "staging": "staging"},
    )


def _remote(digest, tag="v16"):
    return registry.RemoteImage(
        ref=registry.parse_ref(f"ghcr.io/datahenge/erpnext-btu-v16:{tag}"),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=2_750_000_000,
        labels={INPUT_HASH_LABEL: "aaa111"},
    )


# --- the declared list (BR-DEPLOY-009a) -------------------------------------


def test_declared_environments_resolve_to_repository_references():
    """The environment's tag is composed onto the same base `cairn build` pushes to, so the
    pointer and the images it may point at cannot end up in different repositories."""
    declared = environments.declared(_manifest(), CONFIG)

    assert set(declared) == {"production", "staging"}
    assert str(declared["staging"].ref) == "ghcr.io/datahenge/erpnext-btu-v16:staging"


def test_a_manifest_declaring_none_has_none():
    """Absent the table, no environment exists — a fact the verbs act on, not a gap to fill."""
    manifest = Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("u", "v16.0.1"),
        apps=(),
        environments={},
    )

    assert environments.declared(manifest, CONFIG) == {}


def test_requiring_an_undeclared_environment_lists_what_exists():
    with pytest.raises(UnknownEnvironmentError, match="production, staging"):
        environments.require(_manifest(), CONFIG, "prod")


def test_requiring_one_when_none_are_declared_says_how_to_declare_one():
    manifest = Manifest(image_name="x", frappe=Frappe("u", "v16"), apps=(), environments={})

    with pytest.raises(UnknownEnvironmentError, match=re.escape("[cairn.environments]")):
        environments.require(manifest, CONFIG, "production")


def test_an_environments_tag_may_differ_from_its_name():
    """The name is what the operator types; the tag is what a registry's conventions require."""
    declared = environments.declared(_manifest(production="live"), CONFIG)

    assert declared["production"].tag == "live"
    assert declared["production"].is_production is True


def test_production_is_matched_on_the_name_not_the_tag():
    """The confirmation quotes the name back, so that is what must decide the gate."""
    declared = environments.declared(_manifest(production="stable", staging="production"), CONFIG)

    assert declared["production"].is_production is True
    assert declared["staging"].is_production is False


# --- guards (BR-CLI-009) ----------------------------------------------------


def _move(previous):
    return environments.Move(
        environment=environments.declared(_manifest(), CONFIG)["staging"],
        source=_remote("sha256:" + "a" * 64),
        previous_digest=previous,
    )


def test_creating_over_a_live_pointer_is_refused():
    """It would be a deploy wearing the word 'new'."""
    with pytest.raises(EnvironmentExistsError, match="use `cairn retag staging`"):
        environments.assert_creating(_move("sha256:" + "9" * 64))


def test_creating_a_pointer_that_does_not_exist_is_allowed():
    environments.assert_creating(_move(None))  # no exception is the assertion


def test_moving_a_pointer_that_does_not_exist_is_refused():
    with pytest.raises(UnknownEnvironmentError, match="new-tag"):
        environments.assert_moving(_move(None))


def test_moving_an_existing_pointer_is_allowed():
    environments.assert_moving(_move("sha256:" + "9" * 64))


# --- selectors (BR-CLI-004) -------------------------------------------------


@pytest.fixture
def declared_staging(monkeypatch):
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:" + "9" * 64)
    return environments.declared(_manifest(), CONFIG)["staging"]


def test_latest_picks_the_newest_candidate(declared_staging):
    newest, older = _remote("sha256:new"), _remote("sha256:old")

    move = environments.plan_move(
        declared_staging, selector=environments.Selector.LATEST, candidates=[newest, older]
    )

    assert move.source.digest == "sha256:new"


def test_latest_with_no_candidates_says_to_build_first(declared_staging):
    with pytest.raises(RegistryError, match="cairn build --push"):
        environments.plan_move(
            declared_staging, selector=environments.Selector.LATEST, candidates=[]
        )


def test_previous_skips_whatever_is_running_now(monkeypatch):
    """A rollback target is 'an image that is not the one running', which is not the same
    question as 'an image older than the current one' — a pointer may already be rolled back."""
    running = "sha256:" + "9" * 64
    monkeypatch.setattr(registry, "digest_of", lambda ref: running)
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    move = environments.plan_move(
        staging,
        selector=environments.Selector.PREVIOUS,
        candidates=[_remote(running), _remote("sha256:earlier")],
    )

    assert move.source.digest == "sha256:earlier"


def test_previous_with_nothing_earlier_is_refused(monkeypatch):
    running = "sha256:" + "9" * 64
    monkeypatch.setattr(registry, "digest_of", lambda ref: running)
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    with pytest.raises(RegistryError, match="No earlier image"):
        environments.plan_move(
            staging, selector=environments.Selector.PREVIOUS, candidates=[_remote(running)]
        )


def test_from_reads_the_source_environments_pointer(monkeypatch):
    """Promotion deploys what the upstream environment *actually runs*, which may be older
    than the newest image — that is the entire point of promoting rather than deploying."""
    inspected: list[str] = []

    def _inspect(ref):
        inspected.append(str(ref))
        return _remote("sha256:whatever-production-runs")

    monkeypatch.setattr(registry, "inspect", _inspect)
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:" + "9" * 64)
    declared = environments.declared(_manifest(), CONFIG)

    move = environments.plan_move(
        declared["staging"],
        selector=environments.Selector.FROM_ENV,
        source_environment=declared["production"],
    )

    assert move.source.digest == "sha256:whatever-production-runs"
    assert inspected == ["ghcr.io/datahenge/erpnext-btu-v16:production"]


def test_id_inspects_that_exact_tag(monkeypatch):
    inspected: list[str] = []
    monkeypatch.setattr(
        registry,
        "inspect",
        lambda ref: (inspected.append(str(ref)), _remote("sha256:named"))[1],
    )
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:" + "9" * 64)
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    environments.plan_move(
        staging, selector=environments.Selector.IDENTIFIER, identifier="v16.0.1-aaa111"
    )

    assert inspected == ["ghcr.io/datahenge/erpnext-btu-v16:v16.0.1-aaa111"]


def test_a_selector_called_without_its_argument_is_a_bug_not_user_error(declared_staging):
    """These are unreachable through the CLI, which validates first; if one fires it is
    cairn's fault and should surface as an internal error, not an actionable message."""
    with pytest.raises(ValueError, match="requires an identifier"):
        environments.plan_move(declared_staging, selector=environments.Selector.IDENTIFIER)

    with pytest.raises(ValueError, match="requires a source environment"):
        environments.plan_move(declared_staging, selector=environments.Selector.FROM_ENV)


# --- the move itself (BR-DEPLOY-004) ---------------------------------------


def test_a_nonexistent_pointer_reads_as_no_previous_digest(monkeypatch):
    """The normal state before a first deploy, and not a failure."""

    def _absent(ref):
        raise RegistryError("does not exist")

    monkeypatch.setattr(registry, "digest_of", _absent)
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    move = environments.plan_move(
        staging, selector=environments.Selector.LATEST, candidates=[_remote("sha256:a")]
    )

    assert move.previous_digest is None
    assert "does not exist yet" in move.render()


def test_a_move_onto_the_same_image_is_recognised_as_a_noop(monkeypatch):
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:same")
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    move = environments.plan_move(
        staging, selector=environments.Selector.LATEST, candidates=[_remote("sha256:same")]
    )

    assert move.is_noop is True
    assert "would change nothing" in move.render()


def test_applying_a_move_retags_server_side(monkeypatch):
    """No rebuild and no pull: the whole of deploy, promote and rollback."""
    seen: dict = {}
    monkeypatch.setattr(
        registry,
        "retag",
        lambda source, tag: (seen.update(source=str(source), tag=tag), "sha256:done")[1],
    )
    staging = environments.declared(_manifest(), CONFIG)["staging"]

    digest = environments.apply(
        environments.Move(
            environment=staging, source=_remote("sha256:a", tag="v16"), previous_digest=None
        )
    )

    assert digest == "sha256:done"
    assert seen == {"source": "ghcr.io/datahenge/erpnext-btu-v16:v16", "tag": "staging"}


def test_the_rendered_move_names_the_digest_that_will_deploy():
    """The production confirmation quotes this, so it must be the decided digest and not the
    selector that will later choose one."""
    staging = environments.declared(_manifest(), CONFIG)["staging"]
    move = environments.Move(
        environment=staging, source=_remote("sha256:" + "a" * 64), previous_digest="sha256:old"
    )

    rendered = move.render()
    assert "sha256:" + "a" * 64 in rendered
    assert "currently    sha256:old" in rendered
    assert "input hash   aaa111" in rendered


def test_retire_validates_but_removes_nothing():
    """cairn deletes no tag and edits no manifest; retirement is the operator's edit."""
    retiring = environments.retire(_manifest(), CONFIG, "staging")

    assert retiring.name == "staging"
    assert retiring.tag == "staging"


def test_retiring_an_undeclared_environment_is_refused():
    with pytest.raises(UnknownEnvironmentError, match="No such environment"):
        environments.retire(_manifest(), CONFIG, "nope")
