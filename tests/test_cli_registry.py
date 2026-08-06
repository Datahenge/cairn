"""Tests for the `cairn-registry` command surface (`BR-CLI-001` group C, `ADR-048`).

This file covers what `cli_registry.py` itself decides: exit codes, flag plumbing, and output
shape. The algorithms behind the flags are tested where they live — retention in
`test_registry_retention.py`, provisioning in `test_registry_provision.py`, the registry client
in `test_registry.py`, and `images`' provenance-reading/grouping in `test_images.py`.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairn import cli_registry, images, registry, registry_config, registry_provision, setup_runner
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


# --- images (BR-CLI-024, BR-REG-005, ADR-069) ---------------------------------
#
# What cli_registry.py itself decides: flag plumbing, the catalog-vs-direct-lookup split,
# and output shape. The provenance-reading/grouping algorithm behind each repository is
# `images.inspect_registry`/`group_registry`, tested where it lives — `test_images.py`.


def _remote_image(digest, labels, size=2_750_000_000):
    return registry.RemoteImage(
        ref=registry.parse_ref(f"placeholder.example/x:{digest[:6]}"),
        digest=digest,
        media_type="application/vnd.oci.image.manifest.v1+json",
        size=size,
        labels=labels,
    )


def _cairn_labels(input_hash="aaa111", created="2026-07-25T10:00:00Z"):
    return {
        images.INPUT_HASH_LABEL: input_hash,
        images.FRAPPE_REF_LABEL: "v16.0.1",
        images.FRAPPE_COMMIT_LABEL: "a" * 40,
        images.CREATED_LABEL: created,
    }


def _stub_repositories(monkeypatch, repos):
    """*repos*: ``{repository_name: (tags, {tag: RemoteImage_or_Exception})}``."""

    def _tags(ref):
        return repos[ref.repository][0]

    def _inspect(ref):
        answer = repos[ref.repository][1][ref.tag]
        if isinstance(answer, Exception):
            raise answer
        return answer

    monkeypatch.setattr(registry, "tags", _tags)
    monkeypatch.setattr(registry, "inspect", _inspect)


def test_images_lists_repositories_with_provenance(local_registry, monkeypatch):
    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16"])
    _stub_repositories(
        monkeypatch,
        {
            "erpnext-btu-v16": (
                ["v16-aaaaaaaaaaaa", "production"],
                {
                    "v16-aaaaaaaaaaaa": _remote_image("sha256:" + "a" * 64, _cairn_labels()),
                    "production": _remote_image("sha256:" + "a" * 64, _cairn_labels()),
                },
            )
        },
    )

    result = runner.invoke(cli_registry.app, ["images"])

    assert result.exit_code == 0
    assert f"Registry {local_registry.host}" in result.stderr
    assert f"Repository {local_registry.host}/erpnext-btu-v16" in result.stderr
    assert "v16-aaaaaaaaaaaa" in result.stderr and "production" in result.stderr
    assert "v16.0.1" in result.stderr  # frappe ref, from BR-BUILD-011's labels


def test_the_registry_is_printed_once_not_per_repository(local_registry, monkeypatch):
    """A target descriptor's `registry_host` and `image` are separate fields (`BR-DEPLOY-010`)
    — the registry is one fact about the whole listing, not repeated per repository line."""
    monkeypatch.setattr(registry, "catalog", lambda host: ["acme/erpnext-v16", "acme/other"])
    _stub_repositories(
        monkeypatch,
        {
            "acme/erpnext-v16": (
                ["latest"], {"latest": _remote_image("sha256:" + "a" * 64, _cairn_labels())}
            ),
            "acme/other": (
                ["latest"], {"latest": _remote_image("sha256:" + "b" * 64, _cairn_labels())}
            ),
        },
    )

    result = runner.invoke(cli_registry.app, ["images"])

    assert result.stderr.count(f"Registry {local_registry.host}") == 1
    repository_lines = [
        line for line in result.stderr.splitlines() if line.startswith("Repository")
    ]
    assert repository_lines == [
        f"Repository {local_registry.host}/acme/erpnext-v16",
        f"Repository {local_registry.host}/acme/other",
    ]


def test_repositories_with_no_cairn_images_are_counted_not_listed(local_registry, monkeypatch):
    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16", "someone-elses"])
    _stub_repositories(
        monkeypatch,
        {
            "erpnext-btu-v16": (
                ["v16"], {"v16": _remote_image("sha256:" + "a" * 64, _cairn_labels())}
            ),
            "someone-elses": (["latest"], {"latest": _remote_image("sha256:" + "b" * 64, {})}),
        },
    )

    result = runner.invoke(cli_registry.app, ["images"])

    assert "Repository" + f" {local_registry.host}/erpnext-btu-v16" in result.stderr
    assert "someone-elses" not in result.stderr
    assert "1 other repositories" in result.stderr


def test_images_json_is_valid_and_structured(local_registry, monkeypatch):
    monkeypatch.setattr(registry, "catalog", lambda host: ["erpnext-btu-v16"])
    _stub_repositories(
        monkeypatch,
        {
            "erpnext-btu-v16": (
                ["v16-aaaaaaaaaaaa", "production"],
                {
                    "v16-aaaaaaaaaaaa": _remote_image("sha256:" + "a" * 64, _cairn_labels()),
                    "production": _remote_image("sha256:" + "a" * 64, _cairn_labels()),
                },
            )
        },
    )

    result = runner.invoke(cli_registry.app, ["images", "--json"])

    payload = json.loads(result.stdout)
    assert payload["registry"] == local_registry.host
    repo = payload["repositories"][0]
    assert repo["repository"] == f"{local_registry.host}/erpnext-btu-v16"
    image = repo["groups"][0]["images"][0]
    assert image["digest"] == "sha256:" + "a" * 64  # full digest, not truncated
    assert image["tags"] == ["production", "v16-aaaaaaaaaaaa"]
    assert payload["repositories_without_cairn_images"] == 0


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


def test_host_option_overrides_this_machines_own_registry(local_registry, monkeypatch):
    seen = []

    def _catalog(host):
        seen.append(host)
        return []

    monkeypatch.setattr(registry, "catalog", _catalog)

    result = runner.invoke(cli_registry.app, ["images", "--host", "registry.example.com:5000"])

    assert seen == ["registry.example.com:5000"]
    assert "registry.example.com:5000" in result.stderr


def test_namespace_and_image_filter_the_catalog(local_registry, monkeypatch):
    """A glob `--image` still enumerates via the catalog — only an exact `--namespace` +
    `--image` (no glob) bypasses it (see the tests below)."""
    monkeypatch.setattr(
        registry,
        "catalog",
        lambda host: ["acme/erpnext-v16", "acme/other", "other-client/erpnext-v16"],
    )
    _stub_repositories(
        monkeypatch,
        {
            "acme/erpnext-v16": (
                ["v16"], {"v16": _remote_image("sha256:" + "a" * 64, _cairn_labels())}
            )
        },
    )

    result = runner.invoke(
        cli_registry.app, ["images", "--namespace", "acme", "--image", "erpnext-*"]
    )

    assert f"Repository {local_registry.host}/acme/erpnext-v16" in result.stderr
    assert "acme/other" not in result.stderr
    assert "other-client" not in result.stderr


def test_exact_namespace_and_image_bypasses_the_catalog(local_registry, monkeypatch):
    """The single named repository is read directly — the same tag-by-tag authenticated read
    `push`/`assign-tag` use — so it reaches an authenticated remote registry the anonymous-only
    catalog endpoint cannot (`ADR-069`)."""

    def _catalog_must_not_be_called(host):
        raise AssertionError("the catalog endpoint must not be called for an exact repository")

    monkeypatch.setattr(registry, "catalog", _catalog_must_not_be_called)
    _stub_repositories(
        monkeypatch,
        {
            "acme/erpnext-v16": (
                ["v16"], {"v16": _remote_image("sha256:" + "a" * 64, _cairn_labels())}
            )
        },
    )

    result = runner.invoke(
        cli_registry.app,
        ["images", "--host", "ghcr.io", "--namespace", "acme", "--image", "erpnext-v16"],
    )

    assert result.exit_code == 0
    assert "Repository ghcr.io/acme/erpnext-v16" in result.stderr


def test_glob_image_does_not_bypass_the_catalog(local_registry, monkeypatch):
    catalog_calls = []
    monkeypatch.setattr(registry, "catalog", lambda host: catalog_calls.append(host) or [])

    result = runner.invoke(
        cli_registry.app, ["images", "--namespace", "acme", "--image", "erpnext-*"]
    )

    assert catalog_calls == [local_registry.host]
    assert result.exit_code == 0
    assert "No repositories found" in result.stderr


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


def test_check_disk_headroom_reports_permission_error_as_fail(monkeypatch):
    """`Path.exists()` can itself raise `PermissionError` (EACCES on an unreadable parent,
    e.g. `data_dir` relocated under a locked-down directory) — not just `disk_usage()`.
    Both must surface as a `FAIL` row, not an unhandled crash (`BR-REG-011`)."""
    config = registry_config.RegistryConfig(data_dir=Path("/var/lib/docker/cairn-registry"))

    def _raise_eacces(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "exists", _raise_eacces)

    label, ok, detail = cli_registry._check_disk_headroom(config)

    assert label == "disk headroom"
    assert ok is False
    assert "cannot be checked" in detail


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
        setup_runner, "check_memory", lambda: setup_runner.Check("memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )

    result = runner.invoke(cli_registry.app, ["setup", "--only", "preflight", "--dry-run"])

    assert result.exit_code == 0
    assert "[preflight]" in result.stderr
    assert "[admin-group]" not in result.stderr


def test_setup_has_no_workdir_option(tmp_path, monkeypatch):
    """`setup`'s three stages (preflight, admin-group, registry) read no manifest and no
    `options.workdir` (`BR-REG-001`) — unlike `cairn-build`/`cairn-adopt setup`, so the flag
    isn't offered here and the banner doesn't print a `workdir` line that would claim it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(
        setup_runner, "check_command", lambda r, label, c: setup_runner.Check(label, True, "ok")
    )
    monkeypatch.setattr(
        setup_runner, "check_memory", lambda: setup_runner.Check("memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )

    result = runner.invoke(
        cli_registry.app, ["setup", "--only", "preflight", "--workdir", str(tmp_path), "--dry-run"]
    )

    assert result.exit_code != 0
    assert "no such option" in result.stderr.lower()

    result = runner.invoke(cli_registry.app, ["setup", "--only", "preflight", "--dry-run"])

    assert "workdir" not in result.stderr


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


def _stub_all_stages(monkeypatch):
    """Replace every real stage with a no-op, so a non-dry-run `setup` invocation touches
    nothing on the test machine — used only by the doctor-after-setup tests below, which care
    about *whether* `_run_doctor` was called, not what any one stage does."""
    for name in list(registry_provision.REGISTRY_STAGE_FUNCS):
        monkeypatch.setitem(registry_provision.REGISTRY_STAGE_FUNCS, name, lambda r, o: None)


def test_setup_runs_doctor_after_a_real_full_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    _stub_all_stages(monkeypatch)
    calls = []
    monkeypatch.setattr(cli_registry, "_run_doctor", lambda: (calls.append(1), 0)[1])

    result = runner.invoke(cli_registry.app, ["setup"])

    assert calls == [1]
    assert result.exit_code == 0


def test_setup_exit_code_follows_doctor_when_it_fails(tmp_path, monkeypatch):
    """The installer's own summary can be all green while the registry it just started is
    unhealthy — `setup`'s exit code must reflect the fuller check, not just that every stage
    ran without raising."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    _stub_all_stages(monkeypatch)
    monkeypatch.setattr(cli_registry, "_run_doctor", lambda: 1)

    result = runner.invoke(cli_registry.app, ["setup"])

    assert result.exit_code == 1


def test_setup_skips_doctor_on_dry_run(tmp_path, monkeypatch):
    """Nothing was actually started, so there is nothing yet for `doctor` to meaningfully
    check — running it here would just report pre-existing host state as if `setup` caused it."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    _stub_all_stages(monkeypatch)
    calls = []
    monkeypatch.setattr(cli_registry, "_run_doctor", lambda: (calls.append(1), 0)[1])

    runner.invoke(cli_registry.app, ["setup", "--dry-run"])

    assert calls == []


@pytest.mark.parametrize("only", ["preflight", "admin-group"])
def test_setup_skips_doctor_for_a_partial_run_that_never_touched_the_registry(
    tmp_path, monkeypatch, only
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    _stub_all_stages(monkeypatch)
    calls = []
    monkeypatch.setattr(cli_registry, "_run_doctor", lambda: (calls.append(1), 0)[1])

    runner.invoke(cli_registry.app, ["setup", "--only", only])

    assert calls == []


def test_setup_only_registry_still_runs_doctor(tmp_path, monkeypatch):
    """`--only registry` still brings the container up on its own — a meaningful moment to
    verify, unlike `--only preflight`/`--only admin-group`."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    _stub_all_stages(monkeypatch)
    calls = []
    monkeypatch.setattr(cli_registry, "_run_doctor", lambda: (calls.append(1), 0)[1])

    runner.invoke(cli_registry.app, ["setup", "--only", "registry"])

    assert calls == [1]


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
