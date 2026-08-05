"""Tests for `cairn-registry setup` (`BR-REG-003`, `ADR-048`).

Migrated from `test_provision.py`'s "the registry" section when the local registry split into
its own binary. This module MUST NOT import `config.py`/`environments.py`
(`BR-REG-001`) — these tests exercise that boundary indirectly by only ever importing
`registry_provision`, `registry_config`, and `setup_runner`.

Nothing here runs docker, openssl, or curl for real. `Runner.run`/`Runner.probe` are the two
seams every command goes through, so substituting them covers the whole surface.
"""

from __future__ import annotations

import ast
import inspect
import sys

import pytest

from cairn import registry_config, registry_provision, setup_runner


def _options(**overrides) -> setup_runner.SetupOptions:
    return setup_runner.SetupOptions(**overrides)


class Recorder(setup_runner.Runner):
    """A Runner that records instead of executing, answering probes from a script."""

    def __init__(self, *, dry_run=False, force=False, answers=None):
        super().__init__(dry_run=dry_run, force=force)
        self.commands: list[list[str]] = []
        self.probes: list[list[str]] = []
        self.answers = answers or {}
        self.said: list[str] = []

    def say(self, message=""):
        self.said.append(message)

    def run(self, command, *, what, timeout=600):
        self.commands.append(command)
        return ""

    def probe(self, command, timeout=120):
        self.probes.append(command)
        joined = " ".join(str(part) for part in command)
        for fragment, answer in self.answers.items():
            if fragment in joined:
                return answer
        return None

    def ran(self, fragment):
        return any(fragment in " ".join(str(p) for p in c) for c in self.commands)

    @property
    def output(self):
        return "\n".join(self.said)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Redirect every path `stage_registry` writes to, so no test can touch the real host."""
    monkeypatch.setattr(setup_runner, "CERT_DIR", tmp_path / "etc/cairn")
    monkeypatch.setattr(registry_provision, "CERT_DIR", tmp_path / "etc/cairn")
    monkeypatch.setattr(
        registry_provision, "SYSTEM_CA_DIR", tmp_path / "usr/local/share/ca-certificates"
    )
    monkeypatch.setattr(registry_provision, "DOCKER_CERT_DIR", tmp_path / "etc/docker/certs.d")
    monkeypatch.setattr(registry_provision, "PROJECT_DIR", tmp_path / "opt/cairn-registry")
    monkeypatch.setattr(registry_provision, "SYSTEMD_DIR", tmp_path / "etc/systemd/system")
    monkeypatch.setattr(registry_config, "CONFIG_PATH", tmp_path / "etc/cairn/registry.toml")
    monkeypatch.setattr(
        registry_config,
        "load",
        lambda path=None: registry_config.RegistryConfig(
            data_dir=tmp_path / "var/lib/cairn-registry"
        ),
    )

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True)
    (bindir / "cairn-registry").touch()
    monkeypatch.setattr(sys, "argv", [str(bindir / "cairn-registry")])

    workdir = tmp_path / "opt/cairn"
    workdir.mkdir(parents=True)
    return workdir


# --- isolation (`BR-REG-001`) -------------------------------------------------


@pytest.mark.parametrize("module", [registry_provision, registry_config])
def test_registry_modules_import_no_manifest_or_environment_machinery(module):
    """A registry host is provisioned independently of a build/target machine (`BR-REG-001`) —
    checked by parsing the module's own `import` statements, not by trusting a docstring."""
    forbidden = {"config", "environments", "adopt", "provision"}
    tree = ast.parse(inspect.getsource(module))
    imported = {
        alias.name.lstrip(".")
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    } | {
        node.module.lstrip(".") if node.module else ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }

    assert not (imported & forbidden), f"{module.__name__} imports {imported & forbidden}"


# --- the fixed stage list, no role flag (`ADR-046`, `ADR-048`) ---------------


def test_registry_setup_has_exactly_three_stages():
    assert registry_provision.REGISTRY_STAGES == ("preflight", "admin-group", "registry")
    assert set(registry_provision.REGISTRY_STAGE_FUNCS) == set(registry_provision.REGISTRY_STAGES)


# --- rule 5: preflight needs openssl, unlike either other role ---------------


def test_registry_preflight_demands_openssl(monkeypatch):
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))

    def _check(runner, label, command):
        return setup_runner.Check(label, True, "ok")

    monkeypatch.setattr(registry_provision, "check_command", _check)
    monkeypatch.setattr(setup_runner, "check_command", _check)
    monkeypatch.setattr(
        setup_runner, "check_memory", lambda: setup_runner.Check("available memory", True, "ok")
    )
    monkeypatch.setattr(
        setup_runner.shutil, "disk_usage", lambda path: type("U", (), {"free": 40_000_000_000})()
    )
    runner = Recorder()

    registry_provision.stage_preflight_registry(runner, _options())  # openssl reports ok: no raise
    assert "openssl" in runner.output


# --- the default config file (`BR-REG-002`) -----------------------------------


def test_default_config_toml_matches_registry_configs_own_defaults():
    """The rendered template is read back from `RegistryConfig()`'s own field defaults, not a
    second, hand-typed set of literals that could drift from `BR-REG-002`."""
    rendered = registry_provision.default_config_toml()
    default = registry_config.RegistryConfig()

    assert f"port = {default.port}" in rendered
    assert f'bind_address = "{default.bind_address}"' in rendered
    assert f'data_dir = "{default.data_dir}"' in rendered
    assert "enabled = false" in rendered


def test_default_config_toml_round_trips_through_load(tmp_path, monkeypatch):
    """The generated file must actually parse — every key it writes is one `registry_config`
    recognizes, and the values it reads back match `RegistryConfig()`'s own defaults."""
    path = tmp_path / "registry.toml"
    path.write_text(registry_provision.default_config_toml(), encoding="utf-8")

    loaded = registry_config.load(path)

    assert loaded == registry_config.RegistryConfig(path=path)


def test_stage_registry_creates_a_default_config_when_none_exists(sandbox):
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert registry_config.CONFIG_PATH.is_file()
    assert "created default" in runner.report.done[0]


def test_stage_registry_dry_run_creates_no_config_file(sandbox):
    runner = Recorder(dry_run=True, answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert not registry_config.CONFIG_PATH.exists()


def test_stage_registry_never_touches_an_existing_config_even_with_force(sandbox, monkeypatch):
    """Rule 3, with no `--force` escape hatch at all: once this file exists it is the
    operator's own config, exactly like `provision.py`'s starter manifest — `setup` must
    never silently discard a hand-edited `port`/`retention` value, even deliberately forced."""
    monkeypatch.setattr(registry_provision.os, "chmod", lambda path, mode: None)
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    registry_config.CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    registry_config.CONFIG_PATH.write_text("[registry]\nport = 9999\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox, force=True))

    assert registry_config.CONFIG_PATH.read_text(encoding="utf-8") == "[registry]\nport = 9999\n"


# --- the certificate ----------------------------------------------------------


def test_the_certificate_covers_localhost_and_the_private_ip():
    """The private IP is included so the certificate survives the registry and a target
    splitting onto separate machines; reissuing later means re-trusting it on every host
    that already had it."""
    sans = registry_provision.subject_alt_names("10.0.0.5")

    assert "DNS:localhost" in sans
    assert "IP:127.0.0.1" in sans
    assert "IP:10.0.0.5" in sans


def test_no_private_ip_still_yields_a_usable_certificate():
    sans = registry_provision.subject_alt_names(None)

    assert "DNS:localhost" in sans
    assert "IP:" in sans


def test_the_certificate_key_is_owner_only(sandbox, monkeypatch):
    """Key material the installer creates must not be world-readable."""
    modes = {}
    monkeypatch.setattr(
        registry_provision.os, "chmod", lambda path, mode: modes.setdefault(path, mode)
    )
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox, force=True))

    assert modes[registry_provision.CERT_DIR / "registry.key"] == 0o600


def test_the_certificate_is_trusted_in_both_stores(sandbox):
    """Python reads the system bundle; Docker reads its own per-registry directory."""
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    system_ca = registry_provision.SYSTEM_CA_DIR / "cairn-registry.crt"
    assert system_ca.read_text(encoding="utf-8") == "cert\n"
    docker_ca = registry_provision.DOCKER_CERT_DIR / "127.0.0.1:5000" / "ca.crt"
    assert docker_ca.read_text(encoding="utf-8") == "cert\n"
    assert runner.ran("update-ca-certificates")


def test_the_registry_is_verified_over_tls_before_being_claimed(sandbox):
    """Rule 6. An untrusted CA fails here rather than at the first push."""
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={})  # curl answers nothing

    with pytest.raises(registry_provision.Aborted, match="did not answer over TLS"):
        registry_provision.stage_registry(runner, _options(workdir=sandbox))


def test_a_renewed_certificate_forces_the_registry_container_to_recreate(sandbox, monkeypatch):
    """A running container has the old cert loaded in memory; `up -d` alone would leave it
    serving a certificate nothing trusts anymore, since a changed bind-mounted file is
    invisible to compose's own change detection (rule 1: re-running MUST converge)."""
    monkeypatch.setattr(registry_provision.os, "chmod", lambda path, mode: None)
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox, force=True))

    assert runner.ran("up -d --force-recreate")


def test_a_reused_certificate_leaves_the_registry_container_alone(sandbox):
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert runner.ran("up -d")
    assert not runner.ran("--force-recreate")


def test_stage_registry_creates_the_configured_data_dir(sandbox, monkeypatch):
    stub_config = registry_config.RegistryConfig(data_dir=sandbox / "registry-blobs")
    monkeypatch.setattr(registry_config, "load", lambda path=None: stub_config)
    registry_provision.CERT_DIR.mkdir(parents=True)
    (registry_provision.CERT_DIR / "registry.crt").write_text("cert\n", encoding="utf-8")
    runner = Recorder(answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert stub_config.data_dir.is_dir()
    compose = (registry_provision.PROJECT_DIR / "compose.yaml").read_text(encoding="utf-8")
    assert f"{stub_config.data_dir}:/var/lib/registry" in compose


def test_stage_registry_dry_run_creates_no_data_dir(sandbox, monkeypatch):
    stub_config = registry_config.RegistryConfig(data_dir=sandbox / "would-be-data")
    monkeypatch.setattr(registry_config, "load", lambda path=None: stub_config)
    runner = Recorder(dry_run=True, answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert not stub_config.data_dir.exists()


def test_stage_registry_dry_run_creates_no_cert_dir(sandbox, monkeypatch):
    """Rule 2: `--dry-run` prints and writes nothing. With no certificate yet present,
    generating one is the branch that used to `mkdir` `/etc/cairn` unconditionally, before
    checking `runner.dry_run` — a real filesystem mutation a dry run must never make."""
    stub_config = registry_config.RegistryConfig(data_dir=sandbox / "would-be-data")
    monkeypatch.setattr(registry_config, "load", lambda path=None: stub_config)
    runner = Recorder(dry_run=True, answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert not registry_provision.CERT_DIR.exists()


def test_stage_registry_dry_run_summary_claims_nothing_was_generated(sandbox, monkeypatch):
    """Rule 6: the summary is a record of what happened, not a claim. A dry run that never
    ran `openssl` must not report `generated <crt>` under `did` — that used to happen
    unconditionally, regardless of `runner.dry_run`."""
    stub_config = registry_config.RegistryConfig(data_dir=sandbox / "would-be-data")
    monkeypatch.setattr(registry_config, "load", lambda path=None: stub_config)
    runner = Recorder(dry_run=True, answers={"curl": "ok"})

    registry_provision.stage_registry(runner, _options(workdir=sandbox))

    assert runner.report.done == []


# --- the compose file ----------------------------------------------------------


def test_the_registry_compose_contents():
    """One `registry_compose()` render, checked against every property it must have.

    - bound to the configured address/port: never exposed further than the operator chose.
    - the cairn-managed label: so `cairn-adopt examine` can recognize this project as cairn's
      own infrastructure by label — never by assuming anything from the project name.
    - delete-enabled storage: what makes retention (`BR-REG-006`) possible; some hosted
      registries cannot do it at all.
    - a bind-mounted data_dir, not an anonymous volume: an operator-chosen disk location.
    - no credentials: a registry behind cairn's own TLS needs no auth of its own here.
    """
    config = registry_config.RegistryConfig()
    rendered = registry_provision.registry_compose(config)

    assert f'"{config.bind_address}:{config.port}:{config.port}"' in rendered
    assert f"{registry_provision.CAIRN_MANAGED_LABEL}=true" in rendered
    assert "REGISTRY_STORAGE_DELETE_ENABLED" in rendered
    assert f"{config.data_dir}:/var/lib/registry" in rendered
    assert "PASSWORD" not in rendered.upper()
    assert "htpasswd" not in rendered
    assert "AUTH" not in rendered.upper()


def test_the_compose_file_honors_a_configured_port_and_bind_address():
    config = registry_config.RegistryConfig(port=5001, bind_address="0.0.0.0")
    rendered = registry_provision.registry_compose(config)

    assert '"0.0.0.0:5001:5001"' in rendered
    assert "REGISTRY_HTTP_ADDR: 0.0.0.0:5001" in rendered


def test_compose_command_addresses_the_registry_project_by_directory(sandbox):
    command = registry_provision.compose_command("up", "-d")

    assert command[:3] == ["docker", "compose", "--project-directory"]
    assert command[-2:] == ["up", "-d"]


def test_read_only_mode_adds_the_maintenance_env_var():
    config = registry_config.RegistryConfig()

    normal = registry_provision.registry_compose(config)
    read_only = registry_provision.registry_compose(config, read_only=True)

    assert "REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED" not in normal
    assert 'REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED: "true"' in read_only


# --- lifecycle (BR-REG-004) ---------------------------------------------------


def test_start_stop_restart_are_thin_compose_wrappers(sandbox):
    runner = Recorder()

    registry_provision.start(runner)
    registry_provision.stop(runner)
    registry_provision.restart(runner)

    assert runner.ran("up -d")
    assert runner.ran("stop")
    assert runner.ran("restart")
    assert not any("volume" in " ".join(c) for c in runner.commands)


def test_status_returns_composes_own_output(sandbox):
    runner = Recorder(answers={"ps": "registry   running"})

    output = registry_provision.status(runner)

    assert "running" in output


# --- gc (BR-REG-009) -----------------------------------------------------


def test_gc_toggles_read_only_mode_around_the_collect(sandbox, monkeypatch):
    monkeypatch.setattr(registry_config, "load", lambda path=None: registry_config.RegistryConfig())
    runner = Recorder()

    registry_provision.gc(runner)

    compose_writes = [c for c in runner.said if "compose.yaml" in c and "write" in c]
    assert any("read-only maintenance mode" in c for c in compose_writes)
    assert any("read-write mode" in c for c in compose_writes)
    # two recreates (read-only, then read-write) bracketing the collect itself
    up_calls = [c for c in runner.commands if c[:2] == ["docker", "compose"] and "up" in c]
    assert len(up_calls) == 2
    assert runner.ran("garbage-collect")


def test_gc_warns_that_pushes_are_briefly_refused(sandbox, monkeypatch):
    monkeypatch.setattr(registry_config, "load", lambda path=None: registry_config.RegistryConfig())
    runner = Recorder()

    registry_provision.gc(runner)

    assert any("pushes are" in warning for warning in runner.report.warnings)


def test_gc_dry_run_writes_no_compose_file(sandbox, monkeypatch):
    stub_config = registry_config.RegistryConfig(data_dir=sandbox / "data")
    monkeypatch.setattr(registry_config, "load", lambda path=None: stub_config)
    runner = Recorder(dry_run=True)

    registry_provision.gc(runner)

    assert not (registry_provision.PROJECT_DIR / "compose.yaml").exists()


def test_gc_runs_garbage_collect_against_the_containers_own_config_path(sandbox, monkeypatch):
    monkeypatch.setattr(registry_config, "load", lambda path=None: registry_config.RegistryConfig())
    runner = Recorder()

    registry_provision.gc(runner)

    gc_call = next(c for c in runner.commands if "garbage-collect" in c)
    assert gc_call[-1] == registry_provision.CONTAINER_CONFIG_PATH
    assert gc_call[:5] == [
        "docker",
        "compose",
        "--project-directory",
        str(registry_provision.PROJECT_DIR),
        "exec",
    ]


# --- setup-timer (BR-CLI-027, BR-REG-010) -------------------------------------


def test_timer_stages_are_exactly_one(sandbox):
    assert registry_provision.TIMER_STAGES == ("timers",)
    assert set(registry_provision.REGISTRY_TIMER_STAGE_FUNCS) == {"timers"}


def test_maintenance_script_runs_prune_then_gc():
    rendered = registry_provision.maintenance_script("/opt/cairn", "/usr/bin/cairn-registry")

    assert "prune --yes" in rendered
    assert "gc --yes" in rendered
    assert rendered.index("prune --yes") < rendered.index("gc --yes")


def test_maintenance_service_does_not_restart_on_failure():
    rendered = registry_provision.maintenance_service("/opt/cairn/registry-maintenance.sh")

    assert "Type=oneshot" in rendered
    assert "Restart=" not in rendered


def test_maintenance_timer_uses_the_configured_schedule():
    rendered = registry_provision.maintenance_timer("weekly")

    assert "OnCalendar=weekly" in rendered
    assert registry_provision.MAINTENANCE_UNIT_NAME in rendered


def test_setup_timer_is_root_gated(sandbox, monkeypatch):
    monkeypatch.setattr(
        setup_runner,
        "_check_root",
        lambda: setup_runner.Check("root", False, "must be run with sudo"),
    )
    runner = Recorder()

    with pytest.raises(registry_provision.Aborted, match="sudo"):
        registry_provision.stage_timers_registry(runner, _options(workdir=sandbox))


def test_setup_timer_is_enabled_but_never_started(sandbox, monkeypatch):
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    runner = Recorder()

    registry_provision.stage_timers_registry(runner, _options(workdir=sandbox))

    assert (
        registry_provision.SYSTEMD_DIR / f"{registry_provision.MAINTENANCE_UNIT_NAME}.timer"
    ).exists()
    assert runner.ran("systemctl enable")
    assert not runner.ran("systemctl start")
    assert any("NOT started" in note for note in runner.report.warnings)


def test_setup_timer_writes_the_schedule_from_config(sandbox, monkeypatch):
    monkeypatch.setattr(setup_runner, "_check_root", lambda: setup_runner.Check("root", True, "ok"))
    monkeypatch.setattr(
        registry_config,
        "load",
        lambda path=None: registry_config.RegistryConfig(gc=registry_config.Gc(schedule="daily")),
    )
    runner = Recorder()

    registry_provision.stage_timers_registry(runner, _options(workdir=sandbox))

    timer = (
        registry_provision.SYSTEMD_DIR / f"{registry_provision.MAINTENANCE_UNIT_NAME}.timer"
    ).read_text(encoding="utf-8")
    assert "OnCalendar=daily" in timer
