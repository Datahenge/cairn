"""Tests for the generic `setup` execution engine (`BR-DEPLOY-021`), shared by every role's
installer (`cairn-build setup`, `cairn-adopt setup`, `cairn-registry setup`).

Extracted from `test_provision.py` when `setup_runner.py` split out of `provision.py`
(`ADR-048`) — the engine itself (Runner, preflight checks, admin-group sharing) is role-agnostic
and belongs here; role-specific stages stay tested in each role's own test file.

Nothing here runs docker, openssl, or systemctl. `Runner.run` and `Runner.probe` are the two
seams every command goes through, so substituting them covers the whole surface.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cairn import setup_runner


def _options(**overrides) -> setup_runner.SetupOptions:
    return setup_runner.SetupOptions(**overrides)


class Recorder(setup_runner.Runner):
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
    """Redirect every path `stage_admin_group` writes to, so no test can touch the real host."""
    monkeypatch.setattr(setup_runner, "CERT_DIR", tmp_path / "etc/cairn")
    return tmp_path


def _preflight(runner: Recorder, options: setup_runner.SetupOptions, *, extra=()) -> None:
    checks, disk_check = setup_runner.base_preflight_checks(runner, options)
    setup_runner.fail_on_checks(list(checks) + list(extra), disk_check, options)


# --- rule 5: gate before acting ---------------------------------------------


def test_preflight_reports_every_check_before_stopping(monkeypatch):
    """An installer that dies on the first problem makes the operator discover prerequisites
    one reboot at a time."""
    runner = Recorder()
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )

    with pytest.raises(setup_runner.Aborted, match="prerequisite"):
        _preflight(runner, _options())

    assert "docker" in runner.output
    assert "free disk" in runner.output
    assert "available memory" in runner.output


def test_the_disk_gate_uses_the_documented_floor(monkeypatch):
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    assert setup_runner.check_disk().ok is False

    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )
    assert setup_runner.check_disk().ok is True


def test_disk_check_targets_dockers_actual_data_dir(monkeypatch):
    """A separate mount for Docker data is common on a target; `/` having room says nothing
    about it."""
    runner = Recorder(answers={"docker info": "/mnt/docker-data\n"})
    assert setup_runner._docker_data_dir(runner) == Path("/mnt/docker-data")

    checked = []
    monkeypatch.setattr(
        setup_runner.shutil,
        "disk_usage",
        lambda path: checked.append(path) or type("U", (), {"free": 40_000_000_000})(),
    )
    setup_runner.check_disk(setup_runner._docker_data_dir(runner))
    assert checked == [Path("/mnt/docker-data")]


def test_disk_check_falls_back_to_root_when_docker_cannot_answer():
    """Not installed, or this preflight is what would install it — either way, `/` is the
    same floor the check always used."""
    runner = Recorder()  # no answers: `docker info` yields nothing, like a missing engine
    assert setup_runner._docker_data_dir(runner) == Path("/")


def test_skip_disk_free_overrides_only_the_disk_check(monkeypatch):
    """`--skip-disk-free` is a named exception to rule 5, not a hole in it: every other
    prerequisite must still gate the run."""
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    runner = Recorder()

    with pytest.raises(setup_runner.Aborted, match="root"):
        _preflight(runner, _options(skip_disk_free=True))

    assert "FAIL" in runner.output  # the disk failure is still reported, not hidden
    assert "overridden by --skip-disk-free" in runner.output


def test_skip_disk_free_lets_a_short_disk_run_proceed(monkeypatch):
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(
        setup_runner,
        "check_command",
        lambda runner, label, command: setup_runner.Check(label, True, "ok"),
    )
    monkeypatch.setattr(
        setup_runner, "check_memory", lambda: setup_runner.Check("available memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 10_000_000_000})()
    )
    runner = Recorder()

    _preflight(runner, _options(skip_disk_free=True))

    assert any("overridden" in warning for warning in runner.report.warnings)


def test_memory_is_read_as_available_not_free(tmp_path):
    """MemFree excludes reclaimable cache and would make a healthy host look starved."""
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(
        "MemTotal:       8039024 kB\nMemFree:          201234 kB\nMemAvailable:    6291456 kB\n",
        encoding="utf-8",
    )

    assert setup_runner.read_available_memory_gb(meminfo) == pytest.approx(6.44, abs=0.05)


def test_unreadable_meminfo_is_a_failed_check_not_a_crash(tmp_path):
    assert setup_runner.read_available_memory_gb(tmp_path / "absent") is None


# --- rule 2: the dry run is truthful ----------------------------------------


def test_a_dry_run_writes_nothing(tmp_path):
    runner = setup_runner.Runner(dry_run=True, force=False)
    target = tmp_path / "written.toml"

    runner.write(target, "x = 1\n", what="a file")

    assert not target.exists()


def test_a_dry_run_still_prints_the_path_and_mode(tmp_path):
    runner = Recorder(dry_run=True)
    setup_runner.Runner.write(runner, tmp_path / "f.conf", "x\n", mode=0o600, what="a file")

    assert "600" in runner.output
    assert "f.conf" in runner.output


def test_a_dry_run_reads_the_host_anyway():
    """A dry run that cannot see the host cannot tell you what it would do — reading is not a
    mutation."""
    runner = setup_runner.Runner(dry_run=True, force=False)

    assert runner.probe(["true"]) is not None


# --- rule 3: never silently overwrite ---------------------------------------


def test_an_existing_different_file_is_refused_without_force(tmp_path):
    target = tmp_path / "adopt.toml"
    target.write_text('environment = "old"\n', encoding="utf-8")
    runner = setup_runner.Runner(dry_run=False, force=False)

    with pytest.raises(setup_runner.Aborted, match="--force"):
        runner.write(target, 'environment = "new"\n', what="descriptor")

    assert target.read_text(encoding="utf-8") == 'environment = "old"\n'


def test_force_replaces_but_keeps_the_previous_file(tmp_path):
    target = tmp_path / "adopt.toml"
    target.write_text('environment = "old"\n', encoding="utf-8")
    runner = setup_runner.Runner(dry_run=False, force=True)

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
    runner = setup_runner.Runner(dry_run=False, force=False)

    runner.write(target, "services: {}\n", what="registry compose")

    assert runner.report.done == []
    assert any("already correct" in note for note in runner.report.skipped)


def test_identical_content_with_a_drifted_mode_is_still_corrected(tmp_path):
    """Convergence (rule 1) covers the mode, not just the content — the directory's setgid bit
    only propagates group *ownership* to a new file, never its permission bits, so a file
    created under an unrelated umask can drift from what sharing `/etc/cairn` requires."""
    target = tmp_path / "adopt.toml"
    target.write_text('environment = "test"\n', encoding="utf-8")
    os.chmod(target, 0o644)
    runner = setup_runner.Runner(dry_run=False, force=False)

    runner.write(target, 'environment = "test"\n', mode=0o664, what="descriptor")

    assert (target.stat().st_mode & 0o777) == 0o664
    assert any("corrected" in line for line in runner.report.done)


def test_a_dry_run_reports_but_does_not_correct_a_drifted_mode(tmp_path):
    target = tmp_path / "adopt.toml"
    target.write_text('environment = "test"\n', encoding="utf-8")
    os.chmod(target, 0o644)
    runner = setup_runner.Runner(dry_run=True, force=False)

    runner.write(target, 'environment = "test"\n', mode=0o664, what="descriptor")

    assert (target.stat().st_mode & 0o777) == 0o644
    assert any("would correct" in line for line in runner.report.done)


def test_writing_twice_converges(tmp_path):
    target = tmp_path / "unit.service"
    runner = setup_runner.Runner(dry_run=False, force=False)

    runner.write(target, "[Service]\n", what="unit")
    runner.write(target, "[Service]\n", what="unit")

    assert not target.with_suffix(".service.cairn-backup").exists()


# --- the shared admin group (BR-CFG-015, BR-DEPLOY-022, ADR-043) -------------


def test_admin_group_is_created_when_absent(sandbox, monkeypatch):
    gids = iter([None, 4242])  # absent, then present after "creation"
    monkeypatch.setattr(setup_runner, "group_gid", lambda name: next(gids))
    monkeypatch.setattr(setup_runner.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    setup_runner.stage_admin_group(runner, _options())

    assert runner.ran("groupadd cairn-admins")
    assert any("created group" in line for line in runner.report.done)
    assert setup_runner.CERT_DIR.is_dir()
    assert (setup_runner.CERT_DIR.stat().st_mode & 0o7777) == setup_runner.SHARED_CONFIG_MODE


def test_admin_group_left_alone_when_it_already_exists(sandbox, monkeypatch):
    """Idempotent (`BR-DEPLOY-021` rule 1): an existing group is reported, not recreated."""
    monkeypatch.setattr(setup_runner, "group_gid", lambda name: 4242)
    monkeypatch.setattr(setup_runner.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    setup_runner.stage_admin_group(runner, _options())

    assert not runner.ran("groupadd")
    assert any("already exists" in line for line in runner.report.skipped)


def test_admin_group_name_is_configurable(sandbox, monkeypatch):
    monkeypatch.setattr(setup_runner, "group_gid", lambda name: None)
    monkeypatch.setattr(setup_runner.os, "chown", lambda *a, **k: None)
    runner = Recorder()

    setup_runner.stage_admin_group(runner, _options(admin_group="ops-team"))

    assert runner.ran("groupadd ops-team")


def test_admin_group_already_correct_is_not_rechowned(sandbox, monkeypatch):
    """Idempotent: matching group and mode are reported and left untouched."""
    setup_runner.CERT_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(setup_runner.CERT_DIR, setup_runner.SHARED_CONFIG_MODE)
    own_gid = setup_runner.CERT_DIR.stat().st_gid
    monkeypatch.setattr(setup_runner, "group_gid", lambda name: own_gid)
    chown_calls = []
    monkeypatch.setattr(setup_runner.os, "chown", lambda *a: chown_calls.append(a))
    runner = Recorder()

    setup_runner.stage_admin_group(runner, _options())

    assert not chown_calls
    assert any("already correct" in line for line in runner.report.skipped)


def test_no_admin_group_skips_the_stage_entirely(sandbox):
    """`--no-admin-group` is wired, at the CLI layer, to `admin_group=None`."""
    runner = Recorder()

    setup_runner.stage_admin_group(runner, _options(admin_group=None))

    assert not runner.commands
    assert any("skipped" in line for line in runner.report.skipped)
    assert not setup_runner.CERT_DIR.exists()


def test_admin_group_dry_run_writes_nothing(sandbox, monkeypatch):
    monkeypatch.setattr(setup_runner, "group_gid", lambda name: None)
    runner = Recorder(dry_run=True)

    setup_runner.stage_admin_group(runner, _options())

    assert not setup_runner.CERT_DIR.exists()


# --- the run as a whole ------------------------------------------------------


def test_an_unknown_stage_lists_the_real_ones():
    with pytest.raises(setup_runner.Aborted, match="unknown stage"):
        setup_runner.stages_for(("a", "b"), {"a": None, "b": None}, "c")


def test_a_failed_gate_exits_two_and_changes_nothing(monkeypatch):
    monkeypatch.setattr(
        setup_runner, "_check_root", lambda: setup_runner.Check("root", False, "no")
    )
    runner = setup_runner.Runner(dry_run=False, force=False)
    stage_funcs = {"preflight": lambda r, o: _preflight(r, o)}

    code = setup_runner.execute(
        runner, _options(), stage_funcs, ("preflight",), "preflight", program="cairn-adopt"
    )

    assert code == 2


def test_a_dry_run_of_a_whole_setup_reports_and_exits_zero():
    stub_funcs = {"a": lambda r, o: None, "b": lambda r, o: None}
    runner = setup_runner.Runner(dry_run=True, force=False)

    code = setup_runner.execute(
        runner, _options(), stub_funcs, ("a", "b"), None, program="cairn-adopt"
    )

    assert code == 0


def test_the_header_names_setup_by_default(capsys):
    """The header must not claim 'setup' while a setup-timer run is what's underway."""
    runner = setup_runner.Runner(dry_run=True, force=False)

    setup_runner.execute(runner, _options(), {}, (), None, program="cairn-build")

    assert "cairn-build setup (dry run)" in capsys.readouterr().err


def test_the_header_names_setup_timer_when_told_to(capsys):
    runner = setup_runner.Runner(dry_run=True, force=False)

    setup_runner.execute(
        runner, _options(), {}, (), None, program="cairn-build", verb="setup-timer"
    )

    assert "cairn-build setup-timer (dry run)" in capsys.readouterr().err


def test_the_manifest_defaults_beside_the_workdir():
    options = setup_runner.SetupOptions(workdir=Path("/opt/cairn"))

    assert options.manifest == Path("/opt/cairn/cairn.toml")


def test_an_explicit_manifest_wins():
    options = setup_runner.SetupOptions(
        workdir=Path("/opt/cairn"), manifest=Path("/srv/acme/cairn.toml")
    )

    assert options.manifest == Path("/srv/acme/cairn.toml")


# --- locating a sibling executable, shared by every role ---------------------


def test_find_executable_prefers_a_sibling_binary(tmp_path, monkeypatch):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "cairn-adopt").touch()
    monkeypatch.setattr(sys, "argv", [str(bindir / "cairn-adopt")])

    assert setup_runner.find_executable("cairn-adopt") == bindir / "cairn-adopt"


def test_find_executable_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "cairn-build")])
    monkeypatch.setattr(setup_runner.shutil, "which", lambda name: "/usr/local/bin/cairn-build")

    assert setup_runner.find_executable("cairn-build") == Path("/usr/local/bin/cairn-build")


def test_find_executable_raises_when_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "cairn-build")])
    monkeypatch.setattr(setup_runner.shutil, "which", lambda name: None)

    with pytest.raises(setup_runner.Aborted, match="cannot find the `cairn-build` executable"):
        setup_runner.find_executable("cairn-build")
