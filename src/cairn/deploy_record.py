"""The deploy record: one line per converging pass (`BR-DEPLOY-026`, `ADR-082`).

A pass that starts to converge ends by printing ``deploy record {...}`` to stdout: which path
it took, whether ``bench migrate`` ran and what it wrote, how long each step took, and, with a
probe URL set, what that URL answered while the pass ran. Stdout only (`BR-DEPLOY-019`):
journald keeps it.

Everything here observes. Nothing in this module may change what a pass does, and nothing in
it may raise into one: a probe that cannot run, or a value that cannot be read, is left out.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

#: The prefix that marks the line, so `grep 'deploy record'` finds one row per deploy.
MARKER = "deploy record"

#: A probe request that has not answered by then counts as a failure.
PROBE_REQUEST_TIMEOUT_SECONDS = 10.0

#: The most tables a record lists. A large migrate can write hundreds; the count is kept.
MAX_TABLES = 50


@dataclass(frozen=True)
class Sample:
    """One probe request: when it started, whether it answered, and how long it took."""

    started: float
    ok: bool
    seconds: float


def summarize(samples: list[Sample]) -> dict[str, float | int]:
    """Reduce probe samples to the figures the record prints (`BR-DEPLOY-026`).

    Response times are over answered requests only: a timeout's duration is the timeout, not
    the site. ``longest_outage_s`` runs from the start of the first failure in a run to the
    start of the next answered request, or to the end of the last failure if the run never
    ended.
    """
    answered = sorted(round(s.seconds * 1000) for s in samples if s.ok)
    outage = 0.0
    run_started: float | None = None
    for sample in samples:
        if not sample.ok:
            if run_started is None:
                run_started = sample.started
            continue
        if run_started is not None:
            outage = max(outage, sample.started - run_started)
            run_started = None
    if run_started is not None:
        last = samples[-1]
        outage = max(outage, last.started + last.seconds - run_started)

    return {
        "requests": len(samples),
        "failed": len(samples) - len(answered),
        "p50_ms": _percentile(answered, 50),
        "p95_ms": _percentile(answered, 95),
        "max_ms": answered[-1] if answered else 0,
        "longest_outage_s": round(outage, 1),
    }


def _percentile(ordered: list[int], percent: int) -> int:
    """Nearest-rank percentile of an ascending list, 0 when it is empty."""
    if not ordered:
        return 0
    rank = max(1, -(-percent * len(ordered) // 100))
    return ordered[rank - 1]


def _probe_once(url: str) -> bool:
    """Request *url* once; True for a 2xx or 3xx answer.

    The one seam tests replace, so a probe thread never runs a real request under test.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "cairn-deploy-probe"})
    try:
        with urllib.request.urlopen(request, timeout=PROBE_REQUEST_TIMEOUT_SECONDS) as answer:
            return 200 <= answer.status < 400
    except (urllib.error.URLError, OSError, ValueError):
        return False


class Probe:
    """Request a URL at a fixed interval on a background thread until stopped.

    One request at a time: a slow answer delays the next request rather than piling up more
    of them against a site that is already struggling.
    """

    def __init__(self, url: str, interval_ms: int) -> None:
        self.url = url
        self.interval = interval_ms / 1000
        self.samples: list[Sample] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="cairn-deploy-probe", daemon=True)

    def start(self) -> Probe:
        self._thread.start()
        return self

    def stop(self) -> dict[str, float | int]:
        self._stop.set()
        self._thread.join(timeout=PROBE_REQUEST_TIMEOUT_SECONDS + 1)
        return summarize(list(self.samples))

    def _loop(self) -> None:
        while not self._stop.is_set():
            started = time.perf_counter()
            ok = _probe_once(self.url)
            seconds = time.perf_counter() - started
            self.samples.append(Sample(started=started, ok=ok, seconds=seconds))
            self._stop.wait(max(0.0, self.interval - seconds))


@dataclass
class Record:
    """What one converging pass did, filled in as it goes (`BR-DEPLOY-026`)."""

    environment: str = ""
    replaced: str | None = None
    enabled: str = ""
    outcome: str = "ok"
    error: str | None = None
    path: str | None = None
    path_note: str | None = None
    migrated: bool | None = None
    tables: list[str] | None = None
    content_files: int | None = None
    content_failed: bool = False
    steps: dict[str, float] = field(default_factory=dict)
    probe: dict[str, float | int] | None = None

    @contextmanager
    def step(self, name: str) -> Iterator[None]:
        """Time the enclosed block as step *name*, adding to any earlier time under it.

        ``perf_counter`` rather than ``monotonic``: tests replace ``time.monotonic`` to run
        reconcile's waits instantly, and a step must measure the wall clock all the same.
        """
        started = time.perf_counter()
        try:
            yield
        finally:
            spent = time.perf_counter() - started
            self.steps[name] = round(self.steps.get(name, 0.0) + spent, 1)

    def failed(self, error: BaseException | str) -> None:
        self.outcome = "failed"
        text = str(error).strip()
        self.error = text.splitlines()[0] if text else type(error).__name__

    def as_dict(self) -> dict[str, object]:
        migrate: dict[str, object] = {"ran": self.migrated}
        if self.content_files is not None:
            migrate["content_files"] = self.content_files
        if self.content_failed:
            migrate["content_failed"] = True
        if self.migrated:
            migrate["seconds"] = self.steps.get("migrate")
            if self.tables is not None:
                migrate["tables_written"] = len(self.tables)
                migrate["tables"] = self.tables[:MAX_TABLES]
        payload: dict[str, object] = {
            "environment": self.environment,
            "from": self.replaced,
            "to": self.enabled,
            "outcome": self.outcome,
        }
        if self.error:
            payload["error"] = self.error
        payload["path"] = self.path
        if self.path_note:
            payload["path_note"] = self.path_note
        payload["migrate"] = migrate
        payload["steps"] = self.steps
        if self.probe is not None:
            payload["probe"] = self.probe
        return payload

    def line(self) -> str:
        return f"{MARKER} {json.dumps(self.as_dict(), separators=(',', ':'))}"


def parse_tables(text: str | None) -> list[str] | None:
    """The table names in Frappe's ``touched_tables.json``, or None if it is not a list.

    Passed through as Frappe wrote it. Frappe also records the first word of a name with a
    space in it (``tabHas`` beside ``tabHas Role``), seen on a local ERPNext 16 site. Those are
    kept: ``tabWorkspace`` is both a real table and the first word of ``tabWorkspace Chart``,
    so a fragment cannot be told from a table.
    """
    try:
        value = json.loads(text or "")
    except ValueError:
        return None
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        return None
    return sorted(set(value))
