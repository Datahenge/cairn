"""Tests for the `cairn-adopt` command surface — exit codes and flag plumbing
(BR-CLI-012, BR-CLI-015).

This file covers only what `cli_adopt.py` itself decides: the exit code every command
leaves behind, and that each flag reaches the module that acts on it. The work behind the
flags is tested where it lives — survey logic in `test_adopt.py`, convergence in
`test_reconcile.py`, unit rendering in `test_systemd.py`.
"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cairn import adopt, cli_adopt, config, doctor, reconcile
from cairn.config import App, Frappe, Manifest
from cairn.errors import ReconcileError

runner = CliRunner()


def _manifest():
    return Manifest(
        image_name="erpnext-btu-v16",
        frappe=Frappe("https://github.com/frappe/frappe", "v16.0.1"),
        apps=(App("erpnext", "https://github.com/frappe/erpnext", "v16.0.1"),),
        build={},
    )


# --- exit codes through `run` (BR-CLI-012, BR-CLI-015) ----------------------


def test_success_exits_zero(monkeypatch):
    monkeypatch.setattr(doctor, "run_target", lambda: 0)

    result = runner.invoke(cli_adopt.app, ["doctor"])

    assert result.exit_code == 0


def test_exit_code_is_the_actions_own_return_value(monkeypatch):
    """BR-CLI-012: a failed check must be detectable, so the code is forwarded, not flattened."""
    monkeypatch.setattr(doctor, "run_target", lambda: 1)

    result = runner.invoke(cli_adopt.app, ["doctor"])

    assert result.exit_code == 1


def test_interrupt_exits_130(monkeypatch):
    """The shell's convention for SIGINT."""

    def _interrupt():
        raise KeyboardInterrupt

    monkeypatch.setattr(doctor, "run_target", _interrupt)

    result = runner.invoke(cli_adopt.app, ["doctor"])

    assert result.exit_code == 130
    assert "Interrupted." in result.stderr


def test_unexpected_exception_is_named_and_reraised(monkeypatch):
    def _bug():
        raise ValueError("off by one")

    monkeypatch.setattr(doctor, "run_target", _bug)

    result = runner.invoke(cli_adopt.app, ["doctor"])

    assert result.exit_code != 0
    assert "Internal error (ValueError): off by one" in result.stderr
    assert isinstance(result.exception, ValueError)


# --- reconcile (BR-CLI-008, BR-DEPLOY-003) ---------------------------------


@pytest.fixture
def target(tmp_path, monkeypatch):
    """A target host: a descriptor on disk, and a stubbed convergence."""
    path = tmp_path / "adopt.toml"
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

    result = runner.invoke(cli_adopt.app, ["reconcile", "--descriptor", str(target)])

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

    result = runner.invoke(cli_adopt.app, ["reconcile", "--descriptor", str(target)])

    assert result.exit_code == 0
    assert "Already running" in result.stderr
    assert "Converged" not in result.stdout


def test_reconcile_halts_and_reports_on_failure(target, monkeypatch):
    """BR-DEPLOY-018: it stops rather than rolling back, and the exit code says so."""

    def _fail(desc, dry_run=False, report=None):
        raise ReconcileError("Failed while running bench migrate (exit code 1).")

    monkeypatch.setattr(reconcile, "run", _fail)

    result = runner.invoke(cli_adopt.app, ["reconcile", "--descriptor", str(target)])

    assert result.exit_code == 2
    assert "Error: Failed while running bench migrate" in result.stderr
    assert "Timing" in result.stderr  # how long it ran before failing still matters


def test_a_missing_descriptor_names_the_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli_adopt.app, ["reconcile", "--descriptor", str(tmp_path / "absent.toml")]
    )

    assert result.exit_code == 2
    assert "absent.toml" in result.stderr


# --- systemd units (BR-CLI-019) --------------------------------------------


def test_systemd_units_are_printed_to_stdout():
    """Printed, never installed on its own — so stdout must be the units themselves."""
    result = runner.invoke(cli_adopt.app, ["systemd-units"])

    assert result.exit_code == 0
    assert "[Timer]" in result.stdout
    assert "Type=oneshot" in result.stdout
    assert "cairn-reconcile.service" in result.stdout


def test_systemd_units_report_what_they_assumed():
    """BR-CLI-019: a host-specific guess must be visible before installation, not after."""
    result = runner.invoke(
        cli_adopt.app, ["systemd-units", "--interval", "15min", "--user", "cairn"]
    )

    assert result.exit_code == 0
    assert "interval     15min" in result.stderr
    assert "user         cairn" in result.stderr
    assert "OnUnitInactiveSec=15min" in result.stdout
    assert "User=cairn" in result.stdout


# --- examine (BR-CLI-020) ---------------------------------------------------


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


def test_examine_needs_no_project_and_prints_a_descriptor(tmp_path, monkeypatch):
    """A host being examined has neither a cairn project nor a manifest yet."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey())

    result = runner.invoke(cli_adopt.app, ["examine", "--environment", "test"])

    assert result.exit_code == 0
    assert 'environment = "test"' in result.stdout
    assert 'site        = "erp.acme.test"' in result.stdout


def test_examine_writes_nothing(tmp_path, monkeypatch):
    """BR-CLI-020: it reads and prints. The descriptor goes to stdout, never to disk."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey())

    runner.invoke(cli_adopt.app, ["examine"])

    assert list(tmp_path.iterdir()) == []


def test_examine_refuses_a_multi_site_host(tmp_path, monkeypatch):
    """Converging it would drop the other sites from the proxy config, so this is a stop."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        adopt, "survey", lambda project=None: _survey(sites=("a.test", "b.test"))
    )

    result = runner.invoke(cli_adopt.app, ["examine"])

    assert result.exit_code == 2
    assert "serves 2 sites" in result.stderr
    assert "environment =" not in result.stdout


def test_examine_reports_what_it_could_not_determine(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    incomplete = adopt.Survey(
        findings=[adopt.Finding("compose project", "`docker compose ls` did not answer")]
    )
    monkeypatch.setattr(adopt, "survey", lambda project=None: incomplete)

    result = runner.invoke(cli_adopt.app, ["examine"])

    assert result.exit_code == 2
    assert "did not answer" in result.stderr
    assert "Not enough could be determined" in result.stderr


def test_examine_cross_checks_the_manifest_when_given_one(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(adopt, "survey", lambda project=None: _survey(apps=("frappe", "erpnext")))
    manifest = tmp_path / "cairn.toml"
    manifest.touch()
    monkeypatch.setattr(config, "load_manifest", lambda path: _manifest())

    result = runner.invoke(cli_adopt.app, ["examine", "--manifest", str(manifest)])

    assert result.exit_code == 0
    assert "Manifest matches" in result.stderr


def test_examine_forwards_the_project_name(tmp_path, monkeypatch):
    seen = {}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        adopt, "survey", lambda project=None: (seen.update(project=project), _survey())[1]
    )

    runner.invoke(cli_adopt.app, ["examine", "--project", "erp-other"])

    assert seen["project"] == "erp-other"


# --- setup (BR-CLI-021) -----------------------------------------------------


def test_setup_is_root_gated(tmp_path, monkeypatch):
    """Exits reporting the shortfall rather than attempting a partial run (`BR-DEPLOY-021`)."""
    monkeypatch.chdir(tmp_path)
    from cairn import provision

    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", False, "no"))

    result = runner.invoke(cli_adopt.app, ["setup", "--dry-run"])

    assert result.exit_code == 2
    assert "root" in result.stderr


def test_setup_only_runs_the_named_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from cairn import provision

    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", True, "ok"))
    monkeypatch.setattr(
        provision, "_check_command", lambda r, label, c: provision.Check(label, True, "ok")
    )
    monkeypatch.setattr(provision, "_check_memory", lambda: provision.Check("memory", True, "ok"))
    monkeypatch.setattr(
        provision.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )

    result = runner.invoke(cli_adopt.app, ["setup", "--only", "preflight", "--dry-run"])

    assert result.exit_code == 0
    assert "[preflight]" in result.stderr
    assert "[admin-group]" not in result.stderr


# --- surfaces every command shares (BR-CLI-015) ----------------------------


@pytest.mark.parametrize(
    "command",
    [
        ["reconcile"],
        ["examine"],
        ["systemd-units"],
        ["doctor"],
        ["setup"],
    ],
)
def test_every_command_has_help(command):
    """BR-CLI-015: `--help` everywhere, and it must not need a project to answer."""
    result = runner.invoke(cli_adopt.app, [*command, "--help"])

    assert result.exit_code == 0
    assert result.stdout.strip()


def test_no_arguments_shows_help_rather_than_failing():
    """Typing `cairn-adopt` alone is a question, not an error."""
    result = runner.invoke(cli_adopt.app, [])

    assert "Usage" in result.stdout


def test_version_is_reported_without_a_project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(cli_adopt.app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.startswith("cairn-adopt ")


def test_the_console_script_entry_point_runs_the_app(monkeypatch):
    """`pyproject.toml` points the `cairn-adopt` command at this function; if it stopped
    invoking the app, an installed cairn-adopt would do nothing and no other test would
    notice."""
    invoked = []
    monkeypatch.setattr(cli_adopt, "app", lambda: invoked.append(True))

    cli_adopt.main()

    assert invoked == [True]


def test_python_dash_m_cairn_adopt_runs_the_app(monkeypatch):
    """`python -m cairn.cli_adopt` is a documented invocation, so its module guard must
    actually fire — proven by letting it really run `--help` and checking it exits 0,
    since a fresh `runpy` execution has its own module namespace to monkeypatch into."""
    monkeypatch.setattr(sys, "argv", ["cairn-adopt", "--help"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_module("cairn.cli_adopt", run_name="__main__")

    assert excinfo.value.code == 0
