"""Tests for the provisioning installer (`BR-DEPLOY-021`, `ADR-040`).

This code runs **as root on client infrastructure**, which is the whole reason it is Python and
not shell. The contract in `BR-DEPLOY-021` is what these tests hold it to: idempotent, a truthful
dry run, never silently overwriting, no secrets, gating before acting, verifying its own claims.

Nothing here runs docker, openssl, or systemctl. `Runner.run` and `Runner.probe` are the two
seams every command goes through, so substituting them covers the whole surface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cairn import provision


def _options(**overrides):
    """Parsed arguments, with a role and a workdir that exist."""
    argv = ["--role", overrides.pop("role", "both")]
    for key, value in overrides.pop("flags", {}).items():
        argv += [key, str(value)]
    for flag in overrides.pop("switches", []):
        argv.append(flag)
    options = provision.parse_args(argv)
    for key, value in overrides.items():
        setattr(options, key, value)
    return options


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
    """Redirect every path the installer writes to, so no test can touch the real host.

    Also gives ``_cairn_executable()`` a real sibling to find, at a known path, so tests that
    exercise the timers/descriptor stages resolve deterministically instead of depending on
    whatever happens to be on ``PATH`` in the environment running the suite.
    """
    for name, relative in (
        ("CERT_DIR", "etc/cairn"),
        ("SYSTEM_CA_DIR", "usr/local/share/ca-certificates"),
        ("DOCKER_CERT_DIR", "etc/docker/certs.d"),
        ("SYSTEMD_DIR", "etc/systemd/system"),
        ("REGISTRY_DIR", "opt/cairn-registry"),
    ):
        monkeypatch.setattr(provision, name, tmp_path / relative)
    monkeypatch.setattr(provision, "DESCRIPTOR_PATH", tmp_path / "etc/cairn/environment.toml")

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "cairn").touch()
    monkeypatch.setattr(sys, "argv", [str(bindir / "cairn-provision")])

    workdir = tmp_path / "opt/cairn"
    workdir.mkdir(parents=True)
    return workdir


# --- roles: each host does only what its role implies ------------------------


def test_a_builder_neither_surveys_nor_backs_up_nor_is_described():
    """A build machine has no ERPNext site. `bench backup` there would be asking a question of
    a container that does not exist, and a descriptor describes a *running* deployment."""
    assert "backup" not in provision.BUILDER_STAGES
    assert "recon" not in provision.BUILDER_STAGES
    assert "descriptor" not in provision.BUILDER_STAGES


def test_a_target_hosts_no_registry():
    """It pulls from the builder's."""
    assert "registry" not in provision.TARGET_STAGES


def test_a_target_backs_up_before_anything_else_changes():
    stages = provision.TARGET_STAGES
    assert "backup" in stages
    assert stages.index("backup") < stages.index("descriptor")


def test_both_is_the_union_and_still_backs_up_first():
    """The bootstrap case: one box doing each. The ordering guarantee must survive it."""
    stages = provision.BOTH_STAGES
    assert set(stages) == set(provision.BUILDER_STAGES) | set(provision.TARGET_STAGES)
    assert stages.index("backup") < stages.index("registry")
    assert stages.index("preflight") == 0


def test_descriptor_precedes_registry_on_a_bootstrap_box():
    """`cairn adopt` needs exactly one compose project running to auto-detect it. If `registry`
    ran first, its own `cairn-registry` project would make every fresh `--role both` install
    ambiguous for a reason that has nothing to do with the actual site."""
    stages = provision.BOTH_STAGES
    assert stages.index("descriptor") < stages.index("registry")


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

    with pytest.raises(provision.Aborted, match=expected):
        provision.STAGES[stage](runner, _options(role=role))


def test_admin_group_stage_runs_before_registry_and_descriptor():
    """The setgid bit must predate every file those stages write (`ADR-043`)."""
    for stages in (provision.BUILDER_STAGES, provision.TARGET_STAGES, provision.BOTH_STAGES):
        assert stages.index("admin-group") < stages.index("timers")
        if "registry" in stages:
            assert stages.index("admin-group") < stages.index("registry")
        if "descriptor" in stages:
            assert stages.index("admin-group") < stages.index("descriptor")


def test_an_unknown_stage_lists_the_real_ones():
    with pytest.raises(provision.Aborted, match="unknown stage"):
        provision.stages_for("both", "registery")


def test_a_stage_outside_the_role_is_refused_by_name():
    with pytest.raises(provision.Aborted, match="does not apply to role"):
        provision.stages_for("target", "registry")


# --- rule 5: gate before acting ---------------------------------------------


def test_preflight_reports_every_check_before_stopping(monkeypatch):
    """An installer that dies on the first problem makes the operator discover prerequisites
    one reboot at a time."""
    runner = Recorder()
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", False, "no"))

    with pytest.raises(provision.Aborted, match="prerequisite"):
        provision.stage_preflight(runner, _options(role="target"))

    assert "docker" in runner.output
    assert "free disk" in runner.output
    assert "available memory" in runner.output


def test_preflight_asks_a_builder_for_build_tools_and_a_target_for_none(monkeypatch):
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", True, "ok"))

    builder = Recorder()
    with pytest.raises(provision.Aborted):
        provision.stage_preflight(builder, _options(role="builder"))
    assert "buildx" in builder.output

    target = Recorder()
    with pytest.raises(provision.Aborted):
        provision.stage_preflight(target, _options(role="target"))
    assert "buildx" not in target.output


def test_the_disk_gate_uses_the_documented_floor(monkeypatch):
    monkeypatch.setattr(
        provision.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    assert provision._check_disk().ok is False

    monkeypatch.setattr(
        provision.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )
    assert provision._check_disk().ok is True


def test_disk_check_targets_dockers_actual_data_dir(monkeypatch):
    """A separate mount for Docker data is common on a target; `/` having room says nothing
    about it."""
    runner = Recorder(answers={"docker info": "/mnt/docker-data\n"})
    assert provision._docker_data_dir(runner) == Path("/mnt/docker-data")

    checked = []
    monkeypatch.setattr(
        provision.shutil,
        "disk_usage",
        lambda path: checked.append(path) or type("U", (), {"free": 40_000_000_000})(),
    )
    provision._check_disk(provision._docker_data_dir(runner))
    assert checked == [Path("/mnt/docker-data")]


def test_disk_check_falls_back_to_root_when_docker_cannot_answer():
    """Not installed, or this preflight is what would install it — either way, `/` is the
    same floor the check always used."""
    runner = Recorder()  # no answers: `docker info` yields nothing, like a missing engine
    assert provision._docker_data_dir(runner) == Path("/")


def test_skip_disk_free_overrides_only_the_disk_check(monkeypatch):
    """`--skip-disk-free` is a named exception to rule 5, not a hole in it: every other
    prerequisite must still gate the run."""
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", False, "no"))
    monkeypatch.setattr(
        provision.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    runner = Recorder()

    with pytest.raises(provision.Aborted, match="root"):
        provision.stage_preflight(runner, _options(role="target", skip_disk_free=True))

    assert "FAIL" in runner.output  # the disk failure is still reported, not hidden
    assert "overridden by --skip-disk-free" in runner.output


def test_skip_disk_free_lets_a_short_disk_run_proceed(monkeypatch):
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", True, "ok"))
    monkeypatch.setattr(
        provision, "_check_command",
        lambda runner, label, command: provision.Check(label, True, "ok"),
    )
    monkeypatch.setattr(
        provision, "_check_memory", lambda: provision.Check("available memory", True, "ok")
    )
    monkeypatch.setattr(
        provision.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    runner = Recorder()

    provision.stage_preflight(runner, _options(role="target", skip_disk_free=True))

    assert any("overridden" in warning for warning in runner.report.warnings)


def test_memory_is_read_as_available_not_free(tmp_path):
    """MemFree excludes reclaimable cache and would make a healthy host look starved."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       8039024 kB\nMemFree:          201234 kB\nMemAvailable:    6291456 kB\n",
        encoding="utf-8",
    )

    assert provision.read_available_memory_gb(meminfo) == pytest.approx(6.44, abs=0.05)


def test_unreadable_meminfo_is_a_failed_check_not_a_crash(tmp_path):
    assert provision.read_available_memory_gb(tmp_path / "absent") is None


# --- locating the sibling `cairn` executable ---------------------------------


def test_cairn_executable_prefers_a_sibling_binary(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "cairn").touch()
    monkeypatch.setattr(sys, "argv", [str(bindir / "cairn-provision")])

    assert provision._cairn_executable() == bindir / "cairn"


def test_cairn_executable_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "cairn-provision")])
    monkeypatch.setattr(provision.shutil, "which", lambda name: "/usr/local/bin/cairn")

    assert provision._cairn_executable() == Path("/usr/local/bin/cairn")


def test_cairn_executable_raises_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "cairn-provision")])
    monkeypatch.setattr(provision.shutil, "which", lambda name: None)

    with pytest.raises(provision.Aborted, match="cannot find the `cairn` executable"):
        provision._cairn_executable()


# --- rule 2: the dry run is truthful ----------------------------------------


def test_a_dry_run_writes_nothing(tmp_path):
    runner = provision.Runner(dry_run=True, force=False)
    target = tmp_path / "written.toml"

    runner.write(target, "x = 1\n", what="a file")

    assert not target.exists()


def test_a_dry_run_still_prints_the_path_and_mode(tmp_path):
    runner = Recorder(dry_run=True)
    provision.Runner.write(runner, tmp_path / "f.conf", "x\n", mode=0o600, what="a file")

    assert "600" in runner.output
    assert "f.conf" in runner.output


def test_a_dry_run_reads_the_host_anyway():
    """A dry run that cannot see the host cannot tell you what it would do — reading is not a
    mutation."""
    runner = provision.Runner(dry_run=True, force=False)

    assert runner.probe(["true"]) is not None


# --- rule 3: never silently overwrite ---------------------------------------


def test_an_existing_different_file_is_refused_without_force(tmp_path):
    target = tmp_path / "environment.toml"
    target.write_text("environment = \"old\"\n", encoding="utf-8")
    runner = provision.Runner(dry_run=False, force=False)

    with pytest.raises(provision.Aborted, match="--force"):
        runner.write(target, 'environment = "new"\n', what="descriptor")

    assert target.read_text(encoding="utf-8") == 'environment = "old"\n'


def test_force_replaces_but_keeps_the_previous_file(tmp_path):
    target = tmp_path / "environment.toml"
    target.write_text('environment = "old"\n', encoding="utf-8")
    runner = provision.Runner(dry_run=False, force=True)

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
    os.chmod(target, 0o644)  # pin the starting mode; the ambient umask is not the point here
    runner = provision.Runner(dry_run=False, force=False)

    runner.write(target, "services: {}\n", what="registry compose")

    assert runner.report.done == []
    assert any("already correct" in note for note in runner.report.skipped)


def test_identical_content_with_a_drifted_mode_is_still_corrected(tmp_path):
    """Convergence (rule 1) covers the mode, not just the content — the directory's setgid bit
    only propagates group *ownership* to a new file, never its permission bits, so a file
    created under an unrelated umask can drift from what sharing `/etc/cairn` requires."""
    target = tmp_path / "environment.toml"
    target.write_text('environment = "test"\n', encoding="utf-8")
    os.chmod(target, 0o644)
    runner = provision.Runner(dry_run=False, force=False)

    runner.write(target, 'environment = "test"\n', mode=0o664, what="descriptor")

    assert (target.stat().st_mode & 0o777) == 0o664
    assert any("corrected" in line for line in runner.report.done)


def test_a_dry_run_reports_but_does_not_correct_a_drifted_mode(tmp_path):
    target = tmp_path / "environment.toml"
    target.write_text('environment = "test"\n', encoding="utf-8")
    os.chmod(target, 0o644)
    runner = provision.Runner(dry_run=True, force=False)

    runner.write(target, 'environment = "test"\n', mode=0o664, what="descriptor")

    assert (target.stat().st_mode & 0o777) == 0o644
    assert any("would correct" in line for line in runner.report.done)


def test_writing_twice_converges(tmp_path):
    target = tmp_path / "unit.service"
    runner = provision.Runner(dry_run=False, force=False)

    runner.write(target, "[Service]\n", what="unit")
    runner.write(target, "[Service]\n", what="unit")

    assert not target.with_suffix(".service.cairn-backup").exists()


# --- rule 4: no secrets ------------------------------------------------------


def test_the_certificate_key_is_owner_only(sandbox, monkeypatch):
    """Key material the installer creates must not be world-readable."""
    modes = {}
    monkeypatch.setattr(provision.os, "chmod", lambda path, mode: modes.setdefault(path, mode))
    runner = Recorder(answers={"curl": "ok"})

    provision.stage_registry(runner, _options(role="builder", workdir=sandbox, force=True))

    assert modes[provision.CERT_DIR / "registry.key"] == 0o600


def test_the_registry_has_no_credentials_to_leak():
    """A localhost-bound registry needs no auth, so there is no secret in this file at all."""
    rendered = provision.registry_compose()

    assert "PASSWORD" not in rendered.upper()
    assert "htpasswd" not in rendered
    assert "AUTH" not in rendered.upper()


# --- the shared admin group (BR-CFG-015, BR-DEPLOY-022, ADR-043) -------------


def test_admin_group_is_created_when_absent(sandbox, monkeypatch):
    gids = iter([None, 4242])  # absent, then present after "creation"
    monkeypatch.setattr(provision, "_group_gid", lambda name: next(gids))
    monkeypatch.setattr(provision.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    provision.stage_admin_group(runner, _options(role="both"))

    assert runner.ran("groupadd cairn-admins")
    assert any("created group" in line for line in runner.report.done)
    assert provision.CERT_DIR.is_dir()
    assert (provision.CERT_DIR.stat().st_mode & 0o7777) == provision.SHARED_CONFIG_MODE


def test_admin_group_left_alone_when_it_already_exists(sandbox, monkeypatch):
    """Idempotent (`BR-DEPLOY-021` rule 1): an existing group is reported, not recreated."""
    monkeypatch.setattr(provision, "_group_gid", lambda name: 4242)
    monkeypatch.setattr(provision.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    provision.stage_admin_group(runner, _options(role="both"))

    assert not runner.ran("groupadd")
    assert any("already exists" in line for line in runner.report.skipped)


def test_admin_group_name_is_configurable(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "_group_gid", lambda name: None)
    monkeypatch.setattr(provision.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    provision.stage_admin_group(
        runner, _options(role="both", flags={"--admin-group": "ops-team"})
    )

    assert runner.ran("groupadd ops-team")


def test_admin_group_already_correct_is_not_rechowned(sandbox, monkeypatch):
    """Idempotent: matching group and mode are reported and left untouched."""
    provision.CERT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(provision.CERT_DIR, provision.SHARED_CONFIG_MODE)
    own_gid = provision.CERT_DIR.stat().st_gid
    monkeypatch.setattr(provision, "_group_gid", lambda name: own_gid)
    chown_calls = []
    monkeypatch.setattr(provision.os, "chown", lambda *a: chown_calls.append(a))
    runner = Recorder()

    provision.stage_admin_group(runner, _options(role="both"))

    assert not chown_calls
    assert any("already correct" in line for line in runner.report.skipped)


def test_no_admin_group_flag_skips_the_stage_entirely(sandbox):
    runner = Recorder()

    provision.stage_admin_group(runner, _options(role="both", switches=["--no-admin-group"]))

    assert not runner.commands
    assert any("skipped" in line for line in runner.report.skipped)
    assert not provision.CERT_DIR.exists()


def test_admin_group_dry_run_writes_nothing(sandbox, monkeypatch):
    monkeypatch.setattr(provision, "_group_gid", lambda name: None)
    runner = Recorder(dry_run=True)

    provision.stage_admin_group(runner, _options(role="both"))

    assert not provision.CERT_DIR.exists()


def test_no_admin_group_flag_clears_the_parsed_option():
    options = provision.parse_args(["--role", "builder", "--no-admin-group"])

    assert options.admin_group is None


def test_admin_group_defaults_to_cairn_admins():
    options = provision.parse_args(["--role", "builder"])

    assert options.admin_group == provision.DEFAULT_ADMIN_GROUP


# --- the registry ------------------------------------------------------------


def test_the_certificate_covers_localhost_and_the_private_ip():
    """The private IP is included now so the certificate survives builder and target splitting;
    reissuing later means re-trusting it on every host that already had it."""
    sans = provision.subject_alt_names("10.0.0.5")

    assert "DNS:localhost" in sans
    assert "IP:127.0.0.1" in sans
    assert "IP:10.0.0.5" in sans


def test_no_private_ip_still_yields_a_usable_certificate():
    sans = provision.subject_alt_names(None)

    assert "DNS:localhost" in sans
    assert "IP:" in sans


def test_the_registry_binds_to_localhost_only():
    """Never exposed: there is no auth, so reachability is the whole of the access control."""
    rendered = provision.registry_compose()

    assert f'"127.0.0.1:{provision.REGISTRY_PORT}:{provision.REGISTRY_PORT}"' in rendered


def test_the_registry_carries_the_cairn_managed_label():
    """So `cairn adopt` can recognize this project as cairn's own infrastructure by label —
    never by assuming anything from the `cairn-registry` project name."""
    assert f'"{provision.CAIRN_MANAGED_LABEL}=true"' in provision.registry_compose()


def test_the_registry_can_delete_versions():
    """What makes keep-N retention possible later; some hosted registries cannot do it at all."""
    assert "REGISTRY_STORAGE_DELETE_ENABLED" in provision.registry_compose()


def test_the_registry_is_verified_over_tls_before_being_claimed(sandbox):
    """Rule 6. An untrusted CA fails here rather than at the first push."""
    provision.CERT_DIR.mkdir(parents=True)
    (provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={})  # curl answers nothing

    with pytest.raises(provision.Aborted, match="did not answer over TLS"):
        provision.stage_registry(runner, _options(role="builder", workdir=sandbox))


def test_the_certificate_is_trusted_in_both_stores(sandbox):
    """Python reads the system bundle; Docker reads its own per-registry directory."""
    provision.CERT_DIR.mkdir(parents=True)
    (provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    provision.stage_registry(runner, _options(role="builder", workdir=sandbox))

    system_ca = provision.SYSTEM_CA_DIR / "cairn-registry.crt"
    assert system_ca.read_text(encoding="utf-8") == "cert\n"
    docker_ca = provision.DOCKER_CERT_DIR / f"localhost:{provision.REGISTRY_PORT}" / "ca.crt"
    assert docker_ca.read_text(encoding="utf-8") == "cert\n"
    assert runner.ran("update-ca-certificates")


def test_a_renewed_certificate_forces_the_registry_container_to_recreate(sandbox, monkeypatch):
    """A running container has the old cert loaded in memory; `up -d` alone would leave it
    serving a certificate nothing trusts anymore, since a changed bind-mounted file is
    invisible to compose's own change detection (rule 1: re-running MUST converge)."""
    monkeypatch.setattr(provision.os, "chmod", lambda path, mode: None)
    provision.CERT_DIR.mkdir(parents=True)
    (provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    provision.stage_registry(runner, _options(role="builder", workdir=sandbox, force=True))

    assert runner.ran("up -d --force-recreate")


def test_a_reused_certificate_leaves_the_registry_container_alone(sandbox):
    provision.CERT_DIR.mkdir(parents=True)
    (provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    provision.stage_registry(runner, _options(role="builder", workdir=sandbox))

    assert runner.ran("up -d")
    assert not runner.ran("--force-recreate")


# --- backup: verified, not assumed ------------------------------------------


def test_a_backup_that_produces_no_dump_stops_the_run(monkeypatch):
    """The whole reason this stage exists is that bench migrate is irreversible."""
    runner = Recorder(answers={"compose ls": '[{"Name": "erp"}]'})  # ls of backups answers nothing

    with pytest.raises(provision.Aborted, match="no dump could be found"):
        provision.stage_backup(runner, _options(role="target"))


def test_a_verified_backup_is_recorded_and_the_operator_told_to_copy_it_off(monkeypatch):
    runner = Recorder(
        answers={
            "compose ls": '[{"Name": "erp"}]',
            "private/backups": "-rw-r--r-- 1 frappe frappe 4096 dump.sql.gz\n",
        }
    )

    provision.stage_backup(runner, _options(role="target"))

    assert any("verified pre-install backup" in note for note in runner.report.done)
    assert any("copy it off" in note for note in runner.report.warnings)


def test_skipping_the_backup_is_recorded_as_a_warning():
    """Allowed, but never silent — the operator should see it in the summary."""
    runner = Recorder()

    provision.stage_backup(runner, _options(role="target", skip_backup=True))

    assert any("irreversible" in note for note in runner.report.warnings)
    assert not runner.commands


def test_backup_backs_up_every_site():
    runner = Recorder(
        answers={"compose ls": '[{"Name": "erp"}]', "private/backups": "dump.sql.gz\n"}
    )

    provision.stage_backup(runner, _options(role="target"))

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

    provision.stage_recon(runner, _options(role="target"))

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

    provision.stage_recon(runner, _options(role="target"))

    assert any("no existing stack" in note for note in runner.report.warnings)


# --- descriptor --------------------------------------------------------------


def test_the_descriptor_comes_from_cairn_adopt(sandbox):
    rendered = 'environment = "test"\nsite = "erp.test"\n'
    runner = Recorder(answers={"adopt": rendered})

    provision.stage_descriptor(runner, _options(role="target", workdir=sandbox))

    assert provision.DESCRIPTOR_PATH.read_text(encoding="utf-8") == rendered
    assert any("adopt" in " ".join(str(p) for p in probe) for probe in runner.probes)


def test_a_descriptor_that_does_not_parse_stops_the_run(sandbox):
    """Rule 6: reconcile refusing it later is a worse failure than refusing now."""
    runner = Recorder(answers={"adopt": "environment = \n"})

    with pytest.raises(provision.Aborted, match="does not parse"):
        provision.stage_descriptor(runner, _options(role="target", workdir=sandbox))


def test_a_failing_adopt_names_the_command_to_rerun(sandbox):
    """Rule 7: every action is reportable as something the operator can run by hand."""
    runner = Recorder(answers={})

    with pytest.raises(provision.Aborted, match="adopt"):
        provision.stage_descriptor(runner, _options(role="target", workdir=sandbox))


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
    service, timer = provision.split_units(UNITS)

    assert "[Service]" in service and "[Timer]" not in service
    assert "[Timer]" in timer and "[Service]" not in timer


def test_unexpected_unit_output_fails_loudly_rather_than_installing_half_a_unit():
    assert provision.split_units("something else entirely") == (None, None)


def test_the_reconcile_unit_is_pointed_at_the_installed_binary(sandbox, tmp_path):
    """`cairn-provision` resolves `cairn` as its own sibling, not via a PATH lookup that may
    not include it under `sudo`."""
    runner = Recorder(answers={"systemd-units": UNITS})

    provision.stage_timers(runner, _options(role="target", workdir=sandbox))

    service = (provision.SYSTEMD_DIR / "cairn-reconcile.service").read_text(encoding="utf-8")
    assert f"ExecStart={tmp_path}/bin/cairn reconcile" in service


def test_a_builder_gets_a_build_timer_and_no_reconcile_timer(sandbox):
    runner = Recorder(answers={"systemd-units": UNITS})

    provision.stage_timers(runner, _options(role="builder", workdir=sandbox))

    assert (provision.SYSTEMD_DIR / "cairn-build.timer").exists()
    assert not (provision.SYSTEMD_DIR / "cairn-reconcile.timer").exists()


def test_a_target_gets_a_reconcile_timer_and_no_build_timer(sandbox):
    runner = Recorder(answers={"systemd-units": UNITS})

    provision.stage_timers(runner, _options(role="target", workdir=sandbox))

    assert (provision.SYSTEMD_DIR / "cairn-reconcile.timer").exists()
    assert not (provision.SYSTEMD_DIR / "cairn-build.timer").exists()


def test_timers_are_enabled_but_never_started(sandbox):
    """A timer firing before anyone has confirmed the manifest turns one wrong configuration
    into a wrong deploy every quarter of an hour."""
    runner = Recorder(answers={"systemd-units": UNITS})

    provision.stage_timers(runner, _options(role="both", workdir=sandbox))

    assert runner.ran("systemctl enable")
    assert not runner.ran("systemctl start")
    assert any("NOT started" in note for note in runner.report.warnings)


def test_the_build_service_sets_a_working_directory():
    """Required, not decoration: cairn finds a manifest not given explicitly by searching
    upward from the working directory."""
    rendered = provision.build_service(
        _options(role="builder", workdir=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "WorkingDirectory=/opt/cairn" in rendered


def test_the_build_service_does_not_restart_on_failure():
    """A restart loop against a failing build turns a bad build into a busy one."""
    rendered = provision.build_service(
        _options(role="builder", workdir=Path("/opt/cairn")), Path("/opt/cairn/build.sh")
    )

    assert "Type=oneshot" in rendered
    assert "Restart=" not in rendered


def test_the_build_timer_measures_from_the_end_of_the_last_run():
    """A build takes tens of minutes; the next one must not already be due when it finishes."""
    rendered = provision.build_timer(_options(role="builder", build_interval="15min"))

    assert "OnUnitInactiveSec=15min" in rendered
    assert "OnCalendar=" not in rendered


def test_the_build_script_builds_then_advances_the_pointer(monkeypatch):
    monkeypatch.setattr(provision, "_cairn_executable", lambda: Path("/opt/cairn-venv/bin/cairn"))
    rendered = provision.build_script(
        _options(
            role="builder",
            workdir=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/deployments/acme/cairn.toml"),
            environment="test",
        )
    )

    assert "build --manifest" in rendered
    assert "retag test --latest --yes" in rendered
    assert rendered.index("build --manifest") < rendered.index("retag test")


def test_a_manifest_path_with_spaces_is_quoted_in_the_script(monkeypatch):
    monkeypatch.setattr(provision, "_cairn_executable", lambda: Path("/opt/cairn-venv/bin/cairn"))
    rendered = provision.build_script(
        _options(
            role="builder",
            workdir=Path("/opt/cairn"),
            manifest=Path("/opt/cairn/my deployments/cairn.toml"),
            environment="test",
        )
    )

    assert "'/opt/cairn/my deployments/cairn.toml'" in rendered


# --- the run as a whole ------------------------------------------------------


def test_a_failed_gate_exits_two_and_changes_nothing(monkeypatch):
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", False, "no"))

    assert provision.main(["--role", "target", "--only", "preflight"]) == 2


def test_a_dry_run_of_a_whole_role_reports_and_exits_zero(monkeypatch):
    monkeypatch.setattr(provision, "_check_root", lambda: provision.Check("root", True, "ok"))
    for name in ("recon", "backup", "descriptor", "timers", "registry"):
        monkeypatch.setitem(provision.STAGES, name, lambda runner, options: None)
    monkeypatch.setitem(provision.STAGES, "preflight", lambda runner, options: None)

    assert provision.main(["--role", "both", "--dry-run"]) == 0


def test_the_manifest_defaults_beside_the_workdir():
    options = provision.parse_args(["--role", "builder", "--workdir", "/opt/cairn"])

    assert options.manifest == Path("/opt/cairn/cairn.toml")


def test_an_explicit_manifest_wins():
    options = provision.parse_args(
        ["--role", "builder", "--manifest", "/srv/acme/cairn.toml"]
    )

    assert options.manifest == Path("/srv/acme/cairn.toml")
