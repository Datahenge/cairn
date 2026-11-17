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
        "registry_host": "ghcr.io",
        "image": "datahenge/erpnext-btu-v16",
        "tag": "production",
        "site": "erp.example.com",
    }
    values.update(overrides)
    return descriptor.Descriptor(**values)


class Commands:
    """Records every command, and answers each from a scripted list of exit codes."""

    def __init__(self, *, fail_on=None, captures=None):
        self.run: list[list[str]] = []
        #: (command, env_overrides) for every call, so a test can assert on the environment a
        #: command was given and not merely on the command itself (BR-DEPLOY-003b).
        self.calls: list[tuple[list[str], dict | None]] = []
        self.fail_on = fail_on
        self.captures = captures or {}

    def try_(self, command, timeout, *, env_overrides=None):
        self.run.append(command)
        self.calls.append((command, env_overrides))
        self.env = env_overrides
        if self.fail_on and self.fail_on in " ".join(command):
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    def capture(self, command, *, env_overrides=None):
        self.run.append(command)
        self.calls.append((command, env_overrides))
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


@pytest.mark.parametrize(
    ("running_digest", "stack_up", "expected_converged"),
    [
        (DESIRED, True, True),
        # a host that pulled an image and then died is not converged, and reporting it as
        # success is how a timer comes to hide an outage.
        (DESIRED, False, False),
        (OTHER, True, False),
    ],
    ids=["matching-digest-running", "matching-digest-stopped", "different-digest"],
)
def test_is_converged(running_digest, stack_up, expected_converged):
    state = reconcile.State(
        desired_digest=DESIRED, running_digest=running_digest, stack_up=stack_up
    )

    assert state.is_converged is expected_converged
    assert state.is_first_deploy is False  # a running_digest is present in every case here


def test_no_local_image_is_a_first_deploy():
    state = reconcile.State(desired_digest=DESIRED, running_digest=None, stack_up=False)

    assert state.is_first_deploy is True


def test_a_no_change_run_does_nothing_at_all(monkeypatch, commands):
    """BR-DEPLOY-001: the common case under a timer. It must not pull, recreate, or migrate —
    it MAY still probe the running container to refresh the adopt-owned marker
    (`BR-DEPLOY-023`, `ADR-072`), which is exactly what closes the rollout gap for a host
    already running an image pulled before that feature existed."""
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: DESIRED)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: True)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)

    outcome = reconcile.run(_descriptor())

    assert outcome.converged is True
    assert outcome.changed is False
    assert not any("pull" in command for command in commands.run)
    assert not any("up" in command for command in commands.run)
    assert not any("migrate" in command for command in commands.run)


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


#: A minimal, valid capture set: a running container whose own image carries DESIRED.
_RUNNING_DESIRED = {
    "ps -q": "abc123containerid\n",
    "docker inspect": "sha256:" + "f" * 64 + "\n",
    "image inspect": json.dumps(["ghcr.io/datahenge/erpnext-btu-v16@" + DESIRED]),
}


def test_the_running_digest_comes_from_the_containers_own_image(commands):
    """BR-DEPLOY-003b: convergence is read off the *running container's* image, not merely
    whether a matching image exists somewhere in the local store — a compose file that
    hardcodes `image:` per service never reacts to CUSTOM_IMAGE/CUSTOM_TAG, so a stale
    container can keep running right next to a freshly pulled, unused image."""
    commands.captures = dict(_RUNNING_DESIRED)

    assert reconcile.running_digest(_descriptor()) == DESIRED


def test_no_running_container_has_no_running_digest(commands):
    """The normal state before a first deploy — nothing to compare against."""
    commands.captures = {}

    assert reconcile.running_digest(_descriptor()) is None


def test_a_container_whose_image_id_cannot_be_read_has_no_running_digest(commands):
    commands.captures = {"ps -q": "abc123containerid\n"}

    assert reconcile.running_digest(_descriptor()) is None


def test_a_digest_for_another_repository_is_not_ours(commands):
    """A local image may carry digests from several repositories; only this one's counts."""
    commands.captures = {
        **_RUNNING_DESIRED,
        "image inspect": json.dumps(["ghcr.io/someone/else@" + DESIRED]),
    }

    assert reconcile.running_digest(_descriptor()) is None


def test_a_stale_container_reports_its_own_older_digest_not_the_local_stores(commands):
    """The exact bug found live 2026-08-05: the desired image can be pulled and sitting in
    the local store while an untouched container keeps running an older one. The digest
    reported must be the container's, not whatever else the store happens to hold."""
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "e" * 64 + "\n",
        "image inspect": json.dumps(["ghcr.io/datahenge/erpnext-btu-v16@" + OTHER]),
    }

    assert reconcile.running_digest(_descriptor()) == OTHER


# --- the adopt-owned marker (BR-DEPLOY-023, ADR-072) ------------------------


def test_running_image_id_reads_off_the_containers_own_image(commands):
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
    }

    assert reconcile.running_image_id(_descriptor()) == "sha256:" + "f" * 64


def test_mark_owned_tags_the_running_image(commands):
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
    }

    reconcile.mark_owned(_descriptor())

    tags = [command for command in commands.run if command[:2] == ["docker", "tag"]]
    assert tags == [
        [
            "docker",
            "tag",
            "sha256:" + "f" * 64,
            "ghcr.io/datahenge/erpnext-btu-v16:cairn-adopt-owned",
        ]
    ]


def test_mark_owned_does_nothing_when_nothing_is_running(commands):
    commands.captures = {}

    reconcile.mark_owned(_descriptor())

    assert not any(command[:2] == ["docker", "tag"] for command in commands.run)


def test_mark_owned_failure_is_silent(commands):
    """Best-effort: a tagging hiccup must not be mistaken for a convergence failure."""
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
    }
    commands.fail_on = "docker tag"

    reconcile.mark_owned(_descriptor())  # must not raise


def test_a_converged_no_op_pass_still_refreshes_the_marker(monkeypatch, commands):
    """The whole point of refreshing on every pass, not only on a pull: a host already
    running an image pulled before this feature existed picks up the marker on its very
    next reconcile, converged or not — no manual step."""
    monkeypatch.setattr(registry, "digest_of", lambda ref: DESIRED)
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: DESIRED)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: True)
    monkeypatch.setattr(reconcile, "_single_flight", _no_lock)
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
    }

    reconcile.run(_descriptor())

    assert any(command[:2] == ["docker", "tag"] for command in commands.run)


def test_a_real_converge_also_refreshes_the_marker(converging, commands):
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
    }

    reconcile.run(_descriptor())

    assert any(command[:2] == ["docker", "tag"] for command in commands.run)


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


def test_a_non_default_compose_file_name_is_used():
    """A hand-built deployment `examine` adopted may not call its base file `compose.yaml` —
    `reconcile` must address the same file `examine` actually found, not assume the name."""
    command = reconcile._compose_command(
        _descriptor(
            compose=descriptor.Compose(
                directory=reconcile.Path("/opt/vps-setup/gitops"), file="erpnext.yaml"
            )
        ),
        ["up", "-d"],
    )

    files = [command[i + 1] for i, part in enumerate(command) if part == "--file"]
    assert files == ["/opt/vps-setup/gitops/erpnext.yaml"]


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


def test_every_compose_probe_carries_the_image_variables(commands):
    """BR-DEPLOY-003b, BR-DEPLOY-017: a compose probe without the image variables reads blind.

    The compose file interpolates `${CUSTOM_IMAGE}`/`${CUSTOM_TAG}`, and `BR-VEND-006` requires
    it to *fail* rather than substitute a default when they are absent. So a read-only probe
    that omits them exits non-zero, which is indistinguishable from a genuinely stopped stack:
    `stack_is_up` reads false forever and health times out, while `running_digest` reads None
    so the host never converges and re-runs `bench migrate` on every single pass.

    Found live on a client VPS 2026-08-19, hours after `BR-VEND-006` removed the `:-` default
    that had been silently absorbing the omission. Asserts over *every* compose invocation
    rather than the three that were wrong, because the next probe added would repeat the
    mistake — the defect is the class, not the instances.
    """
    target = _descriptor(health=descriptor.Health(url="https://erp.example.com"))
    commands.captures = {
        "ps -q": "abc123containerid\n",
        "docker inspect": "sha256:" + "f" * 64 + "\n",
        "ps": json.dumps({"Service": "backend", "State": "running"}),
    }

    reconcile.running_digest(target)
    reconcile.stack_is_up(target)
    reconcile._site_answers(target)

    blind = [
        " ".join(command)
        for command, env in commands.calls
        if command[:2] == ["docker", "compose"] and not (env or {}).get("CUSTOM_IMAGE")
    ]
    assert blind == [], (
        "these `docker compose` calls were given no CUSTOM_IMAGE, so the compose file cannot "
        f"resolve its image reference and the probe fails rather than reports: {blind}"
    )


# --- hot swap (BR-DEPLOY-025, ADR-081) --------------------------------------

SERVICES = {
    "configurator": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "backend": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "websocket": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "frontend": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "queue-short": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "scheduler": {"image": "ghcr.io/datahenge/erpnext-btu-v16:production"},
    "db": {"image": "mariadb:11.8"},
}


class Stack:
    """A fake compose project: one container per web service until a pass scales it up."""

    def __init__(self, *, services=None, new_apps="frappe\nerpnext\n", ready=True):
        self.run: list[list[str]] = []
        self.services = SERVICES if services is None else services
        self.containers = {name: [f"old-{name}"] for name in ("backend", "websocket", "frontend")}
        self.new_apps = new_apps
        self.ready = ready

    def try_(self, command, timeout, *, env_overrides=None):
        self.run.append(command)
        if "--scale" in command:
            service = command[-1]
            self.containers[service].append(f"new-{service}")
        if command[:2] == ["docker", "stop"]:
            cid = command[-1]
            for ids in self.containers.values():
                if cid in ids:
                    ids.remove(cid)
        if "curl" in command and command[:2] == ["docker", "exec"] and not self.ready:
            return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    def capture(self, command, *, env_overrides=None):
        self.run.append(command)
        text = " ".join(command)
        if "config --format json" in text:
            return json.dumps({"services": self.services})
        if "ps -q" in text:
            return "\n".join(self.containers.get(command[-1], []))
        if "--entrypoint ls" in text:
            return "erpnext\nfrappe\n" if "old-image" in text else self.new_apps
        if "docker inspect" in text:
            return "true\n"
        return None


@pytest.fixture
def stack(monkeypatch, converging):
    fake = Stack()
    monkeypatch.setattr(reconcile, "_try", fake.try_)
    monkeypatch.setattr(reconcile, "_capture", fake.capture)
    monkeypatch.setattr(reconcile.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(reconcile, "running_image_id", lambda desc: "old-image")
    return fake


def _hot_swap_descriptor(**overrides):
    return _descriptor(
        deploy=descriptor.Deploy(strategy="hot-swap"),
        health=descriptor.Health(url="http://localhost:8000/api/method/ping"),
        **overrides,
    )


def _index(steps, fragment):
    return next(i for i, step in enumerate(steps) if fragment in step)


def test_hot_swap_migrates_first_then_replaces_the_web_tier_in_order(stack):
    """BR-DEPLOY-025: migration runs before any new container takes traffic, the frontend
    starts after the new backend exists, the old frontend retires before the old backend, and
    nginx reloads as soon as the old backend is gone."""
    reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    order = [
        _index(steps, "docker pull"),
        _index(steps, "run --rm --no-deps -T configurator"),
        _index(steps, "run --rm --no-deps -T backend bench --site erp.example.com migrate"),
        _index(steps, "--scale backend=2 backend"),
        _index(steps, "--scale websocket=2 websocket"),
        _index(steps, "--scale frontend=2 frontend"),
        _index(steps, "docker stop -t 30 old-frontend"),
        _index(steps, "docker stop -t 30 old-backend"),
        _index(steps, "docker exec new-frontend nginx -s reload"),
        _index(steps, "docker stop -t 30 old-websocket"),
        _index(steps, "up -d --no-deps queue-short scheduler"),
    ]
    assert order == sorted(order)
    assert not any("exec -T backend bench" in step and "migrate" in step for step in steps)


def test_hot_swap_checks_the_new_backend_itself(stack):
    """During a swap `backend` resolves to both containers; only the new one's answer counts."""
    reconcile.run(_hot_swap_descriptor())

    assert [
        "docker",
        "exec",
        "new-backend",
        "curl",
        "-fsS",
        "-o",
        "/dev/null",
        "-H",
        f"X-Frappe-Site-Name: {_hot_swap_descriptor().site}",
        "http://localhost:8000/api/method/ping",
    ] in stack.run


@pytest.mark.parametrize(
    "service",
    [
        {"image": "x", "ports": [{"published": "8080", "target": 8080}]},
        {"image": "x", "container_name": "frontend"},
    ],
    ids=["published-port", "container-name"],
)
def test_an_unscalable_web_service_is_refused_before_anything_changes(stack, service):
    services = {**SERVICES, "frontend": service}
    stack.services = services

    with pytest.raises(ReconcileError, match="cannot start beside the first"):
        reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert not any("migrate" in step or "--scale" in step for step in steps)


def test_a_changed_app_list_recreates_in_place_instead(stack):
    """BR-DEPLOY-003a: apps.txt is shared, so old and new code with different apps cannot run
    side by side."""
    stack.new_apps = "frappe\nerpnext\nhrms\n"

    reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert any("up -d --remove-orphans" in step for step in steps)
    assert not any("--scale" in step for step in steps)


@pytest.mark.parametrize(
    ("running_digest", "stack_up"),
    [(None, False), (OTHER, False)],
    ids=["first-deploy", "stack-down"],
)
def test_nothing_running_means_recreate(monkeypatch, stack, running_digest, stack_up):
    monkeypatch.setattr(reconcile, "running_digest", lambda desc: running_digest)
    monkeypatch.setattr(reconcile, "stack_is_up", lambda desc: stack_up)
    monkeypatch.setattr(reconcile, "await_health", lambda desc, report: None)

    reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert any("up -d --remove-orphans" in step for step in steps)
    assert not any("config --format json" in step for step in steps)


def test_an_unready_candidate_is_removed_and_the_old_stack_keeps_serving(stack, monkeypatch):
    """BR-DEPLOY-018: halt and report. The old containers never stopped."""
    stack.ready = False
    monkeypatch.setattr(reconcile.time, "monotonic", iter(range(0, 10_000, 100)).__next__)

    with pytest.raises(ReconcileError, match="still serving the old code"):
        reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert "docker rm -f new-backend" in steps
    assert not any(step.startswith("docker stop") for step in steps)


def test_the_recreate_strategy_is_unchanged(stack):
    reconcile.run(_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert any("up -d --remove-orphans" in step for step in steps)
    assert not any("config --format json" in step for step in steps)


def test_a_dry_run_describes_the_hot_swap(monkeypatch, converging):
    outcome = reconcile.run(_hot_swap_descriptor(), dry_run=True)

    assert "beside the old ones" in outcome.detail


def test_the_health_probe_names_the_site(monkeypatch, commands):
    """BR-DEPLOY-017: Frappe has no default site, so a probe that does not name the site
    answers 404 on a healthy stack."""
    monkeypatch.setattr(
        reconcile, "_compose_command", lambda desc, args: ["docker", "compose", *args]
    )
    desc = _descriptor(health=descriptor.Health(url="http://localhost:8000/api/method/ping"))

    reconcile._site_answers(desc)

    assert any("X-Frappe-Site-Name: erp.example.com" in command for command in commands.run)


def test_hot_swap_quits_the_old_nginx_gracefully_before_stopping_it(stack):
    """BR-DEPLOY-025: `docker stop` alone kills nginx mid-request when bash is PID 1."""
    reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    assert _index(steps, "docker exec old-frontend nginx -s quit") < _index(
        steps, "docker stop -t 30 old-frontend"
    )


def test_hot_swap_drops_the_asset_map_once_the_old_backend_is_gone(stack):
    """BR-DEPLOY-003: before that, the old backend could write its own bundle names back."""
    reconcile.run(_hot_swap_descriptor())

    steps = [" ".join(command) for command in stack.run]
    drop = _index(steps, "frappe.client_cache.delete_value")
    assert (
        _index(steps, "docker rm old-backend")
        < drop
        < _index(steps, "docker stop -t 30 old-websocket")
    )


def test_recreate_drops_the_asset_map_after_migrating(converging, commands):
    """BR-DEPLOY-003: a recreate keeps the Redis volume too, so it needs the same drop."""
    reconcile.run(_descriptor())

    steps = [" ".join(command) for command in commands.run]
    assert _index(steps, "migrate") < _index(steps, "frappe.client_cache.delete_value")
