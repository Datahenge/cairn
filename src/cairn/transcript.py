"""Build transcripts for attended CLI use (BR-CLI-016, `ADR-031`).

cairn runs in three contexts, and the question separating them is not *where* it runs but
**whether something else already owns and retains the record**:

===========================  ==========================  ==========================
Context                      Owner of the record         Behavior
===========================  ==========================  ==========================
Target daemon (systemd)      journald                    stdout/stderr only
Unattended CLI (CI)          the CI system's log viewer  stdout/stderr only
Attended CLI (a terminal)    nobody                      terminal **and** a file
===========================  ==========================  ==========================

Only the third case gets a file. A CI runner *does* have a writable filesystem, so
"cannot write" would be a false rationale — the real one is that the runner is ephemeral
and the stream is already captured with search and retention.

Conveniently, one test resolves all three: neither journald nor a CI runner allocates a
TTY, so ``sys.stderr.isatty()`` is the whole detection. Explicit ``--transcript`` /
``--no-transcript`` remain for when that proxy is wrong.

Transcripts are **disposable diagnostics, not project artifacts**. They default under
``/tmp/cairn-<uid>/`` — self-cleaning, and outside any source tree, consistent with
`BR-BUILD-011` keeping byproducts out of cairn's own tree. Discoverability comes from a
``last-build.log`` symlink and from printing the path at *both* start and end, so it
survives a Ctrl-C or a lost terminal rather than scrolling away.
"""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import IO

from .errors import TranscriptError

#: Where the per-user transcript directory lives when build config names no other place.
DEFAULT_PARENT = Path("/tmp")

#: Directory name prefix; the uid suffix keeps users out of each other's way on a shared box.
DIR_PREFIX = "cairn-"

#: Stable handles, so the timestamped filename never has to be typed or remembered.
LAST_BUILD_LINK = "last-build.log"
LAST_FAILURE_LINK = "last-failure.log"

#: Colons are legal on Linux but travel badly; keep names sortable and portable.
STAMP_FORMAT = "%Y-%m-%dT%H-%M-%S"

_current: Transcript | None = None


class Transcript:
    """An open transcript file, and the symlinks that point at it."""

    def __init__(self, path: Path, handle: IO[str]) -> None:
        self.path = path
        self._handle = handle

    def write(self, text: str) -> None:
        """Append *text* verbatim, flushing so a killed process still leaves a usable file."""
        self._handle.write(text)
        self._handle.flush()

    def line(self, text: str = "") -> None:
        """Append *text* as one line."""
        self.write(f"{text}\n")

    def close(self) -> None:
        self._handle.close()


def record(text: str = "") -> None:
    """Append *text* as a line to the active transcript, if one is recording.

    A no-op when unattended, which is what lets the CLI's progress reporting call this
    unconditionally.
    """
    if _current is not None:
        _current.line(text)


def is_attended() -> bool:
    """Whether a human is watching — i.e. stderr is a terminal.

    stderr rather than stdout, because progress already goes there and a caller piping
    stdout (``cairn images --json | jq``) is still an attended session.
    """
    return sys.stderr.isatty()


def wanted(*, explicit: Path | None, disabled: bool) -> bool:
    """Decide whether to write a transcript for this invocation."""
    if disabled:
        return False
    return True if explicit is not None else is_attended()


def resolve_dir(configured: str | None = None) -> Path:
    """Return the transcript directory: *configured* if set, else ``/tmp/cairn-<uid>``."""
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_PARENT / f"{DIR_PREFIX}{_uid()}"


def path_for(directory: Path, image_name: str, when: datetime | None = None) -> Path:
    """Return the transcript path for *image_name*, timestamped and sortable.

    Named from the manifest's image name rather than the built tag, because the file has
    to be open before ref resolution can compute a tag — the resolution itself is part of
    what the transcript records. The tag is written into the file's header instead.
    """
    stamp = (when or datetime.now().astimezone()).strftime(STAMP_FORMAT)
    return directory / f"{stamp}--{image_name}.log"


@contextmanager
def recording(path: Path) -> Iterator[Transcript]:
    """Open *path* as the active transcript for the enclosed block.

    On the way out the ``last-build.log`` symlink is pointed here; if the block raised,
    the failure is written as the transcript's last line and ``last-failure.log`` is
    pointed here too, so a later successful build cannot bury the failure someone is
    still debugging.

    Recording the exception here rather than at the CLI's error handler is deliberate:
    that handler runs *outside* this block, so the one line an operator most wants —
    why it stopped — would otherwise be the only thing missing from the transcript.
    """
    global _current

    prepare_dir(path.parent)
    try:
        handle = path.open("w", encoding="utf-8")
    except OSError as exc:
        raise TranscriptError(
            f"Cannot write a build transcript to {path} ({exc.strerror}). "
            f"Set `transcript_dir` in build config, or pass --no-transcript."
        ) from exc

    transcript = Transcript(path, handle)
    previous, _current = _current, transcript
    try:
        yield transcript
    except BaseException as exc:
        transcript.line(f"Error: {exc}" if str(exc) else f"Stopped: {type(exc).__name__}")
        _link(path.parent / LAST_FAILURE_LINK, path)
        raise
    finally:
        _current = previous
        _link(path.parent / LAST_BUILD_LINK, path)
        transcript.close()


def prepare_dir(directory: Path) -> None:
    """Create *directory* mode 0700, or verify an existing one is safely ours.

    The default lives under world-writable ``/tmp``, where a predictable name is an
    invitation: another user can pre-create it, or plant a symlink pointing somewhere
    that matters, and wait for a build to write through it. Refusing anything that is not
    a real directory owned by the invoking user closes that off. Ownership is checked
    with :func:`os.lstat`, which reports the link itself rather than its target.
    """
    try:
        info = os.lstat(directory)
    except FileNotFoundError:
        _create_dir(directory)
        return
    except OSError as exc:
        raise TranscriptError(
            f"Cannot use {directory} for build transcripts ({exc.strerror})."
        ) from exc

    if stat.S_ISLNK(info.st_mode):
        raise TranscriptError(
            f"{directory} is a symlink, not a directory — refusing to write build "
            f"transcripts through it. Remove it, or set `transcript_dir` in build config."
        )
    if not stat.S_ISDIR(info.st_mode):
        raise TranscriptError(
            f"{directory} exists but is not a directory. Remove it, or set "
            f"`transcript_dir` in build config."
        )
    if _uid() is not None and info.st_uid != _uid():
        raise TranscriptError(
            f"{directory} is owned by another user (uid {info.st_uid}) — refusing to "
            f"write build transcripts into it. Set `transcript_dir` in build config."
        )


def _create_dir(directory: Path) -> None:
    """Create *directory* owner-only, tolerating a concurrent creator."""
    try:
        os.makedirs(directory, mode=0o700, exist_ok=True)
        # makedirs applies the umask, which on an unusual one could widen or narrow the
        # mode; set it explicitly on the directory we just made.
        os.chmod(directory, 0o700)
    except OSError as exc:
        raise TranscriptError(
            f"Cannot create {directory} for build transcripts ({exc.strerror}). "
            f"Set `transcript_dir` in build config, or pass --no-transcript."
        ) from exc


def _link(link: Path, target: Path) -> None:
    """Point *link* at *target*, atomically, without disturbing a build on failure.

    The link target is the bare filename so the pair survives the directory being moved.
    A filesystem that cannot do symlinks costs only the convenience handle — the real
    path is printed twice regardless — so this degrades quietly rather than failing a
    build that has already succeeded.
    """
    staging = link.with_name(f"{link.name}.new")
    try:
        staging.unlink(missing_ok=True)
        os.symlink(target.name, staging)
        os.replace(staging, link)
    except OSError:
        pass


def _uid() -> int | None:
    """The invoking user's id, or None where the platform has no such concept."""
    getuid = getattr(os, "getuid", None)
    return getuid() if getuid is not None else None
