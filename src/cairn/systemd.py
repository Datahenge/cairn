"""Emit the systemd service and timer for `cairn-adopt reconcile` (`BR-CLI-019`, `ADR-035`).

cairn **prints** these; it never writes to `/etc/systemd/system` and never reloads the daemon
(`ADR-035`). Writing them would need root and would change the host outside cairn's stated
boundary — `BR-DEPLOY-008` makes cairn a thin orchestrator *over* systemd, not an adopter of
the host's init configuration.

Printing them is still cairn's job rather than the operator's guesswork, because the unit
encodes things only cairn knows: that a pass is idempotent and safe to repeat, that it is
already single-flight so a `Persistent` catch-up cannot stack (`BR-DEPLOY-016`), and that it
must not be given a log file because journald already owns the record (`BR-DEPLOY-019`).

Every host-specific value is **reported, not assumed silently** (`BR-CLI-019`): the binary
path, the user, and the cadence are printed alongside the units so a wrong one is visible
before it is installed rather than after it fails.
"""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass

#: How often a target asks the registry whether its pointer moved. Frequent enough that a
#: deploy lands within minutes, rare enough to be unnoticeable against a registry.
DEFAULT_INTERVAL = "5min"

#: Spread across hosts so several targets on one timer do not poll in lockstep.
DEFAULT_JITTER = "30s"

UNIT_NAME = "cairn-reconcile"


@dataclass(frozen=True)
class Units:
    """The two rendered unit files, and the assumptions they were rendered from."""

    service: str
    timer: str
    executable: str
    user: str
    interval: str

    @property
    def assumptions(self) -> list[str]:
        """The host-specific values cairn chose, so a wrong one is caught before install."""
        return [
            f"executable   {self.executable}",
            f"user         {self.user}",
            f"interval     {self.interval} (plus up to {DEFAULT_JITTER} of jitter)",
            f"unit names   {UNIT_NAME}.service, {UNIT_NAME}.timer",
        ]

    def render(self) -> str:
        """The units, each under the filename it should be installed as."""
        return "\n".join(
            [
                f"# --- /etc/systemd/system/{UNIT_NAME}.service ---",
                self.service,
                f"# --- /etc/systemd/system/{UNIT_NAME}.timer ---",
                self.timer,
            ]
        )


def units(
    *, executable: str | None = None, user: str = "root", interval: str = DEFAULT_INTERVAL
) -> Units:
    """Render the service and timer for this host (`BR-CLI-019`)."""
    resolved = executable or _executable()
    return Units(
        service=_service(resolved, user),
        timer=_timer(interval),
        executable=resolved,
        user=user,
        interval=interval,
    )


def _service(executable: str, user: str) -> str:
    """The unit that runs one reconcile pass.

    ``Type=oneshot`` because a pass ends: it is not a daemon, and systemd should consider the
    unit inactive between runs rather than restarting it. No ``Restart=`` for the same reason
    — a failed deploy must halt and be seen (`BR-DEPLOY-018`), and a restart loop against a
    failing migration is how a bad deploy becomes a busy one. No log file is configured
    anywhere: journald has the output already (`BR-DEPLOY-019`).
    """
    return f"""\
[Unit]
Description=cairn — converge this host to its environment's desired state
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
User={user}
ExecStart={executable} reconcile
# A pass that cannot finish in an hour is stuck, not slow: the image pull, the compose
# recreate, and bench migrate each carry their own ceiling well inside this one.
TimeoutStartSec=3600

[Install]
WantedBy=multi-user.target
"""


def _timer(interval: str) -> str:
    """The timer that drives it.

    ``Persistent=true`` is safe *because* a pass is idempotent and single-flight: a host that
    was off catches up once on boot, and a catch-up that collides with a running pass exits
    reporting the lock instead of queueing (`BR-DEPLOY-016`).
    """
    return f"""\
[Unit]
Description=cairn — poll for a moved deploy pointer

[Timer]
OnBootSec=2min
OnUnitInactiveSec={interval}
RandomizedDelaySec={DEFAULT_JITTER}
Persistent=true
Unit={UNIT_NAME}.service

[Install]
WantedBy=timers.target
"""


def install_hint() -> list[str]:
    """What to do with the printed units — deliberately manual (`ADR-035`)."""
    return [
        "To install, review the units above, then:",
        f"  sudo tee /etc/systemd/system/{UNIT_NAME}.service < the service section",
        f"  sudo tee /etc/systemd/system/{UNIT_NAME}.timer   < the timer section",
        "  sudo systemctl daemon-reload",
        f"  sudo systemctl enable --now {UNIT_NAME}.timer",
        f"Then watch it with: journalctl -u {UNIT_NAME}.service -f",
    ]


def _executable() -> str:
    """The path to `cairn-adopt`, so the unit runs the same one that printed it.

    ``sys.argv[0]`` is not enough — under a console script it may be a bare name that
    resolves differently for root than for the invoking user, and a unit that cannot find its
    binary fails at 3am rather than now.
    """
    return shutil.which("cairn-adopt") or f"{sys.executable} -m cairn.cli_adopt"
