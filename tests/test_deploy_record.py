"""Tests for the deploy record's summary and line (BR-DEPLOY-026).

The probe's one real request goes through `deploy_record._probe_once`, which every test here
replaces, so nothing leaves the machine.
"""

from __future__ import annotations

import json
import time

from cairn import deploy_record
from cairn.deploy_record import Record, Sample, summarize


def _samples(pattern, *, every=0.5, seconds=0.1):
    """One sample per character: '.' answered, 'x' failed, *every* seconds apart."""
    return [
        Sample(started=i * every, ok=mark == ".", seconds=seconds) for i, mark in enumerate(pattern)
    ]


def test_an_undisturbed_pass_has_no_outage():
    summary = summarize(_samples("....."))

    assert summary["requests"] == 5
    assert summary["failed"] == 0
    assert summary["longest_outage_s"] == 0
    assert summary["p50_ms"] == summary["p95_ms"] == summary["max_ms"] == 100


def test_the_longest_outage_runs_to_the_next_answer():
    """BR-DEPLOY-026: from the first failure in a run to the next answered request."""
    summary = summarize(_samples("..xx...xxxx.."))

    assert summary["failed"] == 6
    assert summary["longest_outage_s"] == 2.0


def test_an_outage_still_running_at_the_end_is_counted():
    summary = summarize(_samples("..xxx", seconds=0.2))

    assert summary["longest_outage_s"] == 1.2


def test_response_times_count_answered_requests_only():
    samples = [
        Sample(started=0, ok=True, seconds=0.1),
        Sample(started=1, ok=False, seconds=10.0),
        Sample(started=11, ok=True, seconds=0.3),
    ]

    summary = summarize(samples)

    assert summary["max_ms"] == 300
    assert summary["p95_ms"] == 300


def test_nothing_probed_summarizes_to_zeroes():
    assert summarize([]) == {
        "requests": 0,
        "failed": 0,
        "p50_ms": 0,
        "p95_ms": 0,
        "max_ms": 0,
        "longest_outage_s": 0,
    }


def test_the_record_is_one_line_of_json_behind_its_marker():
    record = Record(environment="staging", replaced="sha256:old", enabled="sha256:new")
    record.path = "hot-swap"
    record.migrated = True
    record.tables = ["tabItem"]
    record.steps = {"migrate": 41.2}

    line = record.line()

    assert "\n" not in line
    assert line.startswith("deploy record {")
    payload = json.loads(line.removeprefix("deploy record "))
    assert payload["migrate"] == {
        "ran": True,
        "seconds": 41.2,
        "tables_written": 1,
        "tables": ["tabItem"],
    }
    assert payload["from"] == "sha256:old"


def test_a_long_table_list_is_cut_but_counted():
    record = Record(migrated=True, tables=[f"tab{i:03}" for i in range(80)])

    migrate = record.as_dict()["migrate"]

    assert migrate["tables_written"] == 80
    assert len(migrate["tables"]) == deploy_record.MAX_TABLES


def test_a_failure_keeps_only_its_first_line():
    record = Record()

    record.failed(RuntimeError("bench migrate failed\nTraceback (most recent call last):"))

    assert record.outcome == "failed"
    assert record.error == "bench migrate failed"


def test_steps_add_up_under_one_name():
    record = Record()

    with record.step("retire"):
        pass
    with record.step("retire"):
        pass

    assert list(record.steps) == ["retire"]


def test_touched_tables_must_be_a_list_of_names():
    assert deploy_record.parse_tables('["tabB", "tabA"]') == ["tabA", "tabB"]
    assert deploy_record.parse_tables("not json") is None
    assert deploy_record.parse_tables('{"tabA": 1}') is None
    assert deploy_record.parse_tables(None) is None


def test_frappes_list_is_kept_as_written_because_a_fragment_can_be_a_real_table():
    """Seen on a local ERPNext 16 site: `tabHas` beside `tabHas Role`, but `tabWorkspace` is
    both a real table and the first word of `tabWorkspace Chart`."""
    text = '["tabWorkspace Chart", "tabWorkspace", "tabHas", "tabHas Role", "tabHas"]'

    assert deploy_record.parse_tables(text) == [
        "tabHas",
        "tabHas Role",
        "tabWorkspace",
        "tabWorkspace Chart",
    ]


def test_the_probe_samples_until_stopped(monkeypatch):
    answers = iter([True, False, True] + [True] * 1000)
    monkeypatch.setattr(deploy_record, "_probe_once", lambda url: next(answers))

    probe = deploy_record.Probe("https://erp.example.com/api/method/ping", 100).start()
    time.sleep(0.35)
    summary = probe.stop()

    assert summary["requests"] >= 3
    assert summary["failed"] == 1


def test_a_refused_connection_is_a_failed_probe_not_an_error():
    assert deploy_record._probe_once("http://127.0.0.1:9/") is False
