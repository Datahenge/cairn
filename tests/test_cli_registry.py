"""Tests for the `cairn-registry` command surface (`BR-CLI-001` group C, `ADR-048`).

This file covers what `cli_registry.py` itself decides: exit codes, flag plumbing, and output
shape. The algorithms behind the flags are tested where they live — retention in
`test_registry_retention.py`, provisioning in `test_registry_provision.py`, the registry client
in `test_registry.py`.
"""

from __future__ import annotations

import runpy
import sys

import pytest
from typer.testing import CliRunner

from cairn import cli_registry, registry, registry_config, registry_provision, setup_runner
from cairn.errors import RegistryError

runner = CliRunner()


@pytest.fixture
def local_registry(monkeypatch):
    """A configured registry host, so commands never touch a real network."""
    config = registry_config.RegistryConfig()
    monkeypatch.setattr(registry_config, "load", lambda path=None: config)
    return config


# --- version / entry point ----------------------------------------------------


def test_version_flag_prints_the_own_program_name():
    result = runner.invoke(cli_registry.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("cairn-registry ")


def test_the_console_script_entry_point_runs_the_app(monkeypatch):
    invoked = []
    monkeypatch.setattr(cli_registry, "app", lambda: invoked.append(True))

    cli_registry.main()

    assert invoked == [True]


def test_python_dash_m_cairn_registry_runs_the_app(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cairn-registry", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("cairn.cli_registry", run_name="__main__")

    assert excinfo.value.code == 0


# --- lifecycle (BR-CLI-024) ---------------------------------------------------


def test_status_prints_the_probe_output(monkeypatch):
    monkeypatch.setattr(registry_provision, "status", lambda runner: "registry   running")

    result = runner.invoke(cli_registry.app, ["status"])

    assert result.exit_code == 0
    assert "running" in result.stdout


@pytest.mark.parametrize("command", ["start", "stop", "restart"])
def test_lifecycle_commands_succeed(monkeypatch, command):
    monkeypatch.setattr(registry_provision, command, lambda runner: None)

    result = runner.invoke(cli_registry.app, [command])

    assert result.exit_code == 0


def test_a_lifecycle_failure_is_reported_and_exits_two(monkeypatch):
    def _fail(runner):
        raise setup_runner.Aborted("docker is not installed")

    monkeypatch.setattr(registry_provision, "start", _fail)

    result = runner.invoke(cli_registry.app, ["start"])

    assert result.exit_code == 2
    assert "docker is not installed" in result.stderr


# --- images (BR-CLI-024, BR-REG-005) ------------------------------------------


def test_images_lists_repositories_and_tags(local_registry, monkeypatch):
    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16"])
    monkeypatch.setattr(registry, "tags", lambda ref: ["v16-aaaaaaaaaaaa", "production"])
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:" + "a" * 64)

    result = runner.invoke(cli_registry.app, ["images"])

    assert result.exit_code == 0
    assert "erpnext-btu-v16" in result.stderr
    assert "v16-aaaaaaaaaaaa" in result.stderr
    assert "production" in result.stderr


def test_images_json_is_valid_and_structured(local_registry, monkeypatch):
    import json

    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16"])
    monkeypatch.setattr(registry, "tags", lambda ref: ["v16-aaaaaaaaaaaa"])
    monkeypatch.setattr(registry, "digest_of", lambda ref: "sha256:" + "a" * 64)

    result = runner.invoke(cli_registry.app, ["images", "--json"])

    payload = json.loads(result.stdout)
    assert payload["registry"] == local_registry.host
    assert payload["repositories"][0]["name"] == "erpnext-btu-v16"
    assert payload["repositories"][0]["tags"][0]["tag"] == "v16-aaaaaaaaaaaa"


def test_images_with_no_repositories_says_so(local_registry, monkeypatch):
    monkeypatch.setattr(registry, "catalog", lambda host: [])

    result = runner.invoke(cli_registry.app, ["images"])

    assert result.exit_code == 0
    assert "No repositories found" in result.stderr


def test_an_unreachable_registry_is_reported_as_an_error(local_registry, monkeypatch):
    def _fail(host):
        raise RegistryError("connection refused")

    monkeypatch.setattr(registry, "catalog", _fail)

    result = runner.invoke(cli_registry.app, ["images"])

    assert result.exit_code == 2
    assert "connection refused" in result.stderr


# --- prune (BR-CLI-025, BR-REG-006/007/008) -----------------------------------


def _stub_plan(monkeypatch, plan):
    """Route `prune`'s repository loop through one fixed retention plan."""
    from cairn import registry_retention

    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16"])
    monkeypatch.setattr(registry_retention, "candidates", lambda base: [])
    monkeypatch.setattr(
        registry_retention, "select", lambda items, *, keep_last, max_age_days: plan
    )


def _one_deletion_plan():
    from cairn import registry_retention

    candidate = registry_retention.Candidate("sha256:" + "a" * 64, ("v16-aaaaaaaaaaaa",), None)
    return registry_retention.RetentionPlan(
        deletions=(candidate,), kept_by_floor=(), kept_by_age=(), protected=()
    )


def test_prune_dry_run_deletes_nothing(local_registry, monkeypatch):
    from cairn import registry_retention

    _stub_plan(monkeypatch, _one_deletion_plan())
    deleted_calls = []
    monkeypatch.setattr(registry_retention, "delete", lambda base, plan: deleted_calls.append(1))

    result = runner.invoke(cli_registry.app, ["prune", "--dry-run"])

    assert result.exit_code == 0
    assert not deleted_calls
    assert "Will delete 1 digest" in result.stderr


def test_prune_reports_but_does_not_delete_when_retention_is_disabled(local_registry, monkeypatch):
    from cairn import registry_retention

    _stub_plan(monkeypatch, _one_deletion_plan())
    deleted_calls = []
    monkeypatch.setattr(registry_retention, "delete", lambda base, plan: deleted_calls.append(1))
    assert local_registry.retention.enabled is False  # the documented default

    result = runner.invoke(cli_registry.app, ["prune", "--yes"])

    assert result.exit_code == 0
    assert not deleted_calls
    assert "retention.enabled is false" in result.stderr


def test_prune_deletes_when_enabled_and_confirmed(monkeypatch):
    from cairn import registry_retention

    enabled_config = registry_config.RegistryConfig(
        retention=registry_config.Retention(enabled=True, keep_last=10, max_age_days=90)
    )
    monkeypatch.setattr(registry_config, "load", lambda path=None: enabled_config)
    _stub_plan(monkeypatch, _one_deletion_plan())
    deleted = []
    monkeypatch.setattr(
        registry_retention, "delete", lambda base, plan: (deleted.append(plan), ([], []))[1]
    )

    result = runner.invoke(cli_registry.app, ["prune", "--yes"])

    assert result.exit_code == 0
    assert deleted


def test_prune_without_yes_asks_for_confirmation(monkeypatch):
    from cairn import registry_retention

    enabled_config = registry_config.RegistryConfig(
        retention=registry_config.Retention(enabled=True, keep_last=10, max_age_days=90)
    )
    monkeypatch.setattr(registry_config, "load", lambda path=None: enabled_config)
    _stub_plan(monkeypatch, _one_deletion_plan())
    deleted_calls = []
    monkeypatch.setattr(registry_retention, "delete", lambda base, plan: deleted_calls.append(1))

    result = runner.invoke(cli_registry.app, ["prune"], input="n\n")

    assert result.exit_code == 0
    assert not deleted_calls
    assert "Skipped" in result.stderr


def test_prune_with_nothing_to_delete_needs_no_confirmation(local_registry, monkeypatch):
    from cairn import registry_retention

    empty_plan = registry_retention.RetentionPlan(
        deletions=(), kept_by_floor=(), kept_by_age=(), protected=()
    )
    _stub_plan(monkeypatch, empty_plan)

    result = runner.invoke(cli_registry.app, ["prune", "--yes"])

    assert result.exit_code == 0
    assert "Nothing to delete" in result.stderr


# --- gc (BR-CLI-026, BR-REG-009) -----------------------------------------------


def test_gc_refuses_without_yes_or_dry_run():
    result = runner.invoke(cli_registry.app, ["gc"])

    assert result.exit_code == 2
    assert "--yes" in result.stderr


def test_gc_dry_run_runs_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(registry_provision, "gc", lambda runner: calls.append(1))

    result = runner.invoke(cli_registry.app, ["gc", "--dry-run"])

    assert result.exit_code == 0
    assert not calls


def test_gc_with_yes_runs_and_reports(monkeypatch):
    def _gc(runner):
        runner.report.done.append("garbage collection complete")

    monkeypatch.setattr(registry_provision, "gc", _gc)

    result = runner.invoke(cli_registry.app, ["gc", "--yes"])

    assert result.exit_code == 0
    assert "garbage collection complete" in result.stdout


def test_gc_warns_that_pushes_are_refused_before_running():
    result = runner.invoke(cli_registry.app, ["gc", "--dry-run"])

    assert "read-only" in result.stderr


# --- doctor (BR-CLI-007, BR-REG-011) ------------------------------------------


def test_doctor_reports_every_check(monkeypatch):
    monkeypatch.setattr(cli_registry, "_check_reachable", lambda config: ("reachable", True, "ok"))
    monkeypatch.setattr(
        cli_registry, "_check_certificate", lambda: ("certificate", False, "expired")
    )
    monkeypatch.setattr(
        cli_registry, "_check_disk_headroom", lambda config: ("disk headroom", True, "40 GB free")
    )

    result = runner.invoke(cli_registry.app, ["doctor"])

    assert result.exit_code == 1
    assert "reachable" in result.stdout
    assert "certificate" in result.stdout
    assert "disk headroom" in result.stdout
    assert "1 of 3 checks failed" in result.stderr


def test_doctor_exits_zero_when_everything_passes(monkeypatch):
    monkeypatch.setattr(cli_registry, "_check_reachable", lambda config: ("reachable", True, "ok"))
    monkeypatch.setattr(cli_registry, "_check_certificate", lambda: ("certificate", True, "ok"))
    monkeypatch.setattr(
        cli_registry, "_check_disk_headroom", lambda config: ("disk headroom", True, "ok")
    )

    result = runner.invoke(cli_registry.app, ["doctor"])

    assert result.exit_code == 0
    assert "All 3 checks passed" in result.stdout


# --- setup (BR-CLI-021, BR-REG-003) -------------------------------------------


def test_setup_is_root_gated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )

    result = runner.invoke(cli_registry.app, ["setup", "--dry-run"])

    assert result.exit_code == 2
    assert "root" in result.stderr


def test_setup_only_runs_the_named_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(
        setup_runner, "check_command", lambda r, label, c: setup_runner.Check(label, True, "ok")
    )
    monkeypatch.setattr(
        setup_runner, "_check_memory", lambda: setup_runner.Check("memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )

    result = runner.invoke(cli_registry.app, ["setup", "--only", "preflight", "--dry-run"])

    assert result.exit_code == 0
    assert "[preflight]" in result.stderr
    assert "[admin-group]" not in result.stderr


def test_setup_passes_the_private_ip_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def _stage(runner, options):
        seen["private_ip"] = options.private_ip

    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setitem(registry_provision.REGISTRY_STAGE_FUNCS, "preflight", _stage)

    runner.invoke(
        cli_registry.app, ["setup", "--only", "preflight", "--private-ip", "10.0.0.9", "--dry-run"]
    )

    assert seen["private_ip"] == "10.0.0.9"


# --- setup-timer (BR-CLI-027, BR-REG-010) -------------------------------------


def test_setup_timer_is_root_gated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )

    result = runner.invoke(cli_registry.app, ["setup-timer", "--dry-run"])

    assert result.exit_code == 2
    assert "root" in result.stderr


def test_setup_timer_runs_only_the_timer_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(registry_provision, "find_executable", lambda name: tmp_path / name)

    result = runner.invoke(cli_registry.app, ["setup-timer", "--dry-run"])

    assert result.exit_code == 0
    assert "[timers]" in result.stderr
