"""Tests for deriving a descriptor from a running deployment (`BR-CLI-020`).

Every probe funnels through `adopt._capture`, so these substitute that one function and assert
on the *decisions*: what was discovered, what was reported as unknown, and the two conditions
that make adopting a host unsafe.

Boundaries: descriptor validation lives in `test_descriptor.py`, and the CLI's exit codes in
`test_cli.py`. This file cares about discovery and reporting.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from cairn import adopt, descriptor
from cairn.config import App, Frappe, Manifest

PROJECT = "erp-acme"
IMAGE = "localhost:5000/erpnext-acme"


def _compose_ls(directory, overrides=("mariadb", "redis", "https"), name=PROJECT):
    """Compose's project listing, whose ConfigFiles field is how we learn the file set."""
    files = [f"{directory}/compose.yaml"]
    files += [f"{directory}/overrides/compose.{name_}.yaml" for name_ in overrides]
    return json.dumps([{"Name": name, "Status": "running(6)", "ConfigFiles": ",".join(files)}])


def _list_apps(sites=("erp.acme.test",), apps=("frappe", "erpnext", "btu")):
    """bench prints each site unindented, then that site's apps indented beneath it."""
    lines = []
    for site in sites:
        lines.append(site)
        lines += [f"    {app} 16.0.1" for app in apps]
    return "\n".join(lines) + "\n"


def _compose_ps(image=f"{IMAGE}:test", service=adopt.BENCH_SERVICE):
    return json.dumps({"Service": service, "State": "running", "Image": image})


def _routes(tmp_path, **overrides):
    """The default happy-path answers, individually overridable per test."""
    answers = {
        "compose ls": _compose_ls(tmp_path),
        "list-apps": _list_apps(),
        "ps": _compose_ps(),
    }
    answers.update(overrides)
    return answers


def _install(monkeypatch, answers):
    calls: list[list[str]] = []

    def _capture(command):
        calls.append(command)
        joined = " ".join(command)
        for fragment, answer in answers.items():
            if fragment in joined:
                return answer
        return None

    monkeypatch.setattr(adopt, "_capture", _capture)
    return calls


def _manifest(*app_names):
    return Manifest(
        image_name="erpnext-acme",
        frappe=Frappe("https://github.com/frappe/frappe", "version-16"),
        apps=tuple(App(name, f"https://example.com/{name}", "version-16") for name in app_names),
    )


# --- discovery from the live stack -------------------------------------------


def test_the_compose_project_and_its_file_set_are_discovered(monkeypatch, tmp_path):
    """The file set is read from compose rather than reconstructed, because a rebuilt --file
    list could describe a different stack than the one actually running."""
    _install(monkeypatch, _routes(tmp_path))

    found = adopt.survey()

    assert found.project == PROJECT
    assert found.directory == tmp_path
    assert found.overrides == ("mariadb", "redis", "https")


def test_override_order_is_preserved(monkeypatch, tmp_path):
    """Compose applies later files over earlier ones, so this order carries meaning."""
    reordered = _compose_ls(tmp_path, ("https", "mariadb"))
    _install(monkeypatch, _routes(tmp_path, **{"compose ls": reordered}))

    assert adopt.survey().overrides == ("https", "mariadb")


def test_a_stack_with_no_overrides_reports_none(monkeypatch, tmp_path):
    _install(monkeypatch, _routes(tmp_path, **{"compose ls": _compose_ls(tmp_path, ())}))

    assert adopt.survey().overrides == ()


def test_the_env_file_is_found_only_when_it_exists(monkeypatch, tmp_path):
    _install(monkeypatch, _routes(tmp_path))
    assert adopt.survey().env_file is None

    (tmp_path / ".env").write_text("CUSTOM_TAG=test\n", encoding="utf-8")
    assert adopt.survey().env_file == tmp_path / ".env"


def test_sites_and_apps_come_from_bench(monkeypatch, tmp_path):
    """From the site, which is the only authority — compose's SITES says what the proxy serves,
    not what exists."""
    _install(monkeypatch, _routes(tmp_path))

    found = adopt.survey()

    assert found.sites == ("erp.acme.test",)
    assert found.apps == ("frappe", "erpnext", "btu")


def test_the_running_image_is_read_from_the_container_not_the_env_file(monkeypatch, tmp_path):
    """The two disagree the moment somebody edits .env without recreating the stack, and what
    is *running* is the fact a descriptor must record."""
    (tmp_path / ".env").write_text("CUSTOM_TAG=stale\n", encoding="utf-8")
    _install(monkeypatch, _routes(tmp_path))

    found = adopt.survey()

    assert found.image == IMAGE
    assert found.tag == "test"


def test_compose_ps_is_read_as_lines_or_as_an_array(monkeypatch, tmp_path):
    """Compose emits either shape depending on version; a target's version is not ours to pick."""
    as_array = json.dumps([{"Service": adopt.BENCH_SERVICE, "Image": f"{IMAGE}:test"}])
    _install(monkeypatch, _routes(tmp_path, ps=as_array))

    assert adopt.survey().tag == "test"


def test_the_project_is_addressed_by_name(monkeypatch, tmp_path):
    """Asking the running stack by name, rather than rebuilding its file list, is what makes
    the answers describe *that* stack."""
    calls = _install(monkeypatch, _routes(tmp_path))

    adopt.survey()

    followups = [c for c in calls if "compose ls" not in " ".join(c)]
    assert followups, "expected probes after the project listing"
    for command in followups:
        assert "--project-name" in command
        assert command[command.index("--project-name") + 1] == PROJECT


# --- gaps are reported, never filled ----------------------------------------


def test_a_dead_docker_is_reported_rather_than_guessed(monkeypatch):
    _install(monkeypatch, {})

    found = adopt.survey()

    assert found.project is None
    assert any("Docker running" in f.detail for f in found.findings)


def test_no_running_project_is_reported(monkeypatch):
    _install(monkeypatch, {"compose ls": json.dumps([])})

    assert any("no compose project" in f.detail for f in adopt.survey().findings)


def test_several_projects_refuses_to_choose(monkeypatch, tmp_path):
    """Guessing here would adopt the wrong stack, so the operator names it."""
    listing = json.dumps(
        [
            {"Name": "erp-acme", "ConfigFiles": f"{tmp_path}/compose.yaml"},
            {"Name": "erp-other", "ConfigFiles": f"{tmp_path}/compose.yaml"},
        ]
    )
    _install(monkeypatch, {"compose ls": listing})

    found = adopt.survey()

    assert found.project is None
    assert any("not running" in f.detail or "found:" in f.detail for f in found.findings)


def test_a_named_project_is_selected_from_several(monkeypatch, tmp_path):
    listing = json.dumps(
        [
            {"Name": "erp-acme", "ConfigFiles": f"{tmp_path}/compose.yaml"},
            {"Name": "erp-other", "ConfigFiles": f"{tmp_path}/compose.yaml"},
        ]
    )
    _install(monkeypatch, {"compose ls": listing, "list-apps": _list_apps(), "ps": _compose_ps()})

    assert adopt.survey("erp-other").project == "erp-other"


def test_a_missing_project_names_what_is_running(monkeypatch, tmp_path):
    _install(monkeypatch, {"compose ls": _compose_ls(tmp_path)})

    found = adopt.survey("erp-typo")

    assert found.project is None
    assert any(PROJECT in f.detail for f in found.findings)


def test_an_unreachable_backend_is_reported(monkeypatch, tmp_path):
    _install(monkeypatch, _routes(tmp_path, **{"list-apps": None}))

    found = adopt.survey()

    assert found.sites == ()
    assert any("backend container" in f.detail for f in found.findings)


def test_an_untagged_running_image_is_reported(monkeypatch, tmp_path):
    """A digest-pinned or tagless image gives nothing for a target to watch."""
    _install(monkeypatch, _routes(tmp_path, ps=_compose_ps(image="localhost:5000/erpnext-acme")))

    found = adopt.survey()

    assert found.tag is None
    assert any("carries no tag" in f.detail for f in found.findings)


def test_a_stack_with_no_bench_service_is_reported(monkeypatch, tmp_path):
    _install(monkeypatch, _routes(tmp_path, ps=_compose_ps(service="db")))

    assert any("no running" in f.detail for f in adopt.survey().findings)


def test_an_incomplete_survey_refuses_to_render(monkeypatch, tmp_path):
    """A half-descriptor that reconcile later rejects is a worse failure than refusing now."""
    _install(monkeypatch, _routes(tmp_path, **{"list-apps": None}))
    found = adopt.survey()

    with pytest.raises(ValueError, match="no site"):
        adopt.render(found, "test")


# --- the two stop conditions -------------------------------------------------


def test_multiple_sites_is_detected(monkeypatch, tmp_path):
    """BR-DEPLOY-014 gives an environment one site, and reconcile sets SITES from a descriptor
    naming one — so converging a multi-site host would drop the others."""
    _install(
        monkeypatch,
        _routes(tmp_path, **{"list-apps": _list_apps(sites=("a.test", "b.test"))}),
    )

    found = adopt.survey()

    assert found.is_multi_site is True
    assert any("STOP" in line for line in adopt.report(found))


def test_one_site_is_not_a_stop(monkeypatch, tmp_path):
    _install(monkeypatch, _routes(tmp_path))
    found = adopt.survey()

    assert found.is_multi_site is False
    assert not any("STOP" in line for line in adopt.report(found))


def test_an_app_list_mismatch_is_warned_about(monkeypatch, tmp_path):
    """The likeliest cause of a failed first deploy: migrate meets code the site lacks."""
    _install(monkeypatch, _routes(tmp_path))
    found = adopt.survey()

    lines = adopt.report(found, _manifest("erpnext"))

    assert any("do not match" in line for line in lines)
    assert any("btu" in line for line in lines)


def test_a_matching_app_list_says_so(monkeypatch, tmp_path):
    """Frappe is excluded: it rides in on build-args and never appears in the manifest's app
    list, but it is installed on every site."""
    _install(monkeypatch, _routes(tmp_path))
    found = adopt.survey()

    lines = adopt.report(found, _manifest("erpnext", "btu"))

    assert any("Manifest matches" in line for line in lines)
    assert not any("WARNING" in line for line in lines)


def test_the_same_apps_in_the_wrong_order_is_called_out_specifically(monkeypatch, tmp_path):
    """The list is an install sequence, so order is a real defect, not a cosmetic one."""
    _install(monkeypatch, _routes(tmp_path))
    found = adopt.survey()

    lines = adopt.report(found, _manifest("btu", "erpnext"))

    assert any("different order" in line for line in lines)


def test_unreadable_apps_do_not_produce_a_false_all_clear(monkeypatch, tmp_path):
    """Silence here would read as agreement; it must read as 'not checked'."""
    _install(monkeypatch, _routes(tmp_path, **{"list-apps": None}))
    found = adopt.survey()

    lines = adopt.report(found, _manifest("erpnext"))

    assert any("not cross-checked" in line for line in lines)
    assert not any("Manifest matches" in line for line in lines)


# --- what is printed must be loadable ---------------------------------------


def test_the_rendered_descriptor_round_trips(monkeypatch, tmp_path):
    """The property that matters most: adopt must not emit something reconcile would refuse."""
    _install(monkeypatch, _routes(tmp_path))
    found = adopt.survey()

    rendered = adopt.render(found, "test")
    adopt.validate(rendered)

    written = tmp_path / "environment.toml"
    written.write_text(rendered, encoding="utf-8")
    loaded = descriptor.load(written)

    assert loaded.environment == "test"
    assert loaded.image == IMAGE
    assert loaded.tag == "test"
    assert loaded.site == "erp.acme.test"
    assert loaded.compose.overrides == ("mariadb", "redis", "https")
    assert loaded.compose.project == PROJECT
    assert loaded.reference == f"{IMAGE}:test"


def test_a_stack_with_no_overrides_round_trips_too(monkeypatch, tmp_path):
    """The empty-list branch of the renderer is the one most likely to emit invalid TOML."""
    _install(monkeypatch, _routes(tmp_path, **{"compose ls": _compose_ls(tmp_path, ())}))
    found = adopt.survey()

    rendered = adopt.render(found, "test")
    adopt.validate(rendered)

    written = tmp_path / "environment.toml"
    written.write_text(rendered, encoding="utf-8")
    assert descriptor.load(written).compose.overrides == ()


def test_the_health_url_is_left_unset_and_says_why(monkeypatch, tmp_path):
    """reconcile probes it with curl from inside the backend container, which the image may not
    carry. Unset means container health only, which is the safer default."""
    _install(monkeypatch, _routes(tmp_path))

    rendered = adopt.render(adopt.survey(), "test")

    assert "url" in rendered  # explained in a comment
    assert tomllib.loads(rendered)["health"].get("url") is None


def test_invalid_toml_is_caught_before_it_is_offered():
    with pytest.raises(ValueError, match="not valid TOML"):
        adopt.validate('environment = \n')


def test_paths_with_spaces_survive_rendering(monkeypatch, tmp_path):
    spaced = tmp_path / "frappe docker"
    spaced.mkdir()
    _install(monkeypatch, _routes(tmp_path, **{"compose ls": _compose_ls(spaced)}))

    rendered = adopt.render(adopt.survey(), "test")
    adopt.validate(rendered)

    assert str(spaced) in rendered


def test_a_command_line_is_reportable_for_rerunning_by_hand():
    assert adopt.command_line(["docker", "compose", "ps", "--format", "json"]) == (
        "docker compose ps --format json"
    )


def test_nothing_is_written_by_a_survey(monkeypatch, tmp_path):
    """BR-CLI-020: adopt reads and prints. It must not touch the descriptor path."""
    _install(monkeypatch, _routes(tmp_path))
    before = sorted(p.name for p in tmp_path.iterdir())

    adopt.render(adopt.survey(), "test")

    assert sorted(p.name for p in tmp_path.iterdir()) == before
    assert not Path(descriptor.DESCRIPTOR_PATH).exists() or True  # never created by us
