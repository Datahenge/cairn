"""Tests for build-engine detection — docker or podman (`ADR-027`, BR-CFG-008)."""

from __future__ import annotations

import subprocess
import types

import pytest

from cairn import engine
from cairn.errors import BuildEngineError


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _responses(mapping: dict[tuple[str, ...], subprocess.CompletedProcess]):
    """Build a fake ``_run`` that answers by command prefix, else reports "not found"."""

    def _run(command: list[str]):
        for prefix, response in mapping.items():
            if tuple(command[: len(prefix)]) == prefix:
                return response
        raise BuildEngineError(f"`{command[0]}` not found on PATH.")

    return _run


DOCKER_OK = {("docker", "version"): _completed(0, stdout="27.3.1\n")}
PODMAN_OK = {
    ("podman", "--version"): _completed(0, stdout="podman version 5.4.2\n"),
    ("podman", "info"): _completed(0, stdout="host:\n"),
}


# --- detection order --------------------------------------------------------


def test_prefers_docker_when_both_present(monkeypatch):
    """ADR-027: docker wins when no preference is configured."""
    monkeypatch.setattr(engine, "_run", _responses({**DOCKER_OK, **PODMAN_OK}))

    selected = engine.detect()

    assert selected.name == engine.DOCKER
    assert selected.needs_buildx


def test_falls_back_to_podman_when_docker_absent(monkeypatch):
    """ADR-027: a podman-only machine builds without Docker installed."""
    monkeypatch.setattr(engine, "_run", _responses(PODMAN_OK))

    selected = engine.detect()

    assert selected.name == engine.PODMAN
    assert selected.version == "5.4.2"
    assert not selected.needs_buildx  # podman builds with buildah in-process


def test_no_engine_at_all_names_both_options(monkeypatch):
    """BR-CLI-015: the error names the fix rather than only the symptom."""
    monkeypatch.setattr(engine, "_run", _responses({}))

    with pytest.raises(BuildEngineError, match="Docker Engine v23\\+ or podman v4\\+"):
        engine.detect()


# --- explicit preference (BR-CFG-008) ---------------------------------------


def test_explicit_preference_is_honoured(monkeypatch):
    """BR-CFG-008: `engine = "podman"` selects podman even when docker is present."""
    monkeypatch.setattr(engine, "_run", _responses({**DOCKER_OK, **PODMAN_OK}))

    assert engine.detect(engine.PODMAN).name == engine.PODMAN


def test_explicit_preference_does_not_silently_fall_back(monkeypatch):
    """An explicit choice must fail loudly, not quietly build with the other engine."""
    monkeypatch.setattr(engine, "_run", _responses(DOCKER_OK))

    with pytest.raises(BuildEngineError, match="'podman' is unusable"):
        engine.detect(engine.PODMAN)


def test_unknown_preference_rejected(monkeypatch):
    with pytest.raises(BuildEngineError, match="Unknown build engine 'buildah'"):
        engine.detect("buildah")


# --- version floors (ADR-027) -----------------------------------------------


def test_docker_below_floor_rejected(monkeypatch):
    """ADR-027: Docker below v23 predates BuildKit-by-default."""
    monkeypatch.setattr(
        engine, "_run", _responses({("docker", "version"): _completed(0, stdout="20.10.24\n")})
    )

    with pytest.raises(BuildEngineError, match=r"requires docker v23\+"):
        engine.check(engine.DOCKER)


def test_podman_below_floor_rejected(monkeypatch):
    """ADR-027: podman below v4 predates documented `--mount=type=secret` support."""
    monkeypatch.setattr(
        engine,
        "_run",
        _responses({("podman", "--version"): _completed(0, stdout="podman version 3.4.4\n")}),
    )

    with pytest.raises(BuildEngineError, match=r"requires podman v4\+"):
        engine.check(engine.PODMAN)


# --- engine-specific probe semantics ----------------------------------------


def test_docker_daemon_down_is_distinct_from_missing(monkeypatch):
    """A non-zero `docker version` means the daemon is down, not that docker is absent."""
    monkeypatch.setattr(
        engine,
        "_run",
        _responses({("docker", "version"): _completed(1, stderr="Cannot connect to the daemon")}),
    )

    with pytest.raises(BuildEngineError, match="not reachable"):
        engine.check(engine.DOCKER)


def test_podman_installed_but_unusable_is_caught(monkeypatch):
    """Rootless podman that cannot claim its subuid range answers --version but fails info.

    This is exactly the broken-user-namespace case; reporting the version alone would
    pass the check and then fail at build time.
    """
    monkeypatch.setattr(
        engine,
        "_run",
        _responses(
            {
                ("podman", "--version"): _completed(0, stdout="podman version 5.4.2\n"),
                ("podman", "info"): _completed(125, stderr="permission denied"),
            }
        ),
    )

    with pytest.raises(BuildEngineError, match="installed but unusable"):
        engine.check(engine.PODMAN)


def test_buildx_missing_names_the_package(monkeypatch):
    monkeypatch.setattr(
        engine, "_run", _responses({("docker", "buildx"): _completed(1, stderr="unknown command")})
    )

    with pytest.raises(BuildEngineError, match="docker-buildx-plugin"):
        engine.buildx_version()


def test_version_parsing():
    assert engine._major("27.3.1") == 27
    assert engine._major("v23.0.1") == 23
    assert engine._major("garbage") is None
