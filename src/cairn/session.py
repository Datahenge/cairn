"""Interactive and inspection sessions against the target stack (`BR-CLI-030`, `ADR-075`).

The gap `ADR-073` left. Forbidding an operator to run `docker compose` by hand only works if
cairn offers the things they legitimately need — a console, a SQL prompt, logs. These are
**named verbs**, deliberately not the general passthrough `W-037` proposed and Brian rejected:
the specific cases are made easy, arbitrary compose use stays awkward.

Command construction is kept separate from execution so the commands can be asserted on
without running anything.
"""

from __future__ import annotations

import os
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
