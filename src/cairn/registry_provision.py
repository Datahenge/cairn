"""Provision and operate the registry role — `cairn-registry setup`/`status`/`start`/`stop`/
`restart` (`BR-REG-003/004`, `ADR-048`).

Migrated wholesale from `provision.py`'s former `"registry"` stage, which used to run only as
part of `cairn-build setup`. Split out because a registry host is provisioned independently of
a build machine (`ADR-048`) — it has its own config (`registry_config.py`), its own retention
policy, and its own timer.

This module MUST NOT import `config.py`, `environments.py`, or `provision.py` itself
(`BR-REG-001`) — the last of those because `provision.py` imports `adopt.py`, which reads
`config.py`. It imports the generic `setup` engine straight from `setup_runner.py`, the same
module `provision.py` now also imports it from, so neither pulls in the other.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from . import registry_config
from .registry_config import RegistryConfig
from .setup_runner import (
    SYSTEMD_DIR,
    Aborted,
    Runner,
    SetupOptions,
    base_preflight_checks,
    check_command,
    fail_on_checks,
    find_executable,
    require_root,
    stage_admin_group,
)

#: The label `examine` (`cairn-adopt`) filters on to recognize cairn's own infrastructure
#: containers. Duplicated from `adopt.py`'s own `CAIRN_MANAGED_LABEL` — a plain, stable string
#: literal, not imported, because `adopt.py` reads `config.py` and this module must not
#: (`BR-REG-001`).
CAIRN_MANAGED_LABEL = "com.datahenge.cairn.managed"

#: The compose project directory — fixed, unlike `data_dir` (`registry_config.py`), which is
#: the operator-configurable bind mount for the registry's actual blobs. This directory only
#: ever holds the compose file and is not where an operator would look for image storage.
#: Split from `CERT_DIR` deliberately, not merely historically — `ADR-053`: config/secrets
#: (low-churn, shared) vs. relocatable bulk data belong in different places.
PROJECT_DIR = Path("/opt/cairn-registry")

CERT_DIR = Path("/etc/cairn")
SYSTEM_CA_DIR = Path("/usr/local/share/ca-certificates")
DOCKER_CERT_DIR = Path("/etc/docker/certs.d")

#: How long the self-signed certificate lasts. 825 days is the longest most clients accept.
CERT_DAYS = 825

#: Group-writable, matching `provision.py`'s constant of the same name and value — duplicated,
#: not imported, since this module must not import `provision.py` (`BR-REG-001`).
SHARED_FILE_MODE = 0o664

#: `cairn-registry setup`'s fixed stage list — no `--role` flag, this binary only ever
#: provisions a registry host (`ADR-046`/`ADR-048`'s "binary invoked is the role signal").
REGISTRY_STAGES = ("preflight", "admin-group", "registry")


def stage_preflight_registry(runner: Runner, options: SetupOptions) -> None:
    """Gate a registry host: base checks, plus openssl (needed to generate the TLS cert)."""
    checks, disk_check = base_preflight_checks(runner, options)
    extra = [check_command(runner, "openssl", ["openssl", "version"])]
    for check in extra:
        runner.say(check.render())
    fail_on_checks(checks + extra, disk_check, options)


def subject_alt_names(private_ip: str | None) -> str:
    """Assemble the certificate's SANs.

    ``localhost`` and ``127.0.0.1`` cover today, when the builder/target and the registry are
    one box. The private IP is included so the certificate survives them splitting — reissuing
    later would mean re-trusting it on every host that already had it.
    """
    names = ["DNS:localhost", "DNS:cairn-registry", "IP:127.0.0.1"]
    if private_ip:
        names.append(f"IP:{private_ip}")
    return ",".join(names)


#: The registry's own config path inside the container — baked into the official image,
#: generated from the `REGISTRY_*` environment variables `registry_compose()` sets.
CONTAINER_CONFIG_PATH = "/etc/docker/registry/config.yml"


def registry_compose(config: RegistryConfig, *, read_only: bool = False) -> str:
    """The registry, bound to *config*'s address/port, able to delete versions.

    ``REGISTRY_STORAGE_DELETE_ENABLED`` is what makes retention (`BR-REG-006`) possible at
    all — the reason hosted registries make retention awkward is that some of them cannot
    delete a single version at all.

    Blobs are bind-mounted at *config*'s ``data_dir`` — an operator-chosen path, never an
    anonymous Docker volume, so image storage can be placed on a specific disk.

    Carries ``CAIRN_MANAGED_LABEL`` so ``cairn-adopt examine`` can recognize this project as
    cairn's own infrastructure and exclude it when auto-detecting a site — by label, never by
    the ``cairn-registry`` project name, which is only ``PROJECT_DIR``'s basename and asserts
    nothing on its own.

    *read_only* is `gc`'s (`BR-REG-009`) maintenance-mode switch: with it set, the registry
    still serves reads (pulls) but refuses writes (pushes) — the documented-safe way to run
    `registry garbage-collect` without a concurrent push corrupting the blob store it is
    walking.
    """
    readonly_line = (
        '\n      REGISTRY_STORAGE_MAINTENANCE_READONLY_ENABLED: "true"' if read_only else ""
    )
    return f"""\
# Written by `cairn-registry setup`. A local OCI registry over self-signed TLS.
services:
  registry:
    image: docker.io/library/registry:2
    restart: unless-stopped
    labels:
      - "{CAIRN_MANAGED_LABEL}=true"
    ports:
      - "{config.bind_address}:{config.port}:{config.port}"
    environment:
      REGISTRY_HTTP_ADDR: 0.0.0.0:{config.port}
      REGISTRY_HTTP_TLS_CERTIFICATE: /certs/registry.crt
      REGISTRY_HTTP_TLS_KEY: /certs/registry.key
      REGISTRY_STORAGE_DELETE_ENABLED: "true"{readonly_line}
    volumes:
      - {CERT_DIR}:/certs:ro
      - {config.data_dir}:/var/lib/registry
"""


def default_config_toml() -> str:
    """A fully-commented starter `/etc/cairn/registry.toml`, written once so an operator
    discovers every configurable key without first having to find `BR-REG-002`.

    Every value shown is `RegistryConfig`'s own default, read back from the dataclass rather
    than duplicated as a second set of literals that could silently drift from it.
    """
    default = RegistryConfig()
    return f"""\
# Written once by `cairn-registry setup`. Edit this file freely for your own registry — cairn
# never overwrites it again once it exists, not even with --force (that flag only ever applies
# to files cairn itself generates and regenerates, like the certificate and compose file).
# After editing, run `cairn-registry setup --force` to apply the change.

[registry]
port = {default.port}
bind_address = "{default.bind_address}"
data_dir = "{default.data_dir}"

[registry.retention]
enabled = {str(default.retention.enabled).lower()}
keep_last = {default.retention.keep_last}
max_age_days = {default.retention.max_age_days}

[registry.gc]
schedule = "{default.gc.schedule}"
"""


def _ensure_default_config(runner: Runner) -> None:
    """Create `registry_config.CONFIG_PATH` with the documented defaults, once.

    Mirrors `provision.py`'s starter-manifest stage: an existing file is never touched,
    `--force` included — once this exists it is the operator's own config, not cairn's to
    manage, and `setup` only ever creates it as a discoverability courtesy the first time
    there is none (`BR-REG-002`).
    """
    path = registry_config.CONFIG_PATH
    if path.exists():
        runner.say(f"    {path} already exists — leaving it")
        runner.report.skipped.append(f"{path} (already present, not modified)")
        return

    runner.say(f"    write {path} (default configuration)")
    if runner.dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(default_config_toml(), encoding="utf-8")
    os.chmod(path, SHARED_FILE_MODE)
    runner.report.done.append(f"created default {path}")


def stage_registry(runner: Runner, options: SetupOptions) -> None:
    """Run a local registry over self-signed TLS, trusted by both Python and Docker.

    TLS rather than plain HTTP so that **cairn needs no change**: its registry client speaks
    https, and both `urllib` and Docker read the system CA store.
    """
    _ensure_default_config(runner)
    config = registry_config.load()
    host = config.host
    crt, key = CERT_DIR / "registry.crt", CERT_DIR / "registry.key"

    cert_renewed = not crt.exists() or options.force
    if cert_renewed:
        if not runner.dry_run:
            CERT_DIR.mkdir(parents=True, exist_ok=True)
        runner.run(
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                str(CERT_DAYS),
                "-keyout",
                str(key),
                "-out",
                str(crt),
                "-subj",
                "/CN=cairn-registry",
                "-addext",
                f"subjectAltName={subject_alt_names(options.private_ip)}",
            ],
            what="generating the registry certificate",
        )
        if not runner.dry_run:
            os.chmod(key, 0o600)  # rule 4: key material is owner-only
            runner.report.done.append(f"generated {crt}")
    else:
        runner.say(f"    {crt} already exists — reusing it")
        runner.report.skipped.append("registry certificate (already present)")

    # Trusted twice, because two consumers read two stores: Python via the system bundle,
    # Docker via its own per-registry directory.
    ca_copy = SYSTEM_CA_DIR / "cairn-registry.crt"
    docker_ca = DOCKER_CERT_DIR / host / "ca.crt"
    if not runner.dry_run and crt.exists():
        content = crt.read_text(encoding="utf-8")
        runner.write(ca_copy, content, what=f"trusted the certificate system-wide ({ca_copy})")
        runner.write(docker_ca, content, what=f"trusted the certificate for Docker ({docker_ca})")
    else:
        runner.say(f"    trust {crt} system-wide as {ca_copy}")
        runner.say(f"    trust {crt} for Docker as {docker_ca}")
    runner.run(["update-ca-certificates"], what="refreshing the system CA bundle")

    if runner.dry_run:
        runner.say(f"    ensure {config.data_dir} exists")
    else:
        config.data_dir.mkdir(parents=True, exist_ok=True)

    runner.write(
        PROJECT_DIR / "compose.yaml",
        registry_compose(config),
        what=f"wrote the registry compose file to {PROJECT_DIR}",
    )
    up_command = compose_command("up", "-d")
    if cert_renewed:
        # An already-running container has the old cert loaded in memory; `up -d` alone
        # would leave it serving a certificate nothing trusts anymore, since the bind-mounted
        # file changing underneath it is invisible to compose's own change detection.
        up_command.append("--force-recreate")
    runner.run(up_command, what="starting the registry")

    if not runner.dry_run:
        probe = runner.probe(["curl", "-fsS", f"https://{host}/v2/"])
        if probe is None:
            raise Aborted(
                f"the registry at https://{host}/v2/ did not answer over TLS. If curl reports a "
                f"certificate problem, the CA was not trusted; check {docker_ca}."
            )
        runner.report.done.append(
            f"registry reachable at https://{host} with a trusted certificate"
        )


def compose_command(*verb: str) -> list[str]:
    """Build a `docker compose --project-directory PROJECT_DIR <verb>` invocation.

    Every registry lifecycle command (`status`/`start`/`stop`/`restart`/`gc`) goes through
    this, so they all address the same compose project `setup` created — by directory, never
    by a project *name* an operator's own project could coincidentally share.
    """
    return ["docker", "compose", "--project-directory", str(PROJECT_DIR), *verb]


def status(runner: Runner) -> str:
    """`cairn-registry status` (`BR-REG-004`) — the compose project's own status line.

    Read-only, so it goes through `probe`, not `run` — safe to call under `--dry-run` too,
    and there is nothing here for a dry run to skip.
    """
    return runner.probe(compose_command("ps")) or "no status available"


def start(runner: Runner) -> None:
    runner.run(compose_command("up", "-d"), what="starting the registry")


def stop(runner: Runner) -> None:
    runner.run(compose_command("stop"), what="stopping the registry")


def restart(runner: Runner) -> None:
    runner.run(compose_command("restart"), what="restarting the registry")


def gc(runner: Runner) -> None:
    """Reclaim blob storage for digests retention has already deleted (`BR-REG-009`).

    The documented-safe sequence: recreate the container in read-only maintenance mode
    (pulls, including `cairn-adopt reconcile`'s polling, are unaffected — only pushes are
    refused for the duration), run the registry's own `garbage-collect` inside it, then
    recreate back to read-write. Reported plainly before running, since it briefly blocks
    pushes — `cli_registry.py`'s `gc` command is what gates this behind `--yes`/`--dry-run`.
    """
    config = registry_config.load()
    runner.report.warnings.append(
        "the registry is briefly read-only during gc — pulls are unaffected, pushes are "
        "refused until it completes"
    )

    _write_compose(runner, config, read_only=True, what="entering read-only maintenance mode")
    runner.run(compose_command("up", "-d", "--force-recreate"), what="recreating in read-only mode")

    runner.run(
        compose_command(
            "exec", "-T", "registry", "registry", "garbage-collect", CONTAINER_CONFIG_PATH
        ),
        what="reclaiming blob storage",
    )

    _write_compose(runner, config, read_only=False, what="returning to read-write mode")
    runner.run(
        compose_command("up", "-d", "--force-recreate"), what="recreating in read-write mode"
    )
    runner.report.done.append("garbage collection complete")


def _write_compose(runner: Runner, config: RegistryConfig, *, read_only: bool, what: str) -> None:
    """Write the compose file unconditionally.

    Unlike every other file `Runner.write` protects (`BR-DEPLOY-021` rule 3), this one is
    entirely cairn-generated — "Written by `cairn-registry setup`", never hand-edited — and
    `gc` must be able to toggle it on every run without an operator-facing `--force` flag to
    pass. `stage_registry` still goes through `runner.write` for the initial write, so a
    config change picked up by re-running `setup` still asks for `--force` there.
    """
    path = PROJECT_DIR / "compose.yaml"
    content = registry_compose(config, read_only=read_only)
    runner.say(f"    write {path} ({what})")
    if runner.dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


#: `cairn-registry setup-timer`'s own stage table — one stage, no `--only` needed, mirroring
#: `BUILD_TIMER_STAGE_FUNCS`/`ADOPT_TIMER_STAGE_FUNCS` (`BR-CLI-023`/`027`, `ADR-047`).
TIMER_STAGES = ("timers",)

MAINTENANCE_UNIT_NAME = "cairn-registry-maintenance"


def maintenance_script(workdir: Path, cairn_registry: Path) -> str:
    """Prune old digests, then reclaim their blob storage.

    Two commands, not one: `prune` (`BR-REG-006`) and `gc` (`BR-REG-009`) are independently
    useful and independently safe to run by hand — this script is only the convenience of
    running them back to back on a schedule.
    """
    return f"""\
#!/bin/bash -e
# Written by `cairn-registry setup-timer`.
cd {workdir}
{cairn_registry} prune --yes
{cairn_registry} gc --yes
"""


def maintenance_service(script: Path) -> str:
    return f"""\
[Unit]
Description=cairn-registry — prune old digests and reclaim their blob storage
After=network-online.target docker.service
Wants=network-online.target
Requires=docker.service

[Service]
Type=oneshot
ExecStart={script}
# A stuck gc (a wedged docker exec) should be visible, not silently hung forever.
TimeoutStartSec=1800

[Install]
WantedBy=multi-user.target
"""


def maintenance_timer(schedule: str) -> str:
    """The timer, driven by `[registry.gc] schedule` (`BR-REG-010`) — a systemd
    ``OnCalendar=`` value directly; ``"weekly"``/``"daily"`` are themselves valid syntax."""
    return f"""\
[Unit]
Description=cairn-registry — periodic prune + gc

[Timer]
OnCalendar={schedule}
RandomizedDelaySec=5min
Persistent=true
Unit={MAINTENANCE_UNIT_NAME}.service

[Install]
WantedBy=timers.target
"""


def stage_timers_registry(runner: Runner, options: SetupOptions) -> None:
    """Install the prune+gc timer, enabled but not started (`BR-CLI-027`, `BR-REG-010`).

    Not started deliberately, same reasoning as the build/reconcile timers: the first
    prune/gc pass should be watched by hand before it runs unattended on a schedule.
    `setup-timer` has no preceding `preflight` stage, so this checks root itself.

    The script is written to `PROJECT_DIR`, not `options.workdir` (`ADR-062`, `ADR-063`):
    `options.workdir` defaults to the invoking shell's `cwd`, ordinarily an operator's home
    directory — a retired account could silently take a generated maintenance script down
    with it. `PROJECT_DIR` (`/opt/cairn-registry`) is already this role's durable,
    non-user-specific home for its own installed files (`compose.yaml` lives there too,
    `ADR-053`), reused rather than reinvented. Unlike `cairn-build`'s per-client unit name,
    this role has no naming-collision counterpart to fix — one registry, one host, one fixed
    `MAINTENANCE_UNIT_NAME` (`ADR-048`).
    """
    require_root(runner)
    config = registry_config.load()
    cairn_registry = find_executable("cairn-registry")
    script = PROJECT_DIR / "registry-maintenance.sh"
    runner.write(
        script,
        maintenance_script(options.workdir, cairn_registry),
        mode=0o755,
        what=f"maintenance script at {script}",
    )
    runner.write(
        SYSTEMD_DIR / f"{MAINTENANCE_UNIT_NAME}.service",
        maintenance_service(script),
        what="maintenance service",
    )
    runner.write(
        SYSTEMD_DIR / f"{MAINTENANCE_UNIT_NAME}.timer",
        maintenance_timer(config.gc.schedule),
        what="maintenance timer",
    )

    runner.run(["systemctl", "daemon-reload"], what="reloading systemd")
    runner.run(
        ["systemctl", "enable", f"{MAINTENANCE_UNIT_NAME}.timer"],
        what="enabling the maintenance timer",
    )
    runner.report.warnings.append(
        f"{MAINTENANCE_UNIT_NAME}.timer is enabled but NOT started — run `cairn-registry "
        f"prune`/`gc` by hand first, then `systemctl start {MAINTENANCE_UNIT_NAME}.timer`"
    )


REGISTRY_TIMER_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "timers": stage_timers_registry,
}


REGISTRY_STAGE_FUNCS: dict[str, Callable[[Runner, SetupOptions], None]] = {
    "preflight": stage_preflight_registry,
    "admin-group": stage_admin_group,
    "registry": stage_registry,
}
