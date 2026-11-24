"""Shared test set-up.

Every test gets its own back-off file (BR-DEPLOY-027). A test that fails a converge would
otherwise write `/run/cairn/failed-deploy` on the machine running the suite, and the next test
to converge that digest would find itself waiting.
"""

from __future__ import annotations

import pytest

from cairn import backoff


@pytest.fixture(autouse=True)
def _isolated_backoff(monkeypatch, tmp_path):
    monkeypatch.setattr(backoff, "STATE_PATH", tmp_path / "failed-deploy")
