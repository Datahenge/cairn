"""Tests for the emitted systemd units (`BR-CLI-019`, `ADR-035`).

The units are rendered text, so these tests assert the properties that make them *correct
for cairn* rather than merely well-formed — the ones an operator writing a unit by hand would
have to know cairn's internals to get right.
"""

from __future__ import annotations

from cairn import systemd


def test_the_service_runs_one_pass_and_does_not_restart():
    """A pass ends, so `oneshot`; and a failed deploy must halt and be seen, so no restart —
    a restart loop against a failing migration turns a bad deploy into a busy one."""
    rendered = systemd.units()

    assert "Type=oneshot" in rendered.service
    assert "Restart=" not in rendered.service


def test_the_service_configures_no_log_file():
    """journald already owns the record; a second copy is the thing cairn must not create."""
    for unit in (rendered := systemd.units()).service, rendered.timer:
        assert "StandardOutput=" not in unit
        assert "StandardError=" not in unit
        assert ".log" not in unit


def test_the_service_waits_for_docker():
    """A pass that starts before the engine does fails for a reason nothing else explains."""
    rendered = systemd.units()

    assert "docker.service" in rendered.service
    assert "network-online.target" in rendered.service


def test_the_timer_is_persistent_and_jittered():
    """Persistent is safe *because* a pass is idempotent and single-flight: a catch-up that
    collides with a running pass exits reporting the lock instead of queueing."""
    rendered = systemd.units()

    assert "Persistent=true" in rendered.timer
    assert "RandomizedDelaySec=" in rendered.timer


def test_the_timer_measures_from_the_end_of_the_last_run():
    """OnUnitInactiveSec, not OnCalendar: a pass that takes nine minutes must not have the
    next one already due when it finishes."""
    rendered = systemd.units()

    assert "OnUnitInactiveSec=" in rendered.timer
    assert "OnCalendar=" not in rendered.timer


def test_the_timer_names_the_service_it_drives():
    rendered = systemd.units()

    assert f"Unit={systemd.UNIT_NAME}.service" in rendered.timer


def test_the_interval_and_user_reach_the_units():
    rendered = systemd.units(interval="15min", user="cairn")

    assert "OnUnitInactiveSec=15min" in rendered.timer
    assert "User=cairn" in rendered.service


def test_every_host_specific_value_is_reported():
    """BR-CLI-019: a wrong guess must be visible before installation, not after it fails."""
    rendered = systemd.units(executable="/opt/cairn/bin/cairn", user="deploy", interval="3min")
    reported = "\n".join(rendered.assumptions)

    assert "/opt/cairn/bin/cairn" in reported
    assert "deploy" in reported
    assert "3min" in reported


def test_the_service_invokes_reconcile_with_the_reported_executable():
    """The unit must run the same cairn that printed it — a bare name may resolve differently
    for root than for the invoking user."""
    rendered = systemd.units(executable="/opt/cairn/bin/cairn")

    assert "ExecStart=/opt/cairn/bin/cairn reconcile" in rendered.service


def test_both_units_are_printed_under_the_filenames_to_install_them_as():
    rendered = systemd.units().render()

    assert f"/etc/systemd/system/{systemd.UNIT_NAME}.service" in rendered
    assert f"/etc/systemd/system/{systemd.UNIT_NAME}.timer" in rendered
    assert "[Service]" in rendered
    assert "[Timer]" in rendered


def test_the_hint_is_manual_and_never_writes_for_you():
    """ADR-035: cairn performs no privileged host writes, so the hint must tell the operator
    to run the privileged parts themselves."""
    hint = "\n".join(systemd.install_hint())

    assert "sudo" in hint
    assert "daemon-reload" in hint
    assert "journalctl" in hint


def test_an_absent_cairn_on_path_falls_back_to_the_module(monkeypatch):
    """A cairn installed without its console script on PATH must still produce a unit that
    runs, rather than one that fails at 3am."""
    monkeypatch.setattr(systemd.shutil, "which", lambda name: None)

    assert "-m cairn" in systemd.units().executable
