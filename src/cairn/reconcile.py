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

from . import deploy_record, hold, registry
from .descriptor import Descriptor
from .errors import ReconcileError, RegistryError
from .tagging import ADOPT_OWNED_TAG

#: Where the single-flight lock lives. ``/run`` is tmpfs, so the lock cannot outlive a boot.
LOCK_PATH = Path("/run/cairn/reconcile.lock")

#: Worker containers already sent SIGTERM. A second SIGTERM is RQ's cold shutdown, which kills
#: the job the worker is finishing, so a container listed here is never signalled again.
DRAINED_PATH = Path("/run/cairn/drained-workers")

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

#: The services that answer traffic, in the order a hot swap starts their replacements
#: (`BR-DEPLOY-025`). `frontend` is last because its nginx resolves `backend` once, when it
#: starts: it must start after the new backend exists.
WEB_SERVICES = ("backend", "websocket", "frontend")

#: The order a hot swap retires the old web containers. The old frontend goes first so no new
#: request reaches the old backend through it.
RETIRE_ORDER = ("frontend", "backend", "websocket")

#: frappe_docker's one-shot service that writes `common_site_config.json` and `apps.txt`.
CONFIGURATOR_SERVICE = "configurator"

#: Where frappe_docker's image keeps the bench's apps, for comparing two images' app lists.
APPS_DIRECTORY = "/home/frappe/frappe-bench/apps"

#: Seconds an old container gets to finish in-flight work before Docker kills it. Gunicorn's
#: own graceful timeout is 30 seconds (`ADR-081`).
STOP_GRACE_SECONDS = 30

#: Shorter graces for services whose only long work is an open websocket. The browser reconnects
#: a dropped socket by itself, and waiting out 30 seconds for each held every swap a minute longer.
STOP_GRACE_BY_SERVICE = {"frontend": 5, "websocket": 5}

#: The one service of the remaining image services that must never run twice: two schedulers
#: would enqueue every scheduled job twice.
SCHEDULER_SERVICE = "scheduler"

#: Where frappe_docker's image keeps the bench, and the built files the frontend serves:
#: each app's hashed bundles, and the bench-level asset folders.
BENCH_DIRECTORY = "/home/frappe/frappe-bench"
ASSET_GLOBS = "apps/*/*/public/dist assets/js assets/css"

#: The nginx site file frappe_docker's frontend renders at start, and its two upstreams, keyed by
#: the service each one reaches.
NGINX_SITE = "/etc/nginx/conf.d/frappe.conf"
NGINX_UPSTREAMS = {"backend": "backend-server", "websocket": "socketio-server"}

#: Carried asset files older than this are dropped, unless the new image ships them itself.
ASSET_RETENTION_MINUTES = 24 * 60

#: What `bench migrate` reads: schema JSON and fixtures, patch lists, hooks, and the YAML and
#: CSV some apps sync on migrate, inside each app's package (the folder holding hooks.py). Files
#: outside it, such as CI workflows, never reach migrate. Two images with the same hash of these
#: files need no migrate.
SCHEMA_FINGERPRINT_SCRIPT = (
    f"cd {APPS_DIRECTORY} && find $(dirname */*/hooks.py) \\( -name node_modules -o -name public "
    "\\) -prune -o -type f \\( -name '*.json' -o -name '*.yaml' -o -name '*.yml' -o -name '*.csv' "
    "-o -name patches.txt -o -name hooks.py \\) -print | LC_ALL=C sort | xargs -d '\\n' sha256sum "
    "| sha256sum | cut -d' ' -f1"
)


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
    state: State | None
    detail: str
    #: True when a hold stopped the pass before it began (`BR-DEPLOY-024`). Distinct from both
    #: converged and failed — that third state is the whole reason the hold exists.
    held: bool = False


@dataclass(frozen=True)
class SwapPlan:
    """What a hot swap replaces, read from the rendered compose file (`BR-DEPLOY-025`)."""

    #: Web services present in this stack, in start order.
    web: tuple[str, ...]
    #: Every other service that runs the watched image, except the configurator. These are
    #: recreated in place once the web tier has moved.
    others: tuple[str, ...]


@contextmanager
def single_flight(*, dry_run: bool = False) -> Iterator[None]:
    """The deploy lock, for callers that must hold it across more than one step.

    `BR-CLI-029`'s lifecycle verbs clear a hold, stop the stack and reconcile as one
    indivisible command, so they take the lock themselves and then call :func:`run_locked`.
    They MUST NOT call :func:`run`, which acquires the lock again — a second ``flock`` on a
    fresh descriptor blocks against the process's own lock, and the command hangs forever
    against itself.
    """
    with _single_flight(dry_run=dry_run):
        yield


def run(
    descriptor: Descriptor,
    *,
    dry_run: bool = False,
    report: Callable[[str], None] = lambda message: None,
    on_record: Callable[[str], None] = lambda line: None,
) -> Outcome:
    """Converge the host, or report why it did not (`BR-CLI-008`).

    Held under the single-flight lock for the whole pass, including the registry read: two
    passes reading the same tag and then racing to `compose up` is the failure the lock
    exists to prevent, not merely two overlapping pulls.

    A held host (`BR-DEPLOY-024`) is reported and converges nothing. Checked *before* the
    lock: a held host should answer immediately rather than queue behind a deploy that is
    already running, since its answer does not depend on that deploy's outcome.
    """
    note = hold.describe()
    if note is not None:
        return Outcome(
            converged=False,
            changed=False,
            held=True,
            state=None,
            detail=f"Held — converging nothing. {note}",
        )

    with _single_flight(dry_run=dry_run):
        return run_locked(descriptor, dry_run=dry_run, report=report, on_record=on_record)


def run_locked(
    descriptor: Descriptor,
    *,
    dry_run: bool = False,
    report: Callable[[str], None] = lambda message: None,
    on_record: Callable[[str], None] = lambda line: None,
) -> Outcome:
    """A reconcile pass, assuming the caller already holds the lock (`BR-CLI-029`).

    Split out of :func:`run` so a lifecycle verb can take the lock once and perform several
    steps under it. Never acquires the lock itself; calling it unlocked is a caller error.

    A pass that converges hands one deploy record line to *on_record* as its last act, whether
    it succeeded or failed (`BR-DEPLOY-026`). A converged or dry-run pass hands none.
    """
    state = inspect(descriptor, report=report)

    if state.is_converged:
        mark_owned(descriptor)
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
            detail=_would_do(state, hot_swap=_will_hot_swap(descriptor, state)),
        )

    record = deploy_record.Record(
        environment=descriptor.environment,
        replaced=state.running_digest,
        enabled=state.desired_digest,
    )
    probe = _start_probe(descriptor, report=report)
    try:
        converge(descriptor, state, report=report, record=record)
    except BaseException as exc:
        record.failed(exc)
        raise
    finally:
        if probe is not None:
            record.probe = _stop_probe(probe, report=report)
        _emit(record, on_record, report=report)
    mark_owned(descriptor)
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
    record: deploy_record.Record | None = None,
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
    record = record if record is not None else deploy_record.Record()

    report(f"Pulling {reference}")
    with record.step("pull"):
        _run(["docker", "pull", reference], PULL_TIMEOUT_SECONDS, "pulling the image")

    if _will_hot_swap(descriptor, state):
        plan = plan_hot_swap(descriptor, report=report)
        if plan is not None:
            record.path = "hot-swap"
            hot_swap(descriptor, plan, report=report, record=record)
            report("Verifying health")
            with record.step("health"):
                await_health(descriptor, report=report)
            return
        record.path_note = (
            "the new image's apps differ from the running image's, or could not be read"
        )
    elif descriptor.deploy.hot_swap:
        record.path_note = "first deploy" if state.is_first_deploy else "the stack was not running"

    record.path = "recreate"
    report("Starting the stack")
    with record.step("start"):
        compose_run(
            descriptor,
            ["up", "-d", "--remove-orphans"],
            COMPOSE_TIMEOUT_SECONDS,
            "starting the stack",
        )

    # After every image enable, rollback included (BR-DEPLOY-016). Frappe owns the schema;
    # cairn only asks for the migration it already documents as the sole DB touch.
    report(f"Migrating {descriptor.site}")
    record.migrated = True
    with record.step("migrate"):
        compose_run(
            descriptor,
            ["exec", "-T", BENCH_SERVICE, "bench", "--site", descriptor.site, "migrate"],
            MIGRATE_TIMEOUT_SECONDS,
            "running bench migrate",
        )
    record.tables = touched_tables(descriptor)
    with record.step("finish"):
        drop_asset_map(descriptor, report=report)

    report("Verifying health")
    with record.step("health"):
        await_health(descriptor, report=report)


def _will_hot_swap(descriptor: Descriptor, state: State) -> bool:
    """Whether this pass may hot swap (`BR-DEPLOY-025`).

    Only a running stack has anything to keep serving. A first deploy, or a stack that is
    down, takes the recreate path whatever the descriptor says.
    """
    return descriptor.deploy.hot_swap and state.stack_up and not state.is_first_deploy


def plan_hot_swap(
    descriptor: Descriptor, *, report: Callable[[str], None] = lambda message: None
) -> SwapPlan | None:
    """Check the stack can be hot swapped, before anything changes (`BR-DEPLOY-025`).

    Raises when the compose file makes a second web container impossible: a published host
    port or a fixed ``container_name`` would collide the moment a service scales to two. That
    is a descriptor/compose mismatch the operator must fix, so it halts rather than silently
    taking the recreate path the operator opted out of.

    Returns ``None`` when the new image carries a different app list from the running one.
    ``apps.txt`` lives in the shared sites volume, and old and new code would read one file
    that matches only one of them. Installing or removing an app is the operator's act
    (`BR-DEPLOY-003a`), so that pass takes the recreate path and says why.
    """
    rendered = _compose_capture(descriptor, ["config", "--format", "json"])
    try:
        services = json.loads(rendered or "")["services"]
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ReconcileError(
            "Cannot read the rendered compose file, so a hot swap cannot check that its web "
            "services can run twice. Nothing was changed."
        ) from exc

    if BENCH_SERVICE not in services:
        raise ReconcileError(
            f"The compose file has no '{BENCH_SERVICE}' service, so there is nothing to hot "
            f"swap. Nothing was changed."
        )

    web = tuple(name for name in WEB_SERVICES if name in services)
    for name in web:
        service = services[name] or {}
        if service.get("ports") or service.get("container_name"):
            raise ReconcileError(
                f"The '{name}' service publishes a host port or sets container_name, so a "
                f"second '{name}' container cannot start beside the first. Remove it from the "
                f"compose file, or set the deploy strategy back to recreate. Nothing was changed."
            )

    others = tuple(
        name
        for name, service in services.items()
        if name not in web
        and name != CONFIGURATOR_SERVICE
        and (service or {}).get("image") == descriptor.reference
    )

    running = running_image_id(descriptor)
    old_apps = _app_list(running) if running else None
    new_apps = _app_list(descriptor.reference)
    if old_apps is None or new_apps is None or old_apps != new_apps:
        report(
            "  the new image's apps differ from the running image's (or could not be read), "
            "so this pass recreates the stack in place instead"
        )
        return None

    return SwapPlan(web=web, others=others)


def hot_swap(
    descriptor: Descriptor,
    plan: SwapPlan,
    *,
    report: Callable[[str], None] = lambda message: None,
    record: deploy_record.Record | None = None,
) -> None:
    """Migrate from the new image, then replace the web tier side by side (`BR-DEPLOY-025`).

    The order, and why (`ADR-081`):

    1. the configurator and ``bench migrate`` run in one-off containers of the **new** image
       while the old stack keeps serving. Migration still follows every image enable
       (`BR-DEPLOY-016`); it now happens before the new code takes traffic, against the code
       that needs it, and the old code meets a schema that only gained objects
       (`ADR-014`);
    2. each web service gets one new container beside its old ones, and the pass waits for
       it to answer before starting the next;
    3. the old containers are stopped gracefully; the new frontend's nginx reloads as soon
       as the old backend is gone, so it stops addressing it; the remaining image services
       (workers, scheduler) are recreated in place.

    A candidate that never becomes healthy is removed, with every candidate started before
    it, and the pass halts (`BR-DEPLOY-018`). The old containers never stopped, so the site
    keeps serving the old code. That is not a rollback: the image was never enabled, and the
    migration is not undone.
    """
    site = descriptor.site
    record = record if record is not None else deploy_record.Record()
    remove_drained_workers(descriptor, plan)

    report("Running the configurator from the new image")
    with record.step("configurator"):
        compose_run(
            descriptor,
            ["run", "--rm", "--no-deps", "-T", CONFIGURATOR_SERVICE],
            COMPOSE_TIMEOUT_SECONDS,
            "running the configurator",
        )

    with record.step("fingerprint"):
        running = running_image_id(descriptor)
        old_schema = schema_fingerprint(running) if running else None
        migrate = old_schema is None or old_schema != schema_fingerprint(descriptor.reference)
    record.migrated = migrate
    if migrate:
        report(f"Migrating {site} from the new image while the running stack keeps serving")
        with record.step("migrate"):
            compose_run(
                descriptor,
                [
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    BENCH_SERVICE,
                    "bench",
                    "--site",
                    site,
                    "migrate",
                ],
                MIGRATE_TIMEOUT_SECONDS,
                "running bench migrate",
            )
        record.tables = touched_tables(descriptor)
    else:
        report(f"The schema files match the running image's, so {site} needs no migrate")

    old: dict[str, list[str]] = {}
    with record.step("web"):
        _start_web(descriptor, plan, old, report=report)

    with record.step("retire"):
        _retire_web(descriptor, plan, old, report=report)

    with record.step("workers"):
        _replace_workers(descriptor, plan, report=report)

    with record.step("finish"):
        if not migrate:
            # Migrate clears Frappe's caches. Without it, values cached by the old code stay.
            bench(descriptor, ["clear-cache"], "clearing the cache", report=report)
        # Frappe sends this at the end of migrate, before the new code serves. Sent again now
        # so open tabs check their version against the code that actually answers them.
        bench(
            descriptor,
            ["execute", "frappe.publish_realtime", "--kwargs", '{"event": "version-update"}'],
            "telling open tabs a new version is live",
            report=report,
            required=False,
        )


def _start_web(
    descriptor: Descriptor,
    plan: SwapPlan,
    old: dict[str, list[str]],
    *,
    report: Callable[[str], None],
) -> None:
    """Start one new container beside each old web service, each answering before the next.

    Fills *old* with the containers each service had before, for :func:`_retire_web`.
    """
    started: list[str] = []
    for service in plan.web:
        old[service] = container_ids(descriptor, service)
        report(f"Starting a new {service} beside the running one")
        try:
            compose_run(
                descriptor,
                [
                    "up",
                    "-d",
                    "--no-deps",
                    "--no-recreate",
                    "--scale",
                    f"{service}={len(old[service]) + 1}",
                    service,
                ],
                COMPOSE_TIMEOUT_SECONDS,
                f"starting a new {service}",
            )
            fresh = [cid for cid in container_ids(descriptor, service) if cid not in old[service]]
            started += fresh
            if len(fresh) != 1:
                raise ReconcileError(
                    f"Expected one new {service} container and found {len(fresh)}."
                )
            url = descriptor.health.url if service == BENCH_SERVICE else None
            _await_container(descriptor, fresh[0], url, service, report=report)
        except ReconcileError as exc:
            for candidate in started:
                _try(["docker", "rm", "-f", candidate], PROBE_TIMEOUT_SECONDS)
            raise ReconcileError(
                f"{exc} The new containers were removed and the old ones never stopped, so "
                f"the site is still serving the old code. The migration has already been "
                f"applied and is not undone."
            ) from exc


def _retire_web(
    descriptor: Descriptor,
    plan: SwapPlan,
    old: dict[str, list[str]],
    *,
    report: Callable[[str], None],
) -> None:
    """Hand the old frontend's assets to the new one, then retire the old web containers."""
    if "frontend" in plan.web:
        for new_frontend in [
            c for c in container_ids(descriptor, "frontend") if c not in old["frontend"]
        ]:
            for old_frontend in old["frontend"]:
                carry_assets(old_frontend, new_frontend, report=report)

    for service in RETIRE_ORDER:
        if service == "backend" and "frontend" in plan.web:
            pin_frontends(descriptor, old, report=report)
        for cid in old.get(service, []):
            report(f"Retiring the old {service} ({cid[:12]})")
            if service == "frontend":
                # Graceful quit first. In images whose entrypoint starts nginx without `exec`,
                # bash is PID 1 and drops Docker's stop signal, so `docker stop` waits out the
                # grace and kills nginx mid-request. Found live 2026-11-17 (`BR-DEPLOY-025`).
                _try(["docker", "exec", cid, "nginx", "-s", "quit"], PROBE_TIMEOUT_SECONDS)
            grace = STOP_GRACE_BY_SERVICE.get(service, STOP_GRACE_SECONDS)
            _run(
                ["docker", "stop", "-t", str(grace), cid],
                grace + PROBE_TIMEOUT_SECONDS,
                f"stopping the old {service}",
            )
            _run(["docker", "rm", cid], PROBE_TIMEOUT_SECONDS, f"removing the old {service}")
        # Straight after the old backend goes, not at the end: its address no longer exists,
        # so the new nginx's connections to it hang until the connect timeout rather than
        # failing over. Reloading after the websocket step left a 30 second window of hung
        # requests on Life Scientific's production target, 2026-11-17 (`BR-DEPLOY-025`).
        if service == "backend" and "frontend" in plan.web:
            for cid in container_ids(descriptor, "frontend"):
                _run(
                    ["docker", "exec", cid, "nginx", "-s", "reload"],
                    PROBE_TIMEOUT_SECONDS,
                    "reloading the frontend",
                )
        if service == "backend":
            drop_asset_map(descriptor, report=report)


def _replace_workers(
    descriptor: Descriptor, plan: SwapPlan, *, report: Callable[[str], None]
) -> None:
    """Start new workers beside the old, drain the old ones, then recreate the scheduler."""
    workers = [name for name in plan.others if name != SCHEDULER_SERVICE]
    drained = _read_drained()
    for service in workers:
        draining = container_ids(descriptor, service)
        report(f"Starting a new {service} beside the running one")
        compose_run(
            descriptor,
            [
                "up",
                "-d",
                "--no-deps",
                "--no-recreate",
                "--scale",
                f"{service}={len(draining) + 1}",
                service,
            ],
            COMPOSE_TIMEOUT_SECONDS,
            f"starting a new {service}",
        )
        # SIGTERM is RQ's warm shutdown: the worker takes no new job, finishes the one it has,
        # and exits. `docker stop` would kill a long job when its grace ran out. The exited
        # container is removed at the start of the next hot swap.
        for cid in draining:
            if cid in drained:
                continue
            report(f"Draining the old {service} ({cid[:12]})")
            _try(["docker", "kill", "--signal", "SIGTERM", cid], PROBE_TIMEOUT_SECONDS)
            drained.add(cid)
    _write_drained(drained)

    if SCHEDULER_SERVICE in plan.others:
        report(f"Recreating {SCHEDULER_SERVICE}")
        compose_run(
            descriptor,
            ["up", "-d", "--no-deps", SCHEDULER_SERVICE],
            COMPOSE_TIMEOUT_SECONDS,
            f"recreating {SCHEDULER_SERVICE}",
        )


def pin_frontends(
    descriptor: Descriptor,
    old: dict[str, list[str]],
    *,
    report: Callable[[str], None] = lambda message: None,
) -> None:
    """Point the new frontends' nginx at the new backend and websocket by container name.

    nginx resolves ``backend`` once, when it starts or reloads, and during a swap that name
    answers with the old container too. Once the old container stops, its address no longer
    answers at all, so a request nginx routes there hangs until the connect timeout. One such
    request was seen on Life Scientific's staging target, 2026-11-17. A container name resolves
    to that container only, and survives its restarts. The next deploy's frontend renders its
    file from the template again. Best effort: without the pin, the reload after the old
    backend stops still recovers.
    """
    edits = []
    for service, upstream in NGINX_UPSTREAMS.items():
        fresh = [
            cid for cid in container_ids(descriptor, service) if cid not in old.get(service, [])
        ]
        name = _first_line(_capture(["docker", "inspect", "--format", "{{.Name}}", *fresh[:1]]))
        if len(fresh) != 1 or name is None:
            continue
        edits.append(
            f"sed -i '/upstream {upstream} {{/,/}}/ s/server [^:;]*:/server {name.lstrip('/')}:/' "
            f"{NGINX_SITE}"
        )
    if not edits:
        return
    for cid in [
        c for c in container_ids(descriptor, "frontend") if c not in old.get("frontend", [])
    ]:
        report(f"Pointing the new frontend ({cid[:12]}) at the new backend and websocket")
        result = _try(
            ["docker", "exec", cid, "sh", "-c", " && ".join([*edits, "nginx -s reload"])],
            PROBE_TIMEOUT_SECONDS,
        )
        if result is None or result.returncode != 0:
            report("  could not; requests may wait on the old backend until it is gone")


def schema_fingerprint(image: str) -> str | None:
    """Hash the files `bench migrate` reads in *image*, or None if they could not be read."""
    output = _capture(
        ["docker", "run", "--rm", "--entrypoint", "sh", image, "-c", SCHEMA_FINGERPRINT_SCRIPT]
    )
    value = (output or "").strip()
    return value if len(value) == 64 else None


def carry_assets(
    old: str, new: str, *, report: Callable[[str], None] = lambda message: None
) -> None:
    """Copy the old frontend's built files into the new one, without replacing any.

    Bundle names carry a content hash. A tab opened before the swap still asks for its own
    bundles, which only the old image has, so without this copy they answer 404 once the old
    frontend retires. Files carried from earlier deploys come along too, and those older than
    ``ASSET_RETENTION_MINUTES`` are dropped unless the new image ships them. Best effort: a
    failure costs old tabs a refresh, not the deploy.
    """
    report(f"Carrying the old frontend's asset files into the new one ({new[:12]})")
    own = "/tmp/cairn-own-assets"
    keep = (
        f"cd {BENCH_DIRECTORY} && find {ASSET_GLOBS} -type f > {own} 2>/dev/null; "
        f"tar -xf - --skip-old-files && "
        f"find {ASSET_GLOBS} -type f -mmin +{ASSET_RETENTION_MINUTES} 2>/dev/null "
        f"| grep -vxF -f {own} | xargs -r -d '\\n' rm -f"
    )
    send = f"cd {BENCH_DIRECTORY} && tar -cf - {ASSET_GLOBS} 2>/dev/null"
    result = _try(
        ["sh", "-c", f"docker exec {old} sh -c '{send}' | docker exec -i {new} sh -c \"{keep}\""],
        COMPOSE_TIMEOUT_SECONDS,
    )
    if result is None or result.returncode != 0:
        report(
            "  could not carry the asset files; tabs opened before this deploy may need a refresh"
        )


def _read_drained() -> set[str]:
    try:
        return set(DRAINED_PATH.read_text().split())
    except OSError:
        return set()


def _write_drained(ids: set[str]) -> None:
    try:
        DRAINED_PATH.parent.mkdir(parents=True, exist_ok=True)
        DRAINED_PATH.write_text("\n".join(sorted(ids)))
    except OSError:
        pass


def remove_drained_workers(descriptor: Descriptor, plan: SwapPlan) -> None:
    """Remove worker containers that a previous swap drained and that have since exited."""
    for service in plan.others:
        output = (
            _compose_capture(descriptor, ["ps", "-a", "-q", "--status", "exited", service]) or ""
        )
        for cid in (line.strip() for line in output.splitlines()):
            if cid:
                _try(["docker", "rm", cid], PROBE_TIMEOUT_SECONDS)


def bench(
    descriptor: Descriptor,
    arguments: list[str],
    what: str,
    *,
    report: Callable[[str], None] = lambda message: None,
    required: bool = True,
) -> None:
    """Run a bench command for the site in the running backend."""
    command = ["exec", "-T", BENCH_SERVICE, "bench", "--site", descriptor.site, *arguments]
    if required:
        report(what[0].upper() + what[1:])
        compose_run(descriptor, command, PROBE_TIMEOUT_SECONDS, what)
        return
    result = _compose_try(descriptor, command, PROBE_TIMEOUT_SECONDS)
    if result is None or result.returncode != 0:
        report(f"  could not finish {what}")


def container_ids(descriptor: Descriptor, service: str) -> list[str]:
    """The ids of *service*'s containers in this project, in compose's order."""
    output = _compose_capture(descriptor, ["ps", "-q", service]) or ""
    return [line.strip() for line in output.splitlines() if line.strip()]


def _app_list(image: str) -> list[str] | None:
    """The apps baked into *image*, sorted, or None if they could not be read."""
    output = _capture(["docker", "run", "--rm", "--entrypoint", "ls", image, APPS_DIRECTORY])
    if output is None:
        return None
    return sorted(line.strip() for line in output.splitlines() if line.strip())


def _await_container(
    descriptor: Descriptor,
    container_id: str,
    url: str | None,
    service: str,
    *,
    report: Callable[[str], None] = lambda message: None,
) -> None:
    """Wait for one new container to run, pass its own healthcheck, and answer *url*.

    Asked of the container itself, not of the service: during a swap the service name
    resolves to the old container as well, and an answer from the old one proves nothing.
    """
    deadline = time.monotonic() + descriptor.health.timeout_seconds
    while time.monotonic() < deadline:
        status = _capture(
            [
                "docker",
                "inspect",
                container_id,
                "--format",
                "{{.State.Running}} {{if .State.Health}}{{.State.Health.Status}}{{end}}",
            ]
        )
        words = (status or "").split()
        ready = bool(words) and words[0] == "true" and words[1:] in ([], ["healthy"])
        if ready and url is not None:
            probe = ["docker", "exec", container_id, *_health_probe(descriptor, url)]
            result = _try(probe, PROBE_TIMEOUT_SECONDS)
            ready = result is not None and result.returncode == 0
        if ready:
            report(f"  the new {service} is ready")
            return
        time.sleep(descriptor.health.interval_seconds)

    raise ReconcileError(
        f"The new {service} did not become ready within {descriptor.health.timeout_seconds}s."
    )


def drop_asset_map(
    descriptor: Descriptor, *, report: Callable[[str], None] = lambda message: None
) -> None:
    """Drop Frappe's cached map of bundle file names after new code is enabled (`BR-DEPLOY-003`).

    With developer mode off, Frappe 16 keeps ``assets.json`` in a shared Redis key with no
    expiry. The image carries new bundle names, the Redis volume survives the deploy, and
    nothing on the target rebuilds assets, so pages keep naming the previous image's files and
    the Desk renders unstyled. During a hot swap the old backend can also write its own map back
    while it still serves, so the key is dropped only once the old backend is gone. Found on
    Life Scientific's staging target, 2026-11-17.

    Cache bookkeeping, not data: the next request rebuilds the key from the running image.
    """
    report("Dropping the cached asset map")
    compose_run(
        descriptor,
        [
            "exec",
            "-T",
            BENCH_SERVICE,
            "bench",
            "--site",
            descriptor.site,
            "execute",
            "frappe.client_cache.delete_value",
            "--args",
            '["assets_json"]',
            "--kwargs",
            '{"shared": True}',
        ],
        PROBE_TIMEOUT_SECONDS,
        "dropping the cached asset map",
    )


def touched_tables(descriptor: Descriptor) -> list[str] | None:
    """The tables Frappe recorded writing during the migrate just run (`BR-DEPLOY-026`).

    Frappe leaves ``touched_tables.json`` in the site folder at the end of every migrate. The
    sites volume is shared, so the running ``backend`` reads what a one-off migrate container
    wrote. Best effort: None when it cannot be read.
    """
    output = _compose_capture(
        descriptor,
        ["exec", "-T", BENCH_SERVICE, "cat", f"sites/{descriptor.site}/touched_tables.json"],
    )
    return deploy_record.parse_tables(output)


def _start_probe(
    descriptor: Descriptor, *, report: Callable[[str], None]
) -> deploy_record.Probe | None:
    """Start the deploy record's probe when the descriptor names a URL (`BR-DEPLOY-026`).

    Observation only: a probe that cannot start is reported, and the pass goes on without it.
    """
    settings = descriptor.record
    if settings.probe_url is None:
        return None
    try:
        return deploy_record.Probe(settings.probe_url, settings.probe_interval_ms).start()
    except Exception as exc:
        report(f"  could not start the deploy probe ({exc}); the record will not include it")
        return None


def _stop_probe(
    probe: deploy_record.Probe, *, report: Callable[[str], None]
) -> dict[str, float | int] | None:
    try:
        return probe.stop()
    except Exception as exc:
        report(f"  could not summarize the deploy probe ({exc})")
        return None


def _emit(
    record: deploy_record.Record,
    on_record: Callable[[str], None],
    *,
    report: Callable[[str], None],
) -> None:
    """Hand the record's line to *on_record*. A failure here never fails the pass."""
    try:
        on_record(record.line())
    except Exception as exc:
        report(f"  could not print the deploy record ({exc})")


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


def running_image_id(descriptor: Descriptor) -> str | None:
    """Return the local image id backing the running `backend` container, or ``None``.

    The one place that reads which image is *actually* running, as opposed to merely
    pulled — shared by :func:`running_digest` (`BR-DEPLOY-003b`) and :func:`mark_owned`
    (`BR-DEPLOY-023`), so both ask the engine the same question the same way.
    """
    container_id = _first_line(_compose_capture(descriptor, ["ps", "-q", BENCH_SERVICE]))
    if container_id is None:
        return None

    return _first_line(_capture(["docker", "inspect", container_id, "--format", "{{.Image}}"]))


def mark_owned(descriptor: Descriptor) -> None:
    """Tag the currently-running image as `cairn-adopt`'s own (`BR-DEPLOY-023`, `ADR-072`).

    Called on **every** `reconcile` pass, converged or not (see :func:`run`) — refreshing on
    a no-op, not only on a pull, is what lets a host already running an image pulled before
    this feature existed pick up the marker on its very next pass, with no manual step. The
    marker is never removed here; only `cairn-adopt prune` (`BR-CLI-028`) releases it.

    Best-effort and silent on failure: the image is already running correctly regardless of
    whether this bookkeeping tag attaches, and a tagging hiccup must not be mistaken for a
    convergence failure.
    """
    image_id = running_image_id(descriptor)
    if image_id is None:
        return
    _try(
        ["docker", "tag", image_id, f"{descriptor.repository}:{ADOPT_OWNED_TAG}"],
        PROBE_TIMEOUT_SECONDS,
    )


def running_digest(descriptor: Descriptor) -> str | None:
    """Return the registry digest of the image the running `backend` container was actually
    started from — not merely whether a matching image exists in the local store
    (`BR-DEPLOY-003b`).

    ``docker compose up`` only recreates a container when its *rendered* service definition
    changes. A compose file that hardcodes ``image:`` per service, rather than
    parameterizing it with ``${CUSTOM_IMAGE}``/``${CUSTOM_TAG}`` (frappe_docker's `pwd.yml`
    quick-start shape, as opposed to its `compose.yaml`), never reacts to those variables at
    all — the desired image can be pulled and sitting in the local store while the running
    container stays completely untouched. Reading the digest off the *container's own* image
    — not asking the store whether a matching image merely exists — is what turns that into a
    loud mismatch instead of a silent false convergence (found live 2026-08-05, `ADR-021`
    fork-pressure register item 4). ``None`` means there is no running container to ask,
    which is the normal state before a first deploy.
    """
    image_id = running_image_id(descriptor)
    if image_id is None:
        return None

    result = _capture(["docker", "image", "inspect", image_id, "--format", "{{json .RepoDigests}}"])
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


def _first_line(output: str | None) -> str | None:
    """Return *output*'s first non-blank line, stripped, or None if there isn't one."""
    if output is None:
        return None
    for line in output.splitlines():
        line = line.strip()
        if line:
            return line
    return None


def stack_is_up(descriptor: Descriptor) -> bool:
    """Whether the stack's bench service is running.

    Asked of the service that serves the site rather than of the project as a whole: a
    project with only its database up is not a running deployment.
    """
    output = _compose_capture(descriptor, ["ps", "--format", "json"])
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


def _health_probe(descriptor: Descriptor, url: str) -> list[str]:
    """The curl command that asks *url* for this descriptor's site (`BR-DEPLOY-017`).

    Frappe picks the site from the ``X-Frappe-Site-Name`` header, else from the Host header,
    and has no default-site fallback. A probe from inside the stack reaches gunicorn as
    ``localhost``, which names no site, so without the header every probe answers 404 and a
    healthy stack can never pass. Found on Life Scientific's production target, 2026-11-17.
    """
    return ["curl", "-fsS", "-o", "/dev/null", "-H", f"X-Frappe-Site-Name: {descriptor.site}", url]


def _site_answers(descriptor: Descriptor) -> tuple[bool, str]:
    """Fetch the health URL from inside the stack, returning (ok, why not).

    From inside deliberately: the URL is how the *site* answers, and probing it from the host
    would test the proxy and DNS as well, turning an unrelated outage into a failed deploy.
    """
    url = descriptor.health.url or ""
    probe = _health_probe(descriptor, url)
    result = _compose_try(descriptor, ["exec", "-T", BENCH_SERVICE, *probe], PROBE_TIMEOUT_SECONDS)
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


def compose_invocation(
    descriptor: Descriptor, arguments: list[str]
) -> tuple[list[str], dict[str, str]]:
    """The compose command for *arguments*, and the environment it must be run with.

    The public form of the ``_compose_*`` seam, for callers that cannot use it because they do
    not run the command as a child at all — `BR-CLI-030`'s interactive verbs replace the
    process (`ADR-075`). Returns both halves together for the same reason the private helpers
    pair them: a compose invocation without `CUSTOM_IMAGE`/`CUSTOM_TAG` cannot resolve its own
    image reference (`BR-VEND-006`) and fails rather than reports.
    """
    return _compose_command(descriptor, arguments), _compose_environment(descriptor)


def compose_run(descriptor: Descriptor, arguments: list[str], timeout: int, what: str) -> None:
    """Run a compose command, always with the variables its file interpolates.

    The three ``_compose_*`` helpers exist so that building a compose invocation and supplying
    its environment cannot be done separately (`BR-DEPLOY-003b`, `BR-DEPLOY-017`). They were
    added after a live incident: three probes called ``_compose_command`` and then executed the
    result without ``_compose_environment``, which was harmless only for as long as the compose
    file carried a ``:-`` default to absorb the omission. `BR-VEND-006` removed that default by
    design, and the probes went blind — reporting a running stack as stopped. Pairing the two
    here removes the opportunity rather than relying on each caller to remember.
    """
    _run(
        _compose_command(descriptor, arguments),
        timeout,
        what,
        env_overrides=_compose_environment(descriptor),
    )


def _compose_capture(descriptor: Descriptor, arguments: list[str]) -> str | None:
    """Capture a compose command's stdout, always with its environment. See :func:`compose_run`."""
    return _capture(
        _compose_command(descriptor, arguments),
        env_overrides=_compose_environment(descriptor),
    )


def _compose_try(
    descriptor: Descriptor, arguments: list[str], timeout: int
) -> subprocess.CompletedProcess[str] | None:
    """Run a compose command tolerantly, always with its environment. See :func:`compose_run`."""
    return _try(
        _compose_command(descriptor, arguments),
        timeout,
        env_overrides=_compose_environment(descriptor),
    )


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


def _would_do(state: State, *, hot_swap: bool = False) -> str:
    """Describe the pass a ``--dry-run`` declined to perform (`BR-CLI-011`)."""
    if hot_swap:
        return (
            f"Would replace {state.running_digest} with {state.desired_digest}: pull, migrate "
            f"from the new image while the running stack serves, start the new web containers "
            f"beside the old ones, retire the old ones, and verify health. A changed app list "
            f"would recreate the stack in place instead."
        )
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
        return subprocess.run(command, timeout=timeout, check=False, text=True, env=environment)
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return None


def _capture(command: list[str], *, env_overrides: dict[str, str] | None = None) -> str | None:
    """Run a short informational command, returning its stdout or None if it failed.

    ``env_overrides`` is not optional in practice for any ``docker compose`` invocation
    (`BR-DEPLOY-003b`, `BR-DEPLOY-017`): the compose file interpolates `CUSTOM_IMAGE`/
    `CUSTOM_TAG`, and `BR-VEND-006` requires it to *fail* rather than substitute a default
    when they are absent. A read-only probe that omits them therefore exits non-zero and is
    indistinguishable here from a genuinely stopped stack — which is exactly the failure this
    parameter exists to prevent. Only a plain `docker` call (no compose file, no
    interpolation) may safely omit it.
    """
    try:
        result = subprocess.run(
            command,
            timeout=PROBE_TIMEOUT_SECONDS,
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, **(env_overrides or {})},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None
