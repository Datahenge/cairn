"""Tests for the target-side convergence loop (BR-CLI-008, BR-DEPLOY-003/016/017/018).

Nothing here runs docker. The module funnels every external command through two functions
(`_try` and `_capture`), and these tests substitute those, so what is under test is the
*decision* — when to converge, in what order, and what to do when a step fails.

Boundaries: descriptor validation lives in `test_descriptor.py`, the registry read in
`test_registry.py`. This file cares only about desired-versus-actual and the sequence.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from cairn import descriptor, reconcile, registry
from cairn.errors import ReconcileError, RegistryError

DESIRED = "sha256:" + "a" * 64
OTHER = "sha256:" + "b" * 64


def _descriptor(**overrides):
    values = {
        "environment": "production",
        "image": "ghcr.io/datahenge/erpnext-btu-v16",
        "tag": "production",
        "site": "erp.example.com",
    }
    values.update(overrides)
    return descriptor.Descriptor(**values)


class Commands:
    """Records every command, and answers each from a scripted list of exit codes."""

    def __init__(self, *, fail_on=None, captures=None):
        self.run: list[list[str]] = []
        self.fail_on = fail_on
        self.captures = captures or {}

    def try_(self, command, timeout, *, env_overrides=None):
        self.run.append(command)
        self.env = env_overrides
        if self.fail_on and self.fail_on in " ".join(command):
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    def capture(self, command):
        self.run.append(command)
        for fragment, answer in self.captures.items():
            if fragment in " ".join(command):
                return answer
        return None


@pytest.fixture
def commands(monkeypatch):
    """Replace the two process seams, and neutralise the lock and the sleep."""
    recorder = Commands()
    monkeypatch.setattr(reconcile, "_try", recorder.try_)
    monkeypatch.setattr(reconcile, "_capture", recorder.capture)
    monkeypatch.setattr(reconcile.time, "sleep", lambda seconds: None)
    return recorder


# --- the convergence decision (BR-DEPLOY-001) -------------------------------


def test_a_matching_digest_with_a_running_stack_is_converged():
    state = reconcile.State(desired_digest=DESIRED, running_digest=DESIRED, stack_up=True)

    assert state.is_converged is True


def test_a_matching_digest_with_a_stopped_stack_is_not_converged():
    """A host that pulled an image and then died is not converged, and reporting it as
    success is how a timer comes to hide an outage."""
    state = reconcile.State(desired_digest=DESIRED, running_digest=DESIRED, stack_up=False)

    assert state.is_converged is False


def test_a_different_digest_is_not_converged():
    state = reconcile.State(desired_digest=DESIRED, running_digest=OTHER, stack_up=True)

    assert state.is_converged is False
    assert state.is_first_deploy is False


def test_no_local_image_is_a_first_deploy():
    state = reconcile.State(desired_digest=DESIRED, running_digest=None, stack_up=False)

    assert state.is_first_deploy is True


def test_a_no_change_run_does_nothing_at_all(monkeypatch, commands):
    """BR-DEPLOY-001: the common case under a timer. It must not pull, recreate, or migrate."""
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: DESIRED)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: True)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)

    outcome = reconcile.run(_descriptor())

    assert outcome.converged is True
    assert outcome.changed is False
    assert commands.run == []


# --- the sequence (BR-DEPLOY-003) -------------------------------------------


@pytest.fixture
def converging(monkeypatch):
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: OTHER)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: True)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)


def test_the_order_is_pull_then_up_then_migrate(converging, commands):
    """BR-DEPLOY-003 fixes this order. Migrating before the new image is running would
    migrate against the old code."""
    reconcile.run(_descriptor())

    steps = [" ".join(command) for command in commands.run]
    pull = next(i for i, step in enumerate(steps) if "docker pull" in step)
    up = next(i for i, step in enumerate(steps) if " up -d" in step)
    migrate = next(i for i, step in enumerate(steps) if "bench --site" in step)

    assert pull < up < migrate


def test_migrate_runs_on_every_image_change_including_a_rollback(converging, commands):
    """BR-DEPLOY-016: a rollback is a deploy, and the schema must be reconciled either way."""
    reconcile.run(_descriptor())

    assert any("migrate" in " ".join(command) for command in commands.run)


def test_the_site_is_named_to_bench(converging, commands):
    """A multi-site bench would otherwise migrate whichever site it picked."""
    reconcile.run(_descriptor(site="other.example.com"))

    migrate = next(c for c in commands.run if "migrate" in " ".join(c))
    assert "--site" in migrate
    assert migrate[migrate.index("--site") + 1] == "other.example.com"


def test_install_app_is_never_run(converging, commands):
    """Never, by decision (`ADR-037`): a convergence step cannot host a one-shot irreversible
    mutation, it would be a second data-plane write, and it breaks rollback — move the pointer
    back and the schema remains while the code that understands it is gone."""
    reconcile.run(_descriptor())

    assert not any("install-app" in " ".join(command) for command in commands.run)


def test_the_image_reaches_compose_as_custom_image(converging, commands):
    """These are the variables frappe_docker's compose files actually read."""
    reconcile.run(_descriptor())

    assert commands.env["CUSTOM_IMAGE"] == "ghcr.io/datahenge/erpnext-btu-v16"
    assert commands.env["CUSTOM_TAG"] == "production"


def test_compose_is_told_not_to_pull_again(converging, commands):
    """cairn already pulled deliberately and knows the digest; letting compose pull again
    reintroduces the ambiguity the explicit pull removed."""
    reconcile.run(_descriptor())

    assert commands.env["PULL_POLICY"] == "missing"


# --- failure halts and reports (BR-DEPLOY-018) ------------------------------


def test_a_failed_migrate_halts_and_does_not_roll_back(converging, commands):
    commands.fail_on = "migrate"

    with pytest.raises(ReconcileError, match="does not roll back"):
        reconcile.run(_descriptor())

    steps = " ".join(" ".join(command) for command in commands.run)
    assert "docker pull" in steps  # it got that far
    assert steps.count("up -d") == 1  # and did not try to put the old image back


def test_a_failed_pull_stops_before_touching_the_stack(converging, commands):
    commands.fail_on = "docker pull"

    with pytest.raises(ReconcileError, match="pulling the image"):
        reconcile.run(_descriptor())

    assert not any("up -d" in " ".join(command) for command in commands.run)


def test_a_missing_docker_says_what_a_target_needs(converging, monkeypatch):
    monkeypatch.setattr(reconcile, "_try", lambda *args, **kwargs: None)
    monkeypatch.setattr(reconcile, "_capture", lambda command: None)

    with pytest.raises(ReconcileError, match="needs Docker and the Compose plugin"):
        reconcile.run(_descriptor())


def test_an_unreadable_registry_names_the_environment(monkeypatch):
    def _fail(ref):
        raise RegistryError("ghcr.io/x/y:production does not exist in the registry.")

    monkeypatch.setattr(registry, "digest_of", _fail)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)

    with pytest.raises(ReconcileError, match="desired state for 'production'"):
        reconcile.inspect(_descriptor())


def test_health_failure_says_the_migration_already_ran(converging, monkeypatch, commands):
    """The operator needs to know the schema has moved — that is what makes an automatic
    rollback unsafe and a manual decision necessary."""
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: False)
    monkeypatch.setattr(reconcile.time, "monotonic", _elapsing())

    with pytest.raises(ReconcileError, match="migration has already been applied"):
        reconcile.run(_descriptor(health=descriptor.Health(timeout_seconds=1, interval_seconds=1)))


# --- dry run (BR-CLI-011) ---------------------------------------------------


def test_dry_run_changes_nothing(converging, commands):
    outcome = reconcile.run(_descriptor(), dry_run=True)

    assert outcome.changed is False
    assert not any("docker pull" in " ".join(command) for command in commands.run)


def test_dry_run_describes_a_first_deploy_differently_from_a_replacement(monkeypatch, commands):
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: False)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)

    monkeypatch.setattr(reconcile, "running_digest", lambda desc: None)
    assert "holds no image" in reconcile.run(_descriptor(), dry_run=True).detail

    monkeypatch.setattr(reconcile, "running_digest", lambda desc: OTHER)
    assert "Would replace" in reconcile.run(_descriptor(), dry_run=True).detail

    monkeypatch.setattr(reconcile, "running_digest", lambda desc: DESIRED)
    assert "already here" in reconcile.run(_descriptor(), dry_run=True).detail


def test_a_dry_run_takes_no_lock(monkeypatch):
    """The one command an operator reaches for during a deploy must not be the one command
    that refuses to answer."""
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: DESIRED)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: True)
    monkeypatch.setattr(
        reconcile, "LOCK_PATH", reconcile.Path("/proc/definitely-not-writable/lock")
    )

    assert reconcile.run(_descriptor(), dry_run=True).changed is False


def test_an_unusable_lock_refuses_to_deploy(monkeypatch, tmp_path):
    """BR-DEPLOY-016: without the lock two passes could race, so cairn declines rather than
    proceeding unprotected."""
    monkeypatch.setattr(reconcile, "LOCK_PATH", tmp_path / "nope" / "deep" / "lock")
    monkeypatch.setattr(
        reconcile.Path, "mkdir", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("denied"))
    )

    with pytest.raises(ReconcileError, match="will not deploy without it"):
        reconcile.run(_descriptor())


def test_a_second_pass_exits_rather_than_queueing(monkeypatch, tmp_path):
    """Under a timer, waiting behind a running deploy only builds a queue."""
    monkeypatch.setattr(reconcile, "LOCK_PATH", tmp_path / "lock")

    with reconcile._single_flight(dry_run=False):  # noqa: SIM117 — nesting is the point
        with pytest.raises(ReconcileError, match="already running"):
            with reconcile._single_flight(dry_run=False):
                pass


# --- reading actual state ---------------------------------------------------


def test_the_running_digest_comes_from_the_repo_digest(commands):
    """RepoDigests is the registry's own name for the content — the only thing comparable
    with what the registry reports."""
    commands.captures = {
        "image inspect": json.dumps(["ghcr.io/datahenge/erpnext-btu-v16@" + DESIRED])
    }

    assert reconcile.running_digest(_descriptor()) == DESIRED


def test_an_unpulled_image_has_no_running_digest(commands):
    commands.captures = {}

    assert reconcile.running_digest(_descriptor()) is None


def test_a_digest_for_another_repository_is_not_ours(commands):
    """A local image may carry digests from several repositories; only this one's counts."""
    commands.captures = {"image inspect": json.dumps(["ghcr.io/someone/else@" + DESIRED])}

    assert reconcile.running_digest(_descriptor()) is None


def test_the_stack_is_up_only_when_the_bench_service_runs(commands):
    """A project with only its database up is not a running deployment."""
    commands.captures = {"ps": json.dumps({"Service": "backend", "State": "running"})}
    assert reconcile.stack_is_up(_descriptor()) is True

    commands.captures = {"ps": json.dumps({"Service": "db", "State": "running"})}
    assert reconcile.stack_is_up(_descriptor()) is False

    commands.captures = {"ps": json.dumps({"Service": "backend", "State": "exited"})}
    assert reconcile.stack_is_up(_descriptor()) is False


def test_compose_json_is_read_whether_it_arrives_as_lines_or_an_array(commands):
    """Compose emits one object per line or a single array, depending on its version."""
    commands.captures = {"ps": json.dumps([{"Service": "backend", "State": "running"}])}

    assert reconcile.stack_is_up(_descriptor()) is True


# --- compose rendering (BR-DEPLOY-010) --------------------------------------


def test_overrides_are_layered_in_declared_order():
    """Compose applies later files over earlier ones, so this order carries meaning."""
    command = reconcile._compose_command(
        _descriptor(
            compose=descriptor.Compose(
                overrides=("mariadb", "redis", "https"), directory=reconcile.Path("/opt/fd")
            )
        ),
        ["up", "-d"],
    )

    files = [command[i + 1] for i, part in enumerate(command) if part == "--file"]
    assert files == [
        "/opt/fd/compose.yaml",
        "/opt/fd/overrides/compose.mariadb.yaml",
        "/opt/fd/overrides/compose.redis.yaml",
        "/opt/fd/overrides/compose.https.yaml",
    ]


def test_the_project_name_is_passed_when_set():
    command = reconcile._compose_command(
        _descriptor(compose=descriptor.Compose(project="erp")), ["ps"]
    )

    assert "--project-name" in command
    assert command[command.index("--project-name") + 1] == "erp"


def _no_lock(*, dry_run):
    from contextlib import nullcontext

    return nullcontext()


def _elapsing():
    """A monotonic clock that jumps past any deadline on its second reading."""
    readings = iter([0.0, 1_000_000.0, 2_000_000.0, 3_000_000.0])

    def _clock():
        try:
            return next(readings)
        except StopIteration:
            return 9_000_000.0

    return _clock
