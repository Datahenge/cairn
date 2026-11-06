"""Tests for the target-stack inspection verbs (BR-CLI-030, ADR-075)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cairn import descriptor, session
from cairn.errors import CairnError


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


# --- interactive verbs allocate a TTY (BR-CLI-030) ----------------------------


@pytest.mark.parametrize("build", [session.console_command, session.mariadb_command])
def test_interactive_verbs_never_disable_the_tty(build) -> None:
    """BR-CLI-030: `-T` would put the MariaDB client into silent batch mode.

    Without a TTY the client suppresses its banner and prompt entirely and waits on stdin,
    which is indistinguishable from a hang — the exact confusion that prompted these verbs.
    `bench console` masks the problem because Python's console prints prompts regardless of
    `isatty`, so testing only that one would prove nothing.
    """
    command, _ = build(_descriptor())
    assert "-T" not in command
    assert command[:2] == ["docker", "compose"]


@pytest.mark.parametrize("build", [session.console_command, session.mariadb_command])
def test_interactive_verbs_carry_the_image_variables(build) -> None:
    """BR-VEND-006: a compose invocation without these cannot resolve its image reference."""
    _, environment = build(_descriptor())
    assert environment["CUSTOM_IMAGE"] == "ghcr.io/datahenge/erpnext-btu-v16"
    assert environment["CUSTOM_TAG"] == "production"


def test_the_site_comes_from_the_descriptor_not_the_operator() -> None:
    """BR-CLI-030: these verbs take no arguments — that is the point of having them."""
    command, _ = session.console_command(_descriptor(site="erp.lsnav.app"))
    assert "erp.lsnav.app" in command


# --- mariadb declines a Postgres environment (BR-CLI-030) ---------------------


def test_mariadb_refuses_when_the_descriptor_composes_postgres() -> None:
    """BR-CLI-030: naming the engine beats letting the client fail obscurely inside."""
    target = _descriptor(compose=descriptor.Compose(overrides=("postgres", "redis")))
    with pytest.raises(CairnError, match="postgres"):
        session.mariadb_command(target)


def test_mariadb_proceeds_without_the_postgres_override() -> None:
    command, _ = session.mariadb_command(
        _descriptor(compose=descriptor.Compose(overrides=("redis",)))
    )
    assert command[-1] == "mariadb"


# --- logs is bounded, not a passthrough (ADR-075) -----------------------------


def test_logs_defaults_to_the_whole_project() -> None:
    command, _ = session.logs_command(_descriptor())
    assert command[-1] == "logs"


def test_logs_applies_only_its_own_flags() -> None:
    """ADR-075: bounded flags, so this stays a verb rather than becoming W-037's passthrough."""
    command, _ = session.logs_command(_descriptor(), follow=True, tail=200, service="backend")
    assert command[-5:] == ["logs", "--follow", "--tail", "200", "backend"]


# --- become replaces the process (BR-CLI-030) --------------------------------


def test_become_execs_rather_than_spawning(monkeypatch) -> None:
    """BR-CLI-030: replacing the process hands the terminal and its signals to the client.

    A subprocess would leave Python in the middle, forwarding Ctrl-C and owning the exit
    status; `execvp` means what the operator sees is what the client returned.
    """
    seen: dict = {}

    def fake_exec(binary, argv):
        seen["binary"] = binary
        seen["argv"] = argv
        raise SystemExit(0)

    monkeypatch.setattr(session.os, "execvp", fake_exec)
    with pytest.raises(SystemExit):
        session.become((["docker", "compose", "ps"], {"CUSTOM_TAG": "production"}))

    assert seen["binary"] == "docker"
    assert seen["argv"] == ["docker", "compose", "ps"]
    # The environment must be in place *before* the exec, since execvp keeps os.environ.
    assert session.os.environ["CUSTOM_TAG"] == "production"


def test_become_reports_a_missing_docker_as_a_cairn_error(monkeypatch) -> None:
    def fake_exec(binary, argv):
        raise OSError(2, "No such file or directory")

    monkeypatch.setattr(session.os, "execvp", fake_exec)
    with pytest.raises(CairnError, match="not available"):
        session.become((["docker", "compose", "ps"], {}))


# --- shell replaces "print me the config" (BR-DATA-006, BR-CLI-030) ----------


def test_shell_defaults_to_the_bench_container() -> None:
    command, _ = session.shell_command(_descriptor())
    assert command[-2:] == ["backend", "bash"]


def test_shell_can_enter_another_service() -> None:
    command, _ = session.shell_command(_descriptor(), "db")
    assert command[-2:] == ["db", "bash"]


def test_shell_allocates_a_tty() -> None:
    """BR-CLI-030: a shell without a TTY has no prompt, no job control and no line editing."""
    command, _ = session.shell_command(_descriptor())
    assert "-T" not in command


def test_no_verb_reads_the_sites_volume() -> None:
    """BR-DATA-006: cairn must not read site_config.json or common_site_config.json.

    `shell` exists precisely so an operator can read their own config without cairn touching
    it — the credential in `site_config.json` never passes through cairn or its output
    (`BR-DEPLOY-011`). This asserts the boundary at the command level: no verb may name those
    files, so none can quietly grow a `cat` of them.
    """
    target = _descriptor()
    built = [
        session.console_command(target),
        session.mariadb_command(target),
        session.shell_command(target),
        session.logs_command(target),
        session.cp_command(target, "/srv/backup.tar", "backend:/tmp/"),
        session.container_info_command(target),
    ]
    for command, _ in built:
        joined = " ".join(command)
        assert "site_config.json" not in joined
        assert "common_site_config.json" not in joined
        assert "cat" not in command


# --- cp moves only what the operator names (BR-CLI-032, ADR-080) -------------


def test_cp_into_a_container_absolutizes_the_host_side(tmp_path) -> None:
    """BR-CLI-032: the invocation carries --project-directory, so a relative path must not
    be left for compose to resolve against that instead of the operator's directory."""
    command, environment = session.cp_command(
        _descriptor(), "dump.sql.gz", "backend:/home/frappe/backups/", cwd=tmp_path
    )
    assert command[-3:] == ["cp", str(tmp_path / "dump.sql.gz"), "backend:/home/frappe/backups/"]
    assert environment["CUSTOM_TAG"] == "production"


def test_cp_out_of_a_container_absolutizes_the_destination(tmp_path) -> None:
    command, _ = session.cp_command(
        _descriptor(), "backend:/home/frappe/backups/x.tar", ".", cwd=tmp_path
    )
    assert command[-3:] == ["cp", "backend:/home/frappe/backups/x.tar", str(tmp_path)]


def test_cp_leaves_an_absolute_host_path_alone(tmp_path) -> None:
    command, _ = session.cp_command(_descriptor(), "/srv/x.tar", "backend:/tmp/", cwd=tmp_path)
    assert command[-2] == "/srv/x.tar"


def test_cp_is_scoped_to_the_descriptors_project() -> None:
    target = _descriptor(compose=descriptor.Compose(project="erpnext"))
    command, _ = session.cp_command(target, "/srv/x.tar", "backend:/tmp/")
    assert command[command.index("--project-name") + 1] == "erpnext"


@pytest.mark.parametrize(
    ("source", "destination", "message"),
    [
        ("backend:/a", "db:/b", "both paths"),
        ("/srv/a", "/srv/b", "neither path"),
        ("./a:b", "/srv/b", "neither path"),
    ],
)
def test_cp_refuses_unless_exactly_one_side_is_a_container(source, destination, message) -> None:
    """BR-CLI-032: refused before running anything, so compose's own error never surfaces."""
    with pytest.raises(CairnError, match=message):
        session.cp_command(_descriptor(), source, destination)


# --- container-info lists the stack plainly (BR-CLI-031) ---------------------

_PS_LINES = "\n".join(
    [
        '{"ID":"e228456ff8ef0123456789","Name":"erpnext-backend-1","Project":"erpnext",'
        '"Service":"backend","Image":"127.0.0.1:5000/acmecorp/erpnext-v16:production",'
        '"Status":"Up 2 days","Command":"/usr/local/bin/entrypoint.sh","Publishers":[]}',
        '{"ID":"3b1de90c6973abcdef","Name":"erpnext-db-1","Project":"erpnext",'
        '"Service":"db","Image":"mariadb:11.8","Status":"Up 2 days (healthy)"}',
        '{"ID":"835b8fdb87b6aaaa","Name":"erpnext-caddy-1","Project":"erpnext",'
        '"Service":"caddy","Image":"caddy:2-alpine","Status":"Exited (0) 1 hour ago"}',
    ]
)


def test_container_info_includes_stopped_containers() -> None:
    """BR-CLI-031: `stop` keeps its containers, and a held stack is when an operator looks."""
    command, _ = session.container_info_command(_descriptor())
    assert command[-4:] == ["ps", "--all", "--format", "json"]


def test_containers_parse_sorted_by_service_with_short_ids() -> None:
    project, containers = session.parse_containers(_PS_LINES)
    assert project == "erpnext"
    assert [c.service for c in containers] == ["backend", "caddy", "db"]
    assert containers[0].id == "e228456ff8ef"


def test_containers_parse_from_a_single_json_array() -> None:
    """Older compose emits one array rather than one object per line."""
    array = "[" + ",".join(_PS_LINES.splitlines()) + "]"
    _, containers = session.parse_containers(array)
    assert len(containers) == 3


def test_the_listing_drops_the_command_and_ports_columns() -> None:
    """BR-CLI-031: their width is what makes `docker container ls` hard to read."""
    project, containers = session.parse_containers(_PS_LINES)
    target = _descriptor(compose=descriptor.Compose(directory=Path("/etc/cairn")))
    text = session.render_containers(target, project, containers)
    lines = text.splitlines()
    assert lines[0] == "Project erpnext  (/etc/cairn/compose.yaml)"
    assert lines[2].split() == ["SERVICE", "NAME", "ID", "IMAGE", "STATUS"]
    assert "entrypoint" not in text
    assert "Up 2 days (healthy)" in text


def test_the_project_name_comes_from_compose_when_the_descriptor_omits_it() -> None:
    """BR-CLI-031: `[compose] project` is optional, and only compose knows the derived name."""
    project, containers = session.parse_containers(_PS_LINES)
    text = session.render_containers(_descriptor(), project, containers)
    assert text.startswith("Project erpnext")


def test_an_empty_project_says_so() -> None:
    text = session.render_containers(_descriptor(), None, [])
    assert "no containers" in text


def test_a_failing_engine_is_reported_with_its_own_message(monkeypatch) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="permission denied")

    monkeypatch.setattr(session.subprocess, "run", fake_run)
    with pytest.raises(CairnError, match="permission denied"):
        session.container_info(_descriptor())
