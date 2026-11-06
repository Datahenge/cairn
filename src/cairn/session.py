"""Interactive and inspection sessions against the target stack (`BR-CLI-030`, `ADR-075`).

The gap `ADR-073` left. Forbidding an operator to run `docker compose` by hand only works if
cairn offers the things they legitimately need — a console, a SQL prompt, logs. These are
**named verbs**, deliberately not the general passthrough `W-037` proposed and Brian rejected:
the specific cases are made easy, arbitrary compose use stays awkward.

Command construction is kept separate from execution so the commands can be asserted on
without running anything.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from .descriptor import Descriptor
from .errors import CairnError
from .reconcile import BENCH_SERVICE, compose_invocation

#: The override whose presence means the site is not on MariaDB (`BR-CLI-030`).
POSTGRES_OVERRIDE = "postgres"


def console_command(descriptor: Descriptor) -> tuple[list[str], dict[str, str]]:
    """`bench console` for this descriptor's site, with a TTY (`BR-CLI-030`)."""
    return compose_invocation(
        descriptor, ["exec", BENCH_SERVICE, "bench", "--site", descriptor.site, "console"]
    )


def mariadb_command(descriptor: Descriptor) -> tuple[list[str], dict[str, str]]:
    """`bench mariadb` for this descriptor's site, with a TTY (`BR-CLI-030`).

    Refuses when the descriptor layers the Postgres override. Best-effort by design: a
    hand-built stack can run Postgres without declaring an override, so this catches the
    declared case and says so rather than pretending to be a guarantee.
    """
    if POSTGRES_OVERRIDE in descriptor.compose.overrides:
        raise CairnError(
            f"this environment composes the '{POSTGRES_OVERRIDE}' override, so its site is not "
            "on MariaDB. Open a Postgres client inside the stack instead."
        )
    return compose_invocation(
        descriptor, ["exec", BENCH_SERVICE, "bench", "--site", descriptor.site, "mariadb"]
    )


def shell_command(
    descriptor: Descriptor, service: str | None = None
) -> tuple[list[str], dict[str, str]]:
    """An interactive shell inside a container of this stack (`BR-CLI-030`).

    Deliberately the answer to "print me `site_config.json`" rather than a verb that reads it.
    `BR-DATA-006` forbids cairn reading `site_config.json`/`common_site_config.json` at all,
    and `BR-DEPLOY-011` forbids it handling secret values — that file carries `db_password`.
    Handing over a shell keeps both intact: the operator reads their own file, and no
    credential passes through cairn or lands in its output.
    """
    return compose_invocation(descriptor, ["exec", service or BENCH_SERVICE, "bash"])


def logs_command(
    descriptor: Descriptor,
    *,
    follow: bool = False,
    tail: int | None = None,
    service: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Compose logs for the project, or one service (`BR-CLI-030`).

    Bounded flags only. A passthrough for arbitrary arguments would reintroduce the shape
    `ADR-075` declined.
    """
    arguments = ["logs"]
    if follow:
        arguments.append("--follow")
    if tail is not None:
        arguments += ["--tail", str(tail)]
    if service:
        arguments.append(service)
    return compose_invocation(descriptor, arguments)


def cp_command(
    descriptor: Descriptor, source: str, destination: str, *, cwd: Path | None = None
) -> tuple[list[str], dict[str, str]]:
    """`docker compose cp` between the host and one container of this stack (`BR-CLI-032`).

    Both ends are the operator's, which is what keeps this on the operator's side of
    `BR-DATA-003`/`BR-DATA-006` (`ADR-080`): cairn chooses, defaults and reads nothing. The one
    change it makes is absolutizing the host side against the operator's own working directory,
    because the invocation carries `--project-directory` and a relative path must not be read
    against that instead.
    """
    source_side, destination_side = _container_side(source), _container_side(destination)
    if source_side and destination_side:
        raise CairnError(
            "both paths name a container. One side must be a path on this host, the other "
            "SERVICE:PATH."
        )
    if not source_side and not destination_side:
        raise CairnError(
            "neither path names a container. Write the container side as SERVICE:PATH, "
            "for example backend:/home/frappe/frappe-bench/sites."
        )
    base = cwd or Path.cwd()
    if source_side:
        destination = str(base / destination)
    else:
        source = str(base / source)
    return compose_invocation(descriptor, ["cp", source, destination])


def _container_side(argument: str) -> bool:
    """True when *argument* is compose's ``SERVICE:PATH`` form rather than a host path.

    A host path containing a colon after a slash (``./a:b``) stays a host path, as it does for
    compose itself.
    """
    service, colon, _ = argument.partition(":")
    return bool(colon) and bool(service) and "/" not in service


#: Width of the container ID shown, matching `docker container ls`.
SHORT_ID_LENGTH = 12

#: Ceiling on the listing, which only asks the engine and should answer at once.
CONTAINER_INFO_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class Container:
    """One container of the stack, as `container-info` shows it (`BR-CLI-031`)."""

    service: str
    name: str
    id: str
    image: str
    status: str


def container_info_command(descriptor: Descriptor) -> tuple[list[str], dict[str, str]]:
    """`compose ps` for this stack, stopped containers included (`BR-CLI-031`).

    ``--all`` because `stop` keeps its containers (`ADR-073`), and a held stack is when an
    operator most wants to see them.
    """
    return compose_invocation(descriptor, ["ps", "--all", "--format", "json"])


def parse_containers(output: str) -> tuple[str | None, list[Container]]:
    """The compose project name and its containers, sorted by service, from ``ps`` JSON.

    Compose emits either one object per line or a single array, depending on its version, as
    `adopt._bench_image` also handles. The project name is read back from compose rather than
    the descriptor because `[compose] project` is optional, and when it is unset only compose
    knows the name it derived.
    """
    project: str | None = None
    containers: list[Container] = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        for item in entry if isinstance(entry, list) else [entry]:
            if not isinstance(item, dict):
                continue
            project = project or item.get("Project") or None
            containers.append(
                Container(
                    service=str(item.get("Service", "")),
                    name=str(item.get("Name", "")),
                    id=str(item.get("ID", ""))[:SHORT_ID_LENGTH],
                    image=str(item.get("Image", "")),
                    status=str(item.get("Status", "")),
                )
            )
    containers.sort(key=lambda c: (c.service, c.name))
    return project, containers


def render_containers(
    descriptor: Descriptor, project: str | None, containers: list[Container]
) -> str:
    """The `container-info` listing: a project line, then one aligned row per container."""
    name = project or descriptor.compose.project or "?"
    heading = f"Project {name}"
    if descriptor.compose.directory is not None:
        heading += f"  ({descriptor.compose.directory / descriptor.compose.file})"
    if not containers:
        return f"{heading}\n\nThis project has no containers. Has the stack been brought up?"
    header = ("SERVICE", "NAME", "ID", "IMAGE", "STATUS")
    rows = [header] + [(c.service, c.name, c.id, c.image, c.status) for c in containers]
    widths = [max(len(row[i]) for row in rows) for i in range(len(header) - 1)]
    lines = [
        "  ".join(cell.ljust(width) for cell, width in zip(row[:-1], widths, strict=True))
        + "  "
        + row[-1]
        for row in rows
    ]
    return "\n".join([heading, "", *lines])


def container_info(descriptor: Descriptor) -> str:
    """List this stack's containers (`BR-CLI-031`). Read-only; takes no lock."""
    command, environment = container_info_command(descriptor)
    try:
        result = subprocess.run(
            command,
            timeout=CONTAINER_INFO_TIMEOUT_SECONDS,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **environment},
        )
    except FileNotFoundError as exc:
        raise CairnError(f"`{command[0]}` is not available on this host.") from exc
    except subprocess.TimeoutExpired as exc:
        raise CairnError(
            f"the container engine did not answer within {CONTAINER_INFO_TIMEOUT_SECONDS}s."
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit status {result.returncode}"
        raise CairnError(f"could not list this environment's containers: {detail}")
    project, containers = parse_containers(result.stdout)
    return render_containers(descriptor, project, containers)


def become(invocation: tuple[list[str], dict[str, str]]) -> NoReturn:
    """Replace this process with *invocation* (`BR-CLI-030`, `ADR-075`).

    ``execvp``, not a subprocess: the terminal, Ctrl-C and Ctrl-D then belong to the client
    itself rather than to a Python parent that would have to forward them. It also means cairn
    contributes nothing to the session's exit status — what the operator sees is what the
    client returned.

    A missing `docker` raises rather than exits, so the caller reports it the way every other
    command does.
    """
    command, environment = invocation
    os.environ.update(environment)
    try:
        os.execvp(command[0], command)
    except OSError as exc:
        raise CairnError(
            f"`{command[0]}` is not available on this host, so the session cannot start."
        ) from exc
