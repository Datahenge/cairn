"""Start, end, duration, and per-phase elapsed times (BR-CLI-017).

A build that reports nothing about how long it took leaves the operator unable to answer
the first question they will ask — "was that normal?" — and unable to decide whether the
build is worth optimising at all. Per-phase numbers matter more than the total: a total
cannot distinguish a slow network from a slow asset build.

Two clocks are used on purpose. Durations come from :func:`time.monotonic`, which cannot
run backwards when NTP steps the system clock mid-build; wall-clock start and end times
come from :func:`datetime.now` because "started 14:02:11" is what a human wants to read.
Using the wall clock for both would let a clock adjustment produce a negative duration.

Durations are deliberately *not* recorded in provenance labels (`BR-CLI-017`): elapsed
time is a property of a build **run** — cache state, machine, network — not of the
image's inputs, and inputs are what `BR-BUILD-013` makes guarantees about.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime

#: Wall-clock format for the start/end stamps; local time, since a human reads them.
CLOCK_FORMAT = "%Y-%m-%d %H:%M:%S %Z"


@dataclass(frozen=True)
class Phase:
    """One named span of a command's run."""

    name: str
    seconds: float


@dataclass
class Stopwatch:
    """Records when a command started, and how long each of its phases took."""

    started_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    phases: list[Phase] = field(default_factory=list)
    _origin: float = field(default_factory=lambda: time.monotonic())

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        """Time the enclosed block and record it as *name*.

        A phase that raises is still recorded, so a failure report can show how far the
        command got and how long it spent getting there.
        """
        mark = time.monotonic()
        try:
            yield
        finally:
            self.phases.append(Phase(name=name, seconds=time.monotonic() - mark))

    @property
    def elapsed(self) -> float:
        """Seconds since the stopwatch was created."""
        return time.monotonic() - self._origin

    def summary(self) -> list[str]:
        """Return the report lines: each phase, then start/end/total."""
        finished_at = datetime.now().astimezone()
        width = max((len(phase.name) for phase in self.phases), default=0)
        return [
            *(
                f"  {phase.name:<{width}}  {format_duration(phase.seconds)}"
                for phase in self.phases
            ),
            f"  started  {self.started_at.strftime(CLOCK_FORMAT)}",
            f"  finished {finished_at.strftime(CLOCK_FORMAT)}",
            f"  total    {format_duration(self.elapsed)}",
        ]


def format_duration(seconds: float) -> str:
    """Render *seconds* the way a person reads a stopwatch.

    Sub-minute durations keep a decimal, because the difference between 0.4s and 6.1s is
    interesting at that scale; beyond a minute it is noise.
    """
    if seconds < 60:
        return f"{seconds:.1f}s"

    whole = int(seconds)
    hours, remainder = divmod(whole, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    return f"{minutes}m {secs:02d}s"
