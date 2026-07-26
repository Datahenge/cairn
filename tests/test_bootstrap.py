"""Tests for the provisioning installer (`BR-DEPLOY-021`, `ADR-040`).

This code runs **as root on client infrastructure**, which is the whole reason it is Python and
not shell. The contract in `BR-DEPLOY-021` is what these tests hold it to: idempotent, a truthful
dry run, never silently overwriting, no secrets, gating before acting, verifying its own claims.

Nothing here runs docker, openssl, or systemctl. `Runner.run` and `Runner.probe` are the two
seams every command goes through, so substituting them covers the whole surface.
"""

from __future__ import annotations

from pathlib import Path

import bootstrap
import pytest


def _options(**overrides):
    """Parsed arguments, with a role and a source that exist."""
    argv = ["--role", overrides.pop("role", "both")]
    for key, value in overrides.pop("flags", {}).items():
        argv += [key, str(value)]
    for flag in overrides.pop("switches", []):
        argv.append(flag)
    options = bootstrap.parse_args(argv)
    for key, value in overrides.items():
        setattr(options, key, value)
    return options


class Recorder(bootstrap.Runner):
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
    """Redirect every path the installer writes to, so no test can touch the real host."""
    for name, relative in (
        ("CERT_DIR", "etc/cairn"),
        ("SYSTEM_CA_DIR", "usr/local/share/ca-certificates"),
        ("DOCKER_CERT_DIR", "etc/docker/certs.d"),
        ("SYSTEMD_DIR", "etc/systemd/system"),
        ("REGISTRY_DIR", "opt/cairn-registry"),
    ):
        monkeypatch.setattr(bootstrap, name, tmp_path / relative)
    monkeypatch.setattr(bootstrap, "DESCRIPTOR_PATH", tmp_path / "etc/cairn/environment.toml")
    source = tmp_path / "opt/cairn"
    source.mkdir(parents=True)
    return source


# --- roles: each host does only what its role implies ------------------------


def test_a_builder_neither_surveys_nor_backs_up_nor_is_described():
    """A build machine has no ERPNext site. `bench backup` there would be asking a question of
    a container that does not exist, and a descriptor describes a *running* deployment."""
    assert "backup" not in bootstrap.BUILDER_STAGES
    assert "recon" not in bootstrap.BUILDER_STAGES
    assert "descriptor" not in bootstrap.BUILDER_STAGES


def test_a_target_hosts_no_registry():
    """It pulls from the builder's."""
    assert "registry" not in bootstrap.TARGET_STAGES


def test_a_target_backs_up_before_anything_else_changes():
    stages = bootstrap.TARGET_STAGES
    assert "backup" in stages
    assert stages.index("backup") < stages.index("cairn")
    assert stages.index("backup") < stages.index("descriptor")


def test_both_is_the_union_and_still_backs_up_first():
    """The bootstrap case: one box doing each. The ordering guarantee must survive it."""
    stages = bootstrap.BOTH_STAGES
    assert set(stages) == set(bootstrap.BUILDER_STAGES) | set(bootstrap.TARGET_STAGES)
    assert stages.index("backup") < stages.index("registry")
    assert stages.index("preflight") == 0


@pytest.mark.parametrize(
    ("stage", "role", "expected"),
    [
        ("backup", "builder", "A builder has none"),
        ("recon", "builder", "no running deployment to survey"),
        ("descriptor", "builder", "a build machine has none"),
        ("registry", "target", "belongs on the build machine"),
    ],
)
def test_a_stage_run_against_the_wrong_role_says_why(stage, role, expected):
    """`--only` lets a stage be invoked directly, so each must refuse the wrong role itself
    rather than relying on the stage list to have filtered it."""
    runner = Recorder()

    with pytest.raises(bootstrap.Aborted, match=expected):
        bootstrap.STAGES[stage](runner, _options(role=role))


def test_an_unknown_stage_lists_the_real_ones():
    with pytest.raises(bootstrap.Aborted, match="unknown stage"):
        bootstrap.stages_for("both", "registery")


def test_a_stage_outside_the_role_is_refused_by_name():
    with pytest.raises(bootstrap.Aborted, match="does not apply to role"):
        bootstrap.stages_for("target", "registry")


# --- rule 5: gate before acting ---------------------------------------------


def test_preflight_reports_every_check_before_stopping(monkeypatch):
    """An installer that dies on the first problem makes the operator discover prerequisites
    one reboot at a time."""
    runner = Recorder()
    monkeypatch.setattr(bootstrap, "_check_root", lambda: bootstrap.Check("root", False, "no"))

    with pytest.raises(bootstrap.Aborted, match="prerequisite"):
        bootstrap.stage_preflight(runner, _options(role="target"))

    assert "docker" in runner.output
    assert "free disk" in runner.output
    assert "available memory" in runner.output


def test_preflight_asks_a_builder_for_build_tools_and_a_target_for_none(monkeypatch):
    monkeypatch.setattr(bootstrap, "_check_root", lambda: bootstrap.Check("root", True, "ok"))

    builder = Recorder()
    with pytest.raises(bootstrap.Aborted):
        bootstrap.stage_preflight(builder, _options(role="builder"))
    assert "buildx" in builder.output
    assert "cairn checkout" in builder.output

    target = Recorder()
    with pytest.raises(bootstrap.Aborted):
        bootstrap.stage_preflight(target, _options(role="target"))
    assert "buildx" not in target.output
    assert "cairn checkout" not in target.output


def test_the_disk_gate_uses_the_documented_floor(monkeypatch):
    monkeypatch.setattr(
        bootstrap.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    assert bootstrap._check_disk().ok is False

    monkeypatch.setattr(
        bootstrap.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )
    assert bootstrap._check_disk().ok is True


def test_memory_is_read_as_available_not_free(tmp_path):
    """MemFree excludes reclaimable cache and would make a healthy host look starved."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       8039024 kB\nMemFree:          201234 kB\nMemAvailable:    6291456 kB\n",
        encoding="utf-8",
    )

    assert bootstrap.read_available_memory_gb(meminfo) == pytest.approx(6.44, abs=0.05)


def test_unreadable_meminfo_is_a_failed_check_not_a_crash(tmp_path):
    assert bootstrap.read_available_memory_gb(tmp_path / "absent") is None


def test_a_builder_without_the_vendored_tree_is_refused(tmp_path):
    """A pip install carries no vendored tree today (`ADR-018`), so a builder is a checkout."""
    check = bootstrap._check_checkout(tmp_path)

    assert check.ok is False
    assert "pip install" in check.detail


def test_a_builder_with_the_vendored_tree_passes(tmp_path):
    containerfile = tmp_path / "frappe_docker" / "images" / "custom" / "Containerfile"
    containerfile.parent.mkdir(parents=True)
    containerfile.write_text("FROM scratch\n", encoding="utf-8")

    assert bootstrap._check_checkout(tmp_path).ok is True


# --- rule 2: the dry run is truthful ----------------------------------------


def test_a_dry_run_writes_nothing(tmp_path):
    runner = bootstrap.Runner(dry_run=True, force=False)
    target = tmp_path / "written.toml"

    runner.write(target, "x = 1\n", what="a file")

    assert not target.exists()


def test_a_dry_run_still_prints_the_path_and_mode(tmp_path):
    runner = Recorder(dry_run=True)
    bootstrap.Runner.write(runner, tmp_path / "f.conf", "x\n", mode=0o600, what="a file")

    assert "600" in runner.output
    assert "f.conf" in runner.output


def test_a_dry_run_reads_the_host_anyway():
    """A dry run that cannot see the host cannot tell you what it would do — reading is not a
    mutation."""
    runner = bootstrap.Runner(dry_run=True, force=False)

    assert runner.probe(["true"]) is not None


# --- rule 3: never silently overwrite ---------------------------------------


def test_an_existing_different_file_is_refused_without_force(tmp_path):
    target = tmp_path / "environment.toml"
    target.write_text("environment = \"old\"\n", encoding="utf-8")
    runner = bootstrap.Runner(dry_run=False, force=False)

    with pytest.raises(bootstrap.Aborted, match="--force"):
        runner.write(target, 'environment = "new"\n', what="descriptor")

    assert target.read_text(encoding="utf-8") == 'environment = "old"\n'


def test_force_replaces_but_keeps_the_previous_file(tmp_path):
    target = tmp_path / "environment.toml"
    target.write_text('environment = "old"\n', encoding="utf-8")
    runner = bootstrap.Runner(dry_run=False, force=True)

    runner.write(target, 'environment = "new"\n', what="descriptor")

    assert target.read_text(encoding="utf-8") == 'environment = "new"\n'
    backup = target.with_suffix(".toml.cairn-backup")
    assert backup.read_text(encoding="utf-8") == 'environment = "old"\n'
    assert any("previous kept at" in note for note in runner.report.warnings)


# --- rule 1: idempotent ------------------------------------------------------


def test_an_identical_file_is_left_alone_and_reported_as_skipped(tmp_path):
    """Re-running must converge, not churn. This is what makes VPS #2 and #3 cheap."""
    target = tmp_path / "compose.yaml"
    target.write_text("services: {}\n", encoding="utf-8")
    runner = bootstrap.Runner(dry_run=False, force=False)

    runner.write(target, "services: {}\n", what="registry compose")

    assert runner.report.done == []
    assert any("already correct" in note for note in runner.report.skipped)


def test_writing_twice_converges(tmp_path):
    target = tmp_path / "unit.service"
    runner = bootstrap.Runner(dry_run=False, force=False)

    runner.write(target, "[Service]\n", what="unit")
    runner.write(target, "[Service]\n", what="unit")

    assert not target.with_suffix(".service.cairn-backup").exists()


# --- rule 4: no secrets ------------------------------------------------------


def test_the_certificate_key_is_owner_only(sandbox, monkeypatch):
    """Key material the installer creates must not be world-readable."""
    modes = {}
    monkeypatch.setattr(bootstrap.os, "chmod", lambda path, mode: modes.setdefault(path, mode))
    runner = Recorder(answers={"curl": "ok"})

    bootstrap.stage_registry(runner, _options(role="builder", source=sandbox, force=True))

    assert modes[bootstrap.CERT_DIR / "registry.key"] == 0o600


def test_the_registry_has_no_credentials_to_leak():
    """A localhost-bound registry needs no auth, so there is no secret in this file at all."""
    rendered = bootstrap.registry_compose()

    assert "PASSWORD" not in rendered.upper()
    assert "htpasswd" not in rendered
    assert "AUTH" not in rendered.upper()


# --- the registry ------------------------------------------------------------


def test_the_certificate_covers_localhost_and_the_private_ip():
    """The private IP is included now so the certificate survives builder and target splitting;
    reissuing later means re-trusting it on every host that already had it."""
    sans = bootstrap.subject_alt_names("10.0.0.5")

    assert "DNS:localhost" in sans
    assert "IP:127.0.0.1" in sans
    assert "IP:10.0.0.5" in sans


def test_no_private_ip_still_yields_a_usable_certificate():
    sans = bootstrap.subject_alt_names(None)

    assert "DNS:localhost" in sans
    assert "IP:" in sans


def test_the_registry_binds_to_localhost_only():
    """Never exposed: there is no auth, so reachability is the whole of the access control."""
    rendered = bootstrap.registry_compose()

    assert f'"127.0.0.1:{bootstrap.REGISTRY_PORT}:{bootstrap.REGISTRY_PORT}"' in rendered


def test_the_registry_can_delete_versions():
    """What makes keep-N retention possible later; some hosted registries cannot do it at all."""
    assert "REGISTRY_STORAGE_DELETE_ENABLED" in bootstrap.registry_compose()


def test_the_registry_is_verified_over_tls_before_being_claimed(sandbox):
    """Rule 6. An untrusted CA fails here rather than at the first push."""
    bootstrap.CERT_DIR.mkdir(parents=True)
    (bootstrap.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={})  # curl answers nothing

    with pytest.raises(bootstrap.Aborted, match="did not answer over TLS"):
        bootstrap.stage_registry(runner, _options(role="builder", source=sandbox))


def test_the_certificate_is_trusted_in_both_stores(sandbox):
    """Python reads the system bundle; Docker reads its own per-registry directory."""
    bootstrap.CERT_DIR.mkdir(parents=True)
    (bootstrap.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    bootstrap.stage_registry(runner, _options(role="builder", source=sandbox))

    system_ca = bootstrap.SYSTEM_CA_DIR / "cairn-registry.crt"
    assert system_ca.read_text(encoding="utf-8") == "cert\n"
    docker_ca = bootstrap.DOCKER_CERT_DIR / f"localhost:{bootstrap.REGISTRY_PORT}" / "ca.crt"
    assert docker_ca.read_text(encoding="utf-8") == "cert\n"
    assert runner.ran("update-ca-certificates")


# --- backup: verified, not assumed ------------------------------------------


def test_a_backup_that_produces_no_dump_stops_the_run(monkeypatch):
    """The whole reason this stage exists is that bench migrate is irreversible."""
    runner = Recorder(answers={"compose ls": '[{"Name": "erp"}]'})  # ls of backups answers nothing

    with pytest.raises(bootstrap.Aborted, match="no dump could be found"):
        bootstrap.stage_backup(runner, _options(role="target"))


def test_a_verified_backup_is_recorded_and_the_operator_told_to_copy_it_off(monkeypatch):
    runner = Recorder(
        answers={
            "compose ls": '[{"Name": "erp"}]',
            "private/backups": "-rw-r--r-- 1 frappe frappe 4096 dump.sql.gz\n",
        }
    )

    bootstrap.stage_backup(runner, _options(role="target"))

    assert any("verified pre-install backup" in note for note in runner.report.done)
    assert any("copy it off" in note for note in runner.report.warnings)


def test_skipping_the_backup_is_recorded_as_a_warning():
    """Allowed, but never silent — the operator should see it in the summary."""
    runner = Recorder()

    bootstrap.stage_backup(runner, _options(role="target", skip_backup=True))

    assert any("irreversible" in note for note in runner.report.warnings)
    assert not runner.commands


def test_backup_backs_up_every_site():
    runner = Recorder(
        answers={"compose ls": '[{"Name": "erp"}]', "private/backups": "dump.sql.gz\n"}
    )

    bootstrap.stage_backup(runner, _options(role="target"))

    assert runner.ran("--site all backup --with-files")


# --- recon: capture the revert before anything changes ----------------------


def test_recon_records_how_to_put_the_stack_back(tmp_path):
    """reconcile never rolls back, so the values it will replace must be captured first."""
    (tmp_path / ".env").write_text(
        "CUSTOM_IMAGE=localhost:5000/erp\nCUSTOM_TAG=old\nDB_PASSWORD=secret\n", encoding="utf-8"
    )
    runner = Recorder(
        answers={
            "compose ls": f'[{{"Name": "erp", "ConfigFiles": "{tmp_path}/compose.yaml"}}]'
        }
    )

    bootstrap.stage_recon(runner, _options(role="target"))

    assert runner.report.revert
    note = runner.report.revert[0]
    assert "CUSTOM_TAG=old" in note
    assert "secret" not in note  # rule 4: it reads three keys, not the whole file


def test_env_values_are_read_selectively(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# a comment\n\nCUSTOM_TAG=test\nDB_PASSWORD=secret\nmalformed\n", encoding="utf-8"
    )

    values = bootstrap.read_env_values(env_file, ("CUSTOM_TAG", "SITES"))

    assert values == {"CUSTOM_TAG": "test"}


def test_a_missing_env_file_is_not_an_error(tmp_path):
    assert bootstrap.read_env_values(tmp_path / "absent", ("CUSTOM_TAG",)) == {}


def test_recon_on_a_host_with_no_stack_is_a_note_not_a_failure():
    runner = Recorder()

    bootstrap.stage_recon(runner, _options(role="target"))

    assert any("no existing stack" in note for note in runner.report.warnings)


# --- descriptor --------------------------------------------------------------


def test_the_descriptor_comes_from_cairn_adopt(sandbox):
    rendered = 'environment = "test"\nsite = "erp.test"\n'
    runner = Recorder(answers={"adopt": rendered})

    bootstrap.stage_descriptor(runner, _options(role="target", source=sandbox))

    assert bootstrap.DESCRIPTOR_PATH.read_text(encoding="utf-8") == rendered
    assert any("adopt" in " ".join(str(p) for p in probe) for probe in runner.probes)


def test_a_descriptor_that_does_not_parse_stops_the_run(sandbox):
    """Rule 6: reconcile refusing it later is a worse failure than refusing now."""
    runner = Recorder(answers={"adopt": "environment = \n"})

    with pytest.raises(bootstrap.Aborted, match="does not parse"):
        bootstrap.stage_descriptor(runner, _options(role="target", source=sandbox))


def test_a_failing_adopt_names_the_command_to_rerun(sandbox):
    """Rule 7: every action is reportable as something the operator can run by hand."""
    runner = Recorder(answers={})

    with pytest.raises(bootstrap.Aborted, match="adopt"):
        bootstrap.stage_descriptor(runner, _options(role="target", source=sandbox))


# --- timers ------------------------------------------------------------------


UNITS = """\
# --- /etc/systemd/system/cairn-reconcile.service ---
[Service]
Type=oneshot
ExecStart=cairn reconcile

# --- /etc/systemd/system/cairn-reconcile.timer ---
[Timer]
OnUnitInactiveSec=5min
"""


def test_units_are_split_into_a_service_and_a_timer():
    service, timer = bootstrap.split_units(UNITS)

    assert "[Service]" in service and "[Timer]" not in service
    assert "[Timer]" in timer and "[Service]" not in timer


def test_unexpected_unit_output_fails_loudly_rather_than_installing_half_a_unit():
    assert bootstrap.split_units("something else entirely") == (None, None)


def test_the_reconcile_unit_is_pointed_at_the_venv_binary(sandbox):
    """cairn resolves its own path with shutil.which, which will not find a venv binary."""
    runner = Recorder(answers={"systemd-units": UNITS})

    bootstrap.stage_timers(runner, _options(role="target", source=sandbox))

    service = (bootstrap.SYSTEMD_DIR / "cairn-reconcile.service").read_text(encoding="utf-8")
    assert f"ExecStart={sandbox}/.venv/bin/cairn reconcile" in service


def test_a_builder_gets_a_build_timer_and_no_reconcile_timer(sandbox):
    runner = Recorder(answers={"systemd-units": UNITS})

    bootstrap.stage_timers(runner, _options(role="builder", source=sandbox))

    assert (bootstrap.SYSTEMD_DIR / "cairn-build.timer").exists()
    assert not (bootstrap.SYSTEMD_DIR / "cairn-reconcile.timer").exists()


def test_a_target_gets_a_reconcile_timer_and_no_build_timer(sandbox):
    runner = Recorder(answers={"systemd-units": UNITS})

    bootstrap.stage_timers(runner, _options(role="target", source=sandbox))

    assert (bootstrap.SYSTEMD_DIR / "cairn-reconcile.timer").exists()
    assert not (bootstrap.SYSTEMD_DIR / "cairn-build.timer").exists()


def test_timers_are_enabled_but_never_started(sandbox):
    """A timer firing before anyone has confirmed the manifest turns one wrong configuration
    into a wrong deploy every quarter of an hour."""
    runner = Recorder(answers={"systemd-units": UNITS})

    bootstrap.stage_timers(runner, _options(role="both", source=sandbox))

    assert runner.ran("systemctl enable")
    assert not runner.ran("systemctl start")
    assert any("NOT started" in note for note in runner.report.warnings)


def test_the_build_service_sets_a_working_directory(monkeypatch, tmp_path):
    """Required, not decoration: cairn finds the vendored tree by searching upward from cwd."""
    rendered = bootstrap.build_service(
        _options(role="builder", source=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "WorkingDirectory=/opt/cairn" in rendered


def test_the_build_service_does_not_restart_on_failure():
    """A restart loop against a failing build turns a bad build into a busy one."""
    rendered = bootstrap.build_service(
        _options(role="builder", source=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "Type=oneshot" in rendered
    assert "Restart=" not in rendered


def test_the_build_timer_measures_from_the_end_of_the_last_run():
    """A build takes tens of minutes; the next one must not already be due when it finishes."""
    rendered = bootstrap.build_timer(_options(role="builder", build_interval="15min"))

    assert "OnUnitInactiveSec=15min" in rendered
    assert "OnCalendar=" not in rendered


def test_the_build_script_builds_then_advances_the_pointer(tmp_path):
    rendered = bootstrap.build_script(
        _options(
            role="builder",
            source=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/deployments/acme/cairn.toml"),
            environment="test",
        )
    )

    assert "build --manifest" in rendered
    assert "retag test --latest --yes" in rendered
    assert rendered.index("build --manifest") < rendered.index("retag test")


def test_a_manifest_path_with_spaces_is_quoted_in_the_script():
    rendered = bootstrap.build_script(
        _options(
            role="builder",
            source=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/my deployments/cairn.toml"),
            environment="test",
        )
    )

    assert "'/opt/cairn/my deployments/cairn.toml'" in rendered


# --- the run as a whole ------------------------------------------------------


def test_a_failed_gate_exits_two_and_changes_nothing(monkeypatch):
    monkeypatch.setattr(bootstrap, "_check_root", lambda: bootstrap.Check("root", False, "no"))

    assert bootstrap.main(["--role", "target", "--only", "preflight"]) == 2


def test_a_dry_run_of_a_whole_role_reports_and_exits_zero(monkeypatch):
    monkeypatch.setattr(bootstrap, "_check_root", lambda: bootstrap.Check("root", True, "ok"))
    for name in ("recon", "backup", "cairn", "descriptor", "timers", "registry"):
        monkeypatch.setitem(bootstrap.STAGES, name, lambda runner, options: None)
    monkeypatch.setattr(
        bootstrap, "stage_preflight", lambda runner, options: None
    )
    monkeypatch.setitem(bootstrap.STAGES, "preflight", lambda runner, options: None)

    assert bootstrap.main(["--role", "both", "--dry-run"]) == 0


def test_the_manifest_defaults_beside_the_checkout():
    options = bootstrap.parse_args(["--role", "builder", "--source", "/opt/cairn"])

    assert options.manifest == Path("/opt/cairn/cairn.toml")


def test_an_explicit_manifest_wins():
    options = bootstrap.parse_args(
        ["--role", "builder", "--manifest", "/srv/acme/cairn.toml"]
    )

    assert options.manifest == Path("/srv/acme/cairn.toml")
