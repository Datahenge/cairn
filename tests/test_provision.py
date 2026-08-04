"""Tests for `setup` — `cairn-build setup` / `cairn-adopt setup` (`BR-DEPLOY-021`, `ADR-046`).

This code runs **as root on client infrastructure**, which is the whole reason it is Python and
not shell. The contract in `BR-DEPLOY-021` is what these tests hold it to: idempotent, a truthful
dry run, never silently overwriting, no secrets, gating before acting, verifying its own claims.

The generic engine (Runner, preflight checks, admin-group sharing) moved to `setup_runner.py`
and is tested in `test_setup_runner.py` (`ADR-048`); the local registry moved to
`registry_provision.py`, tested in `test_registry_provision.py`. This file covers what is left:
`provision.py`'s own build/adopt-specific stages.

Nothing here runs docker, openssl, or systemctl. `Runner.run` and `Runner.probe` are the two
seams every command goes through, so substituting them covers the whole surface.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from cairn import adopt as adopt_module
from cairn import provision, setup_runner


def _options(**overrides) -> provision.SetupOptions:
    return provision.SetupOptions(**overrides)


class Recorder(provision.Runner):
    """A Runner that records instead of executing, answering probes from a script."""

    def __init__(self, *, dry_run=False, force=False, answers=None):
        super().__init__(dry_run=dry_run, force=force)
        self.commands: list[list[str]] = []
        self.probes: list[list[str]] = []
        self.answers = answers or {}
        self.said: list[str] = []

    def say(self, message=""):
        self.said.append(message)

    def run(self, command, *, what, timeout=600):
        self.commands.append(command)
        return ""

    def probe(self, command, timeout=120):
        self.probes.append(command)
        joined = " ".join(str(part) for part in command)
        for fragment, answer in self.answers.items():
            if fragment in joined:
                return answer
        return None

    def ran(self, fragment):
        return any(fragment in " ".join(str(p) for p in c) for c in self.commands)

    @property
    def output(self):
        return "\n".join(self.said)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every path setup writes to, so no test can touch the real host.

    Also gives ``find_executable()`` real siblings to find, at known paths, so tests that
    exercise the timers stage resolve deterministically instead of depending on whatever
    happens to be on ``PATH`` in the environment running the suite.
    """
    monkeypatch.setattr(setup_runner, "CERT_DIR", tmp_path / "etc/cairn")
    monkeypatch.setattr(provision, "SYSTEMD_DIR", tmp_path / "etc/systemd/system")
    monkeypatch.setattr(provision, "MANIFEST_ROOT", tmp_path / "srv/cairn")
    monkeypatch.setattr(provision, "DESCRIPTOR_PATH", tmp_path / "etc/cairn/adopt.toml")

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "cairn-build").touch()
    (bindir / "cairn-adopt").touch()
    monkeypatch.setattr(sys, "argv", [str(bindir / "cairn-build")])

    workdir = tmp_path / "opt/cairn"
    workdir.mkdir(parents=True)
    return workdir


# --- fixed stage lists, no role flag (`ADR-046`, `ADR-048`) -------------------


def test_build_setup_has_no_target_stages():
    """A build machine has no ERPNext site. `bench backup` there would be asking a question of
    a container that does not exist, and a descriptor describes a *running* deployment."""
    assert "backup" not in provision.BUILD_STAGES
    assert "recon" not in provision.BUILD_STAGES
    assert "descriptor" not in provision.BUILD_STAGES


def test_build_setup_no_longer_hosts_a_registry():
    """The local registry is `cairn-registry setup`'s job now (`ADR-048`)."""
    assert "registry" not in provision.BUILD_STAGES
    assert "registry" not in provision.BUILD_STAGE_FUNCS


def test_adopt_setup_hosts_no_registry():
    """It pulls from wherever the manifest's registry is."""
    assert "registry" not in provision.ADOPT_STAGES


def test_adopt_setup_backs_up_before_the_descriptor():
    stages = provision.ADOPT_STAGES
    assert "backup" in stages
    assert stages.index("backup") < stages.index("descriptor")


def test_admin_group_stage_runs_before_every_stage_that_writes_under_it():
    """The setgid bit must predate every file those stages write (`ADR-043`)."""
    assert provision.BUILD_STAGES.index("admin-group") < provision.BUILD_STAGES.index("manifest")
    assert provision.ADOPT_STAGES.index("admin-group") < provision.ADOPT_STAGES.index("descriptor")


def test_an_unknown_stage_lists_the_real_ones():
    with pytest.raises(provision.Aborted, match="unknown stage"):
        provision.stages_for(provision.BUILD_STAGES, provision.BUILD_STAGE_FUNCS, "manifost")


def test_a_stage_outside_this_setup_is_reported_like_a_typo():
    """`manifest` is a `cairn-build setup` stage; `cairn-adopt setup` doesn't know it exists,
    so asking for it by `--only` is reported the same way a genuine typo would be."""
    with pytest.raises(provision.Aborted, match="unknown stage 'manifest'"):
        provision.stages_for(provision.ADOPT_STAGES, provision.ADOPT_STAGE_FUNCS, "manifest")


# --- rule 5: gate before acting (build/adopt-specific extras) ----------------


def test_preflight_asks_a_builder_for_build_tools_and_an_adopt_setup_for_none(monkeypatch):
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    builder = Recorder()
    with pytest.raises(provision.Aborted):
        provision.stage_preflight_build(builder, _options())
    assert "buildx" in builder.output

    target = Recorder()
    with pytest.raises(provision.Aborted):
        provision.stage_preflight_adopt(target, _options())
    assert "buildx" not in target.output


def test_build_preflight_no_longer_demands_openssl(monkeypatch):
    """openssl was only ever needed to generate the registry's TLS cert — that moved to
    `cairn-registry setup` (`ADR-048`), so a build machine no longer needs it."""
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    def _ok_check(runner, label, command):
        return setup_runner.Check(label, True, "ok")

    monkeypatch.setattr(provision, "check_command", _ok_check)
    monkeypatch.setattr(setup_runner, "check_command", _ok_check)
    monkeypatch.setattr(
        setup_runner, "_check_memory", lambda: setup_runner.Check("available memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )
    builder = Recorder()

    provision.stage_preflight_build(builder, _options())

    assert "openssl" not in builder.output


# --- backup: verified, not assumed ------------------------------------------


def test_a_backup_that_produces_no_dump_stops_the_run(monkeypatch):
    """The whole reason this stage exists is that bench migrate is irreversible."""
    runner = Recorder(answers={"compose ls": '[{"Name": "erp"}]'})  # ls of backups answers nothing

    with pytest.raises(provision.Aborted, match="no dump could be found"):
        provision.stage_backup(runner, _options())


def test_a_verified_backup_is_recorded_and_the_operator_told_to_copy_it_off(monkeypatch):
    runner = Recorder(
        answers={
            "compose ls": '[{"Name": "erp"}]',
            "private/backups": "-rw-r--r-- 1 frappe frappe 4096 dump.sql.gz\n",
        }
    )

    provision.stage_backup(runner, _options())

    assert any("verified pre-install backup" in note for note in runner.report.done)
    assert any("copy it off" in note for note in runner.report.warnings)


def test_skipping_the_backup_is_recorded_as_a_warning():
    """Allowed, but never silent — the operator should see it in the summary."""
    runner = Recorder()

    provision.stage_backup(runner, _options(skip_backup=True))

    assert any("irreversible" in note for note in runner.report.warnings)
    assert not runner.commands


def test_backup_backs_up_every_site():
    runner = Recorder(
        answers={"compose ls": '[{"Name": "erp"}]', "private/backups": "dump.sql.gz\n"}
    )

    provision.stage_backup(runner, _options())

    assert runner.ran("--site all backup --with-files")


# --- recon: capture the revert before anything changes ----------------------


def test_recon_records_how_to_put_the_stack_back(tmp_path):
    """reconcile never rolls back, so the values it will replace must be captured first."""
    (tmp_path / ".env").write_text(
        "CUSTOM_IMAGE=localhost:5000/erp\nCUSTOM_TAG=old\nDB_PASSWORD=secret\n", encoding="utf-8"
    )
    runner = Recorder(
        answers={"compose ls": f'[{{"Name": "erp", "ConfigFiles": "{tmp_path}/compose.yaml"}}]'}
    )

    provision.stage_recon(runner, _options())

    assert runner.report.revert
    note = runner.report.revert[0]
    assert "CUSTOM_TAG=old" in note
    assert "secret" not in note  # rule 4: it reads three keys, not the whole file


def test_env_values_are_read_selectively(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n\nCUSTOM_TAG=test\nDB_PASSWORD=secret\nmalformed\n", encoding="utf-8"
    )

    values = provision.read_env_values(env_file, ("CUSTOM_TAG", "SITES"))

    assert values == {"CUSTOM_TAG": "test"}


def test_a_missing_env_file_is_not_an_error(tmp_path):
    assert provision.read_env_values(tmp_path / "absent", ("CUSTOM_TAG",)) == {}


def test_recon_on_a_host_with_no_stack_is_a_note_not_a_failure():
    runner = Recorder()

    provision.stage_recon(runner, _options())

    assert any("no existing stack" in note for note in runner.report.warnings)


# --- descriptor: calls straight into `adopt`, in-process (`ADR-046`) ---------


def _survey(**overrides) -> adopt_module.Survey:
    defaults = dict(
        project="erp",
        directory=Path("/opt/frappe_docker"),
        sites=("erp.test",),
        image="localhost:5000/erp",
        tag="test",
    )
    return adopt_module.Survey(**{**defaults, **overrides})


def test_the_descriptor_comes_from_adopt_survey(sandbox, monkeypatch):
    monkeypatch.setattr(provision.adopt_module, "survey", lambda project=None: _survey())

    provision.stage_descriptor(Recorder(), _options(workdir=sandbox))

    written = provision.DESCRIPTOR_PATH.read_text(encoding="utf-8")
    assert 'site        = "erp.test"' in written


def test_stage_descriptor_forwards_the_project_name(sandbox, monkeypatch):
    seen = {}
    monkeypatch.setattr(
        provision.adopt_module,
        "survey",
        lambda project=None: (seen.update(project=project), _survey())[1],
    )

    provision.stage_descriptor(Recorder(), _options(workdir=sandbox, project="erp-other"))

    assert seen["project"] == "erp-other"


def test_a_multi_site_host_stops_before_writing_a_descriptor(sandbox, monkeypatch):
    """`BR-DEPLOY-014` gives an environment exactly one site — a stop, not a warning."""
    monkeypatch.setattr(
        provision.adopt_module, "survey", lambda project=None: _survey(sites=("a.test", "b.test"))
    )

    with pytest.raises(provision.Aborted, match="serves 2 sites"):
        provision.stage_descriptor(Recorder(), _options(workdir=sandbox))

    assert not provision.DESCRIPTOR_PATH.exists()


def test_an_incomplete_survey_stops_the_run_rather_than_writing_a_bad_descriptor(
    sandbox, monkeypatch
):
    """Rule 6: `reconcile` refusing a bad descriptor later is a worse failure than refusing
    to write one now."""
    monkeypatch.setattr(
        provision.adopt_module, "survey", lambda project=None: adopt_module.Survey(project="erp")
    )

    with pytest.raises(provision.Aborted, match="not enough could be determined"):
        provision.stage_descriptor(Recorder(), _options(workdir=sandbox))

    assert not provision.DESCRIPTOR_PATH.exists()


def test_a_descriptor_is_confirmed_to_parse_after_writing(sandbox, monkeypatch):
    monkeypatch.setattr(provision.adopt_module, "survey", lambda project=None: _survey())

    provision.stage_descriptor(Recorder(), _options(workdir=sandbox))

    import tomllib

    parsed = tomllib.loads(provision.DESCRIPTOR_PATH.read_text(encoding="utf-8"))
    assert parsed["site"] == "erp.test"


# --- the manifest's home (`BR-CLI-022`, `ADR-047`) ---------------------------


def test_manifest_stage_requires_a_client_name(sandbox):
    runner = Recorder()

    with pytest.raises(provision.Aborted, match="--client"):
        provision.stage_manifest(runner, _options(client=None))


def test_manifest_stage_creates_the_client_directory(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "group_gid", lambda name: None)
    runner = Recorder()

    provision.stage_manifest(runner, _options(client="acme"))

    client_dir = provision.MANIFEST_ROOT / "acme"
    assert client_dir.is_dir()
    assert (client_dir / "cairn.toml").is_file()


def test_manifest_stage_scaffolds_the_canonical_example(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "group_gid", lambda name: None)
    runner = Recorder()

    provision.stage_manifest(runner, _options(client="acme"))

    written = (provision.MANIFEST_ROOT / "acme" / "cairn.toml").read_text(encoding="utf-8")
    assert written == provision.MANIFEST_TEMPLATE
    assert "Order matters" in written  # BR-BUILD-003's required ordered-list comment


def test_manifest_stage_never_touches_an_existing_manifest(sandbox, monkeypatch):
    """Unlike every other file `setup` writes, `--force` does not apply here — this file is
    the operator's own deployment source, not cairn's to manage."""
    monkeypatch.setattr(provision, "group_gid", lambda name: None)
    client_dir = provision.MANIFEST_ROOT / "acme"
    client_dir.mkdir(parents=True)
    (client_dir / "cairn.toml").write_text("# hand-authored\n", encoding="utf-8")
    runner = Recorder(force=True)

    provision.stage_manifest(runner, _options(client="acme", force=True))

    assert (client_dir / "cairn.toml").read_text(encoding="utf-8") == "# hand-authored\n"
    assert any("not modified" in line for line in runner.report.skipped)


def test_manifest_stage_shares_the_group(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "group_gid", lambda name: 4242)
    chown_calls = []
    monkeypatch.setattr(provision.os, "chown", lambda path, uid, gid: chown_calls.append(path))
    runner = Recorder()

    provision.stage_manifest(runner, _options(client="acme"))

    assert provision.MANIFEST_ROOT in chown_calls
    assert provision.MANIFEST_ROOT / "acme" in chown_calls


def test_manifest_stage_never_reads_siblings_under_srv(sandbox, monkeypatch):
    """`/srv/cairn/` is cairn's own namespace; a host's `/srv` may hold unrelated data."""
    monkeypatch.setattr(provision, "group_gid", lambda name: None)
    sibling = provision.MANIFEST_ROOT.parent / "some-other-app"
    sibling.mkdir(parents=True)
    (sibling / "config.toml").write_text("not cairn's", encoding="utf-8")
    runner = Recorder()

    provision.stage_manifest(runner, _options(client="acme"))

    assert (sibling / "config.toml").read_text(encoding="utf-8") == "not cairn's"


def test_manifest_stage_dry_run_writes_nothing(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "group_gid", lambda name: None)
    runner = Recorder(dry_run=True)

    provision.stage_manifest(runner, _options(client="acme"))

    assert not provision.MANIFEST_ROOT.exists()


# --- timers -------------------------------------------------------------


def test_stage_timers_build_writes_only_the_build_timer(sandbox, monkeypatch):
    runner = Recorder()
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    provision.stage_timers_build(runner, _options(workdir=sandbox))

    assert (provision.SYSTEMD_DIR / "cairn-build.timer").exists()
    assert not (provision.SYSTEMD_DIR / "cairn-reconcile.timer").exists()


def test_stage_timers_adopt_writes_only_the_reconcile_timer(sandbox, tmp_path, monkeypatch):
    runner = Recorder()
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    provision.stage_timers_adopt(runner, _options(workdir=sandbox))

    service = (provision.SYSTEMD_DIR / "cairn-reconcile.service").read_text(encoding="utf-8")
    assert f"ExecStart={tmp_path}/bin/cairn-adopt reconcile" in service
    assert not (provision.SYSTEMD_DIR / "cairn-build.timer").exists()


def test_timer_stage_is_root_gated(sandbox, monkeypatch):
    """`setup-timer` has no preceding `preflight` stage, so the timer stages check root
    themselves (`BR-CLI-023`)."""
    runner = Recorder()
    monkeypatch.setattr(
        setup_runner,
        "_check_root",
        lambda: setup_runner.Check("root", False, "must be run with sudo"),
    )

    with pytest.raises(provision.Aborted, match="sudo"):
        provision.stage_timers_build(runner, _options(workdir=sandbox))


@pytest.mark.parametrize(
    "stage",
    [provision.stage_timers_build, provision.stage_timers_adopt],
    ids=["build", "adopt"],
)
def test_a_timer_is_enabled_but_never_started(sandbox, stage, monkeypatch):
    """A timer firing before anyone has confirmed the manifest turns one wrong configuration
    into a wrong deploy every quarter of an hour."""
    runner = Recorder()
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    stage(runner, _options(workdir=sandbox))

    assert runner.ran("systemctl enable")
    assert not runner.ran("systemctl start")
    assert any("NOT started" in note for note in runner.report.warnings)


def test_the_build_service_sets_a_working_directory():
    """Required, not decoration: cairn finds a manifest not given explicitly by searching
    upward from the working directory."""
    rendered = provision.build_service(
        _options(workdir=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "WorkingDirectory=/opt/cairn" in rendered


def test_the_build_service_does_not_restart_on_failure():
    """A restart loop against a failing build turns a bad build into a busy one."""
    rendered = provision.build_service(
        _options(workdir=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "Type=oneshot" in rendered
    assert "Restart=" not in rendered


def test_the_build_timer_measures_from_the_end_of_the_last_run():
    """A build takes tens of minutes; the next one must not already be due when it finishes."""
    rendered = provision.build_timer(_options(build_interval="15min"))

    assert "OnUnitInactiveSec=15min" in rendered
    assert "OnCalendar=" not in rendered


def test_the_build_script_builds_then_advances_the_pointer():
    rendered = provision.build_script(
        _options(
            workdir=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/deployments/acme/cairn.toml"),
            environment="test",
        ),
        Path("/opt/cairn-venv/bin/cairn-build"),
    )

    assert "build --manifest" in rendered
    assert "retag test --latest --yes" in rendered
    assert rendered.index("build --manifest") < rendered.index("retag test")


def test_a_manifest_path_with_spaces_is_quoted_in_the_script():
    rendered = provision.build_script(
        _options(
            workdir=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/my deployments/cairn.toml"),
            environment="test",
        ),
        Path("/opt/cairn-venv/bin/cairn-build"),
    )

    assert "'/opt/cairn/my deployments/cairn.toml'" in rendered


# --- the run as a whole ------------------------------------------------------


def test_a_failed_gate_exits_two_and_changes_nothing(monkeypatch):
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )
    runner = provision.Runner(dry_run=False, force=False)

    code = provision.execute(
        runner,
        _options(),
        provision.ADOPT_STAGE_FUNCS,
        provision.ADOPT_STAGES,
        "preflight",
        program="cairn-adopt",
    )

    assert code == 2


def test_a_dry_run_of_a_whole_setup_reports_and_exits_zero():
    stub_funcs = dict.fromkeys(provision.ADOPT_STAGE_FUNCS, lambda runner, options: None)
    runner = provision.Runner(dry_run=True, force=False)

    code = provision.execute(
        runner, _options(), stub_funcs, provision.ADOPT_STAGES, None, program="cairn-adopt"
    )

    assert code == 0
