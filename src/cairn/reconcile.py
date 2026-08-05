"""Converge this host to its desired state (BR-CLI-008, BR-DEPLOY-001/003/016/017/018).

The target half of the deploy model. The desired state is a **digest in a registry** — the
one the environment's watched tag currently resolves to (`BR-DEPLOY-002`) — and this module's
only job is to make the running stack match it.

The loop, in the order `BR-DEPLOY-003` fixes:

1. resolve the watched tag to a digest, outbound only (`BR-DEPLOY-001`);
2. compare it with what this host actually runs; **if they agree, do nothing** — a
   no-change run is a no-op, and that is the common case under a timer;
3. otherwise pull, render the compose stack, `compose up -d`, `bench migrate`, and verify
   health before recording success.

Four rules this module exists to keep:

* **Single-flight** (`BR-DEPLOY-016`). A timer that fires while a deploy is still running
  must not start a second one. The lock is held for the whole pass, and a second invocation
  exits reporting the lock rather than waiting behind it — under a timer, waiting only
  builds a queue.
* **`bench migrate` after *every* image enable**, including a rollback (`BR-DEPLOY-016`). A
  rollback is a deploy; the schema has to be reconciled either way.
* **Failure halts and reports; it never rolls back** (`BR-DEPLOY-018`). An automatic
  rollback would run `migrate` a second time, against a schema whose state is exactly what
  is now in doubt. Reporting is better than guessing (`ADR-025`).
* **No writes to the data plane of cairn's own** (`BR-DATA-005/006/008`). cairn runs
  `bench migrate`, which Frappe owns; it touches no volume, no SQL, and no site config.
  ``bench install-app`` is deliberately absent — see the note at :func:`converge`.

Everything is logged to stdout/stderr and nowhere else (`BR-DEPLOY-019`): under a timer,
journald already owns the record.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from . import registry
from .descriptor import Descriptor
from .errors import ReconcileError, RegistryError

#: Where the single-flight lock lives. ``/run`` is tmpfs, so the lock cannot outlive a boot.
LOCK_PATH = Path("/run/cairn/reconcile.lock")

#: The compose service `bench` commands run in, per frappe_docker's own layout.
BENCH_SERVICE = "backend"

#: Ceiling on a pull. Images are gigabytes over a VPS link; generous, but not unbounded.
PULL_TIMEOUT_SECONDS = 3600

#: Ceiling on `compose up`, which starts containers but waits for no application.
COMPOSE_TIMEOUT_SECONDS = 600

#: Ceiling on `bench migrate`. Long migrations are normal; hung ones are not.
MIGRATE_TIMEOUT_SECONDS = 3600

#: Ceiling on the short informational commands.
PROBE_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class State:
    """Desired versus actual, which is the whole of what a reconcile decides."""

    desired_digest: str
    running_digest: str | None
    stack_up: bool

    @property
    def is_converged(self) -> bool:
        """Whether this host already runs the desired image, with its stack up.

        Both halves matter. A matching digest with a stopped stack is not convergence — it is
        a host that pulled an image and then died — and reporting it as success is how a timer
        comes to hide an outage.
        """
        return self.stack_up and self.running_digest == self.desired_digest

    @property
    def is_first_deploy(self) -> bool:
        return self.running_digest is None


@dataclass(frozen=True)
class Outcome:
    """What a pass did, for the caller to report and exit on."""

    converged: bool
    changed: bool
    state: State
    detail: str


def run(
    descriptor: Descriptor,
    *,
    dry_run: bool = False,
    report: Callable[[str], None] = lambda message: None,
) -> Outcome:
    """Converge the host, or report why it did not (`BR-CLI-008`).

    Held under the single-flight lock for the whole pass, including the registry read: two
    passes reading the same tag and then racing to `compose up` is the failure the lock
    exists to prevent, not merely two overlapping pulls.
    """
    with _single_flight(dry_run=dry_run):
        state = inspect(descriptor, report=report)

        if state.is_converged:
            return Outcome(
                converged=True,
                changed=False,
                state=state,
                detail=f"Already running {state.desired_digest}.",
            )

        if dry_run:
            return Outcome(
                converged=False,
                changed=False,
                state=state,
                detail=_would_do(state),
            )

        converge(descriptor, state, report=report)
        return Outcome(
            converged=True,
            changed=True,
            state=state,
            detail=f"Converged to {state.desired_digest}.",
        )


def inspect(
    descriptor: Descriptor, *, report: Callable[[str], None] = lambda message: None
) -> State:
    """Read desired state from the registry and actual state from the host."""
    reference = registry.parse_ref(descriptor.reference)
    report(f"Watching {reference}")

    try:
        desired = registry.digest_of(reference)
    except RegistryError as exc:
        raise ReconcileError(
            f"Cannot read the desired state for '{descriptor.environment}': {exc}"
        ) from exc

    running = running_digest(descriptor)
    return State(
        desired_digest=desired,
        running_digest=running,
        stack_up=stack_is_up(descriptor),
    )


def converge(
    descriptor: Descriptor,
    state: State,
    *,
    report: Callable[[str], None] = lambda message: None,
) -> None:
    """Pull, recreate the stack in place, migrate, and verify health (`BR-DEPLOY-003`).

    ``bench install-app`` is **never** run, by decision rather than omission (`ADR-037`,
    `BR-DEPLOY-003a`). This function is a convergence step — safe because repeating it is a
    no-op — and ``install-app`` is a one-shot irreversible mutation that would have to
    remember whether it had already happened. It is also a second data-plane write
    (`ADR-022`), and it breaks rollback: move the pointer back and the app's schema remains
    while the code that understands it is gone. Installing an app is the operator's act, as
    site creation already is (`BR-DEPLOY-007`).
    """
    reference = descriptor.reference

    report(f"Pulling {reference}")
    _run(["docker", "pull", reference], PULL_TIMEOUT_SECONDS, "pulling the image")

    report("Starting the stack")
    _run(
        _compose_command(descriptor, ["up", "-d", "--remove-orphans"]),
        COMPOSE_TIMEOUT_SECONDS,
        "starting the stack",
        env_overrides=_compose_environment(descriptor),
    )

    # After every image enable, rollback included (BR-DEPLOY-016). Frappe owns the schema;
    # cairn only asks for the migration it already documents as the sole DB touch.
    report(f"Migrating {descriptor.site}")
    _run(
        _compose_command(
            descriptor, ["exec", "-T", BENCH_SERVICE, "bench", "--site", descriptor.site, "migrate"]
        ),
        MIGRATE_TIMEOUT_SECONDS,
        "running bench migrate",
        env_overrides=_compose_environment(descriptor),
    )

    report("Verifying health")
    await_health(descriptor, report=report)


def await_health(
    descriptor: Descriptor, *, report: Callable[[str], None] = lambda message: None
) -> None:
    """Wait for the stack to become healthy, or raise (`BR-DEPLOY-017`, `BR-DEPLOY-018`).

    Polls until the timeout and then **halts and reports**. It does not roll back: the
    schema has already been migrated, and undoing the image without undoing the migration
    would leave a combination nobody has tested (`ADR-025`).
    """
    deadline = time.monotonic() + descriptor.health.timeout_seconds
    last = "the stack did not report itself healthy"

    while time.monotonic() < deadline:
        if stack_is_up(descriptor):
            if descriptor.health.url is None:
                report("  containers are up")
                return
            ok, last = _site_answers(descriptor)
            if ok:
                report(f"  {descriptor.health.url} answered")
                return
        time.sleep(descriptor.health.interval_seconds)

    raise ReconcileError(
        f"'{descriptor.environment}' did not become healthy within "
        f"{descriptor.health.timeout_seconds}s — {last}. The new image is running and the "
        f"migration has already been applied, so cairn has stopped rather than guessing. "
        f"Inspect the stack with `docker compose ps` and the logs with `docker compose logs`."
    )


# --- reading actual state ---------------------------------------------------


def running_digest(descriptor: Descriptor) -> str | None:
    """Return the registry digest of the image this host holds for the watched tag.

    Read from the local image's ``RepoDigests``, which is the registry's own name for the
    content — the only thing comparable with what the registry reports. ``None`` means the
    image was never pulled, which is the normal state before a first deploy.
    """
    result = _capture(
        ["docker", "image", "inspect", descriptor.reference, "--format", "{{json .RepoDigests}}"]
    )
    if result is None:
        return None
    try:
        digests = json.loads(result)
    except json.JSONDecodeError:
        return None
    if not isinstance(digests, list):
        return None

    for entry in digests:
        if isinstance(entry, str) and entry.startswith(f"{descriptor.repository}@"):
            return entry.partition("@")[2]
    return None


def stack_is_up(descriptor: Descriptor) -> bool:
    """Whether the stack's bench service is running.

    Asked of the service that serves the site rather than of the project as a whole: a
    project with only its database up is not a running deployment.
    """
    output = _capture(_compose_command(descriptor, ["ps", "--format", "json"]))
    if not output:
        return False

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        # Compose emits either one object per line or a single JSON array, by version.
        for service in entry if isinstance(entry, list) else [entry]:
            if not isinstance(service, dict):
                continue
            if service.get("Service") == BENCH_SERVICE and service.get("State") == "running":
                return True
    return False


def _site_answers(descriptor: Descriptor) -> tuple[bool, str]:
    """Fetch the health URL from inside the stack, returning (ok, why not).

    From inside deliberately: the URL is how the *site* answers, and probing it from the host
    would test the proxy and DNS as well, turning an unrelated outage into a failed deploy.
    """
    url = descriptor.health.url or ""
    probe = ["curl", "-fsS", "-o", "/dev/null", url]
    result = _try(
        _compose_command(descriptor, ["exec", "-T", BENCH_SERVICE, *probe]),
        PROBE_TIMEOUT_SECONDS,
    )
    if result is None:
        return False, f"{url} could not be reached from inside the stack"
    if result.returncode != 0:
        return False, f"{url} returned no successful response"
    return True, ""


# --- compose plumbing -------------------------------------------------------


def _compose_command(descriptor: Descriptor, arguments: list[str]) -> list[str]:
    """Build a ``docker compose`` invocation for this descriptor (`BR-DEPLOY-010`).

    The stack is **rendered**, not stored: the base compose file plus the overrides the
    descriptor selects, layered in the order it lists them. Nothing is written to disk, so
    there is no generated file to drift from the descriptor.
    """
    command = ["docker", "compose"]
    directory = descriptor.compose.directory

    if descriptor.compose.project:
        command += ["--project-name", descriptor.compose.project]
    if descriptor.compose.env_file:
        command += ["--env-file", str(descriptor.compose.env_file)]

    if directory is not None:
        command += ["--project-directory", str(directory)]
        command += ["--file", str(directory / descriptor.compose.file)]
        for name in descriptor.compose.overrides:
            command += ["--file", str(directory / "overrides" / f"compose.{name}.yaml")]

    return command + arguments


def _compose_environment(descriptor: Descriptor) -> dict[str, str]:
    """The variables frappe_docker's compose files read (`BR-DEPLOY-003`).

    ``PULL_POLICY=missing`` because cairn has already pulled deliberately and knows the
    digest it pulled; letting compose pull again would reintroduce the ambiguity the explicit
    pull removed.
    """
    return {
        "CUSTOM_IMAGE": descriptor.repository,
        "CUSTOM_TAG": descriptor.tag,
        "PULL_POLICY": "missing",
        "SITES": f"`{descriptor.site}`",
    }


def _would_do(state: State) -> str:
    """Describe the pass a ``--dry-run`` declined to perform (`BR-CLI-011`)."""
    if state.is_first_deploy:
        return (
            f"Would pull {state.desired_digest}, start the stack, migrate, and verify health "
            f"— this host holds no image for that tag yet."
        )
    if state.running_digest != state.desired_digest:
        return (
            f"Would replace {state.running_digest} with {state.desired_digest}: pull, "
            f"recreate the stack in place, migrate, and verify health."
        )
    return "Would start the stack: the desired image is already here, but nothing is running."


# --- process plumbing -------------------------------------------------------


@contextmanager
def _single_flight(*, dry_run: bool) -> Iterator[None]:
    """Hold the reconcile lock for the enclosed block (`BR-DEPLOY-016`).

    A read-only pass takes no lock: `--dry-run` writes nothing, and refusing to *look* while
    a deploy runs would make the one command an operator reaches for during a deploy the one
    command that will not answer.
    """
    if dry_run:
        yield
        return

    try:
        LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
        handle = LOCK_PATH.open("w")
    except OSError as exc:
        raise ReconcileError(
            f"Cannot create the reconcile lock at {LOCK_PATH} ({exc.strerror}). cairn will "
            f"not deploy without it, because two passes at once would race."
        ) from exc

    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise ReconcileError(
                "Another reconcile is already running on this host, so this pass is stopping. "
                "Nothing was changed; the timer will try again."
            ) from exc
        yield
    finally:
        handle.close()


def _run(
    command: list[str],
    timeout: int,
    what: str,
    *,
    env_overrides: dict[str, str] | None = None,
) -> None:
    """Run *command*, streaming its output, and raise :class:`ReconcileError` on failure."""
    result = _try(command, timeout, env_overrides=env_overrides)
    if result is None:
        raise ReconcileError(
            f"`{command[0]}` is not available on this host, so {what} is impossible. A target "
            f"needs Docker and the Compose plugin; `cairn doctor` checks for both."
        )
    if result.returncode != 0:
        raise ReconcileError(
            f"Failed while {what} (exit code {result.returncode}). cairn has stopped and "
            f"changed nothing further — it does not roll back on its own. The command was:\n"
            f"  {' '.join(command)}"
        )


def _try(
    command: list[str], timeout: int, *, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str] | None:
    """Run *command*, returning None if the binary is missing or it timed out."""
    environment = {**os.environ, **(env_overrides or {})}
    try:
        return subprocess.run(
            command, timeout=timeout, check=False, text=True, env=environment
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def _capture(command: list[str]) -> str | None:
    """Run a short informational command, returning its stdout or None if it failed."""
    try:
        result = subprocess.run(
            command,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            capture_output=True,
            text=True,
            env=os.environ.copy(),
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None
