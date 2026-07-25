"""Tests for attended-mode build transcripts (BR-CLI-016, `ADR-031`)."""

from __future__ import annotations

import os
import stat
from datetime import datetime
from pathlib import Path

import pytest

from cairn import transcript
from cairn.errors import TranscriptError

# --- context detection (BR-CLI-016) -----------------------------------------


@pytest.mark.parametrize(
    ("attended", "explicit", "disabled", "expected"),
    [
        # Attended CLI: nobody else owns the record, so cairn keeps one.
        (True, None, False, True),
        # Target daemon and CI: journald / the CI log viewer already own it.
        (False, None, False, False),
        # Explicit --transcript overrides an unattended context (a CI job that wants
        # a file to upload as an artifact).
        (False, Path("/somewhere/build.log"), False, True),
        # --no-transcript overrides an attended one, and wins over --transcript.
        (True, None, True, False),
        (True, Path("/somewhere/build.log"), True, False),
    ],
)
def test_wanted_follows_the_three_contexts(monkeypatch, attended, explicit, disabled, expected):
    monkeypatch.setattr(transcript, "is_attended", lambda: attended)
    assert transcript.wanted(explicit=explicit, disabled=disabled) is expected


def test_attendedness_is_stderr_being_a_tty(monkeypatch):
    """One isatty() resolves all three contexts: neither journald nor CI has a TTY."""

    class _Stream:
        def __init__(self, tty):
            self._tty = tty

        def isatty(self):
            return self._tty

    monkeypatch.setattr(transcript.sys, "stderr", _Stream(True))
    assert transcript.is_attended() is True
    monkeypatch.setattr(transcript.sys, "stderr", _Stream(False))
    assert transcript.is_attended() is False


# --- location (BR-CLI-016) ---------------------------------------------------


def test_default_dir_is_uid_scoped_under_tmp():
    resolved = transcript.resolve_dir(None)
    assert resolved.parent == Path("/tmp")
    assert resolved.name == f"cairn-{os.getuid()}"


def test_configured_dir_wins_and_expands_user(monkeypatch):
    monkeypatch.setenv("HOME", "/home/somebody")
    assert transcript.resolve_dir("~/builds") == Path("/home/somebody/builds")


def test_filename_is_sortable_and_names_the_image():
    when = datetime(2026, 7, 25, 14, 2, 11)
    path = transcript.path_for(Path("/tmp/cairn-1000"), "erpnext-btu-v16", when)
    assert path.name == "2026-07-25T14-02-11--erpnext-btu-v16.log"
    assert ":" not in path.name  # travels badly off Linux


# --- directory safety (BR-CLI-016) ------------------------------------------


def test_new_directory_is_created_owner_only(tmp_path):
    directory = tmp_path / "cairn-1000"
    transcript.prepare_dir(directory)
    assert directory.is_dir()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700


def test_existing_owned_directory_is_accepted(tmp_path):
    directory = tmp_path / "cairn-1000"
    directory.mkdir(mode=0o700)
    transcript.prepare_dir(directory)  # must not raise


def test_symlinked_directory_is_refused(tmp_path):
    """A predictable name under world-writable /tmp invites a planted symlink."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    directory = tmp_path / "cairn-1000"
    directory.symlink_to(elsewhere, target_is_directory=True)

    with pytest.raises(TranscriptError, match="symlink"):
        transcript.prepare_dir(directory)


def test_non_directory_is_refused(tmp_path):
    path = tmp_path / "cairn-1000"
    path.write_text("not a directory", encoding="utf-8")
    with pytest.raises(TranscriptError, match="not a directory"):
        transcript.prepare_dir(path)


def test_directory_owned_by_another_user_is_refused(tmp_path, monkeypatch):
    directory = tmp_path / "cairn-1000"
    directory.mkdir(mode=0o700)
    monkeypatch.setattr(transcript, "_uid", lambda: os.getuid() + 1)

    with pytest.raises(TranscriptError, match="owned by another user"):
        transcript.prepare_dir(directory)


# --- recording (BR-CLI-016) --------------------------------------------------


def test_recording_writes_and_links_last_build(tmp_path):
    path = tmp_path / "logs" / "build.log"
    with transcript.recording(path) as recorder:
        recorder.write("engine output\n")
        transcript.record("a progress step")

    assert path.read_text(encoding="utf-8") == "engine output\na progress step\n"
    link = path.parent / transcript.LAST_BUILD_LINK
    assert link.is_symlink()
    assert os.readlink(link) == "build.log"  # relative: survives a directory move
    assert not (path.parent / transcript.LAST_FAILURE_LINK).exists()


def test_failure_is_retained_and_linked_separately(tmp_path):
    """A later success must not bury the failure someone is still debugging."""
    failed = tmp_path / "logs" / "failed.log"
    with pytest.raises(RuntimeError), transcript.recording(failed) as recorder:
        recorder.write("boom\n")
        raise RuntimeError("build failed")

    # The reason it stopped is the last line — the CLI's error handler runs outside the
    # recording block, so without this the transcript would omit the one line that matters.
    assert failed.read_text(encoding="utf-8") == "boom\nError: build failed\n"
    assert os.readlink(failed.parent / transcript.LAST_FAILURE_LINK) == "failed.log"

    later = tmp_path / "logs" / "ok.log"
    with transcript.recording(later) as recorder:
        recorder.write("fine\n")

    assert os.readlink(later.parent / transcript.LAST_BUILD_LINK) == "ok.log"
    assert os.readlink(later.parent / transcript.LAST_FAILURE_LINK) == "failed.log"


def test_record_is_a_no_op_when_unattended():
    """Nothing is recording, so the CLI's progress calls must simply do nothing."""
    assert transcript._current is None
    transcript.record("this goes nowhere")  # must not raise


def test_output_is_flushed_as_it_arrives(tmp_path):
    """An interrupted build must still leave a readable transcript."""
    path = tmp_path / "build.log"
    with transcript.recording(path) as recorder:
        recorder.write("first\n")
        assert path.read_text(encoding="utf-8") == "first\n"


def test_unwritable_destination_names_the_fix(tmp_path):
    directory = tmp_path / "readonly"
    directory.mkdir(mode=0o500)
    try:
        with (
            pytest.raises(TranscriptError, match="--no-transcript"),
            transcript.recording(directory / "build.log"),
        ):
            pass
    finally:
        directory.chmod(0o700)
