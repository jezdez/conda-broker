"""Client API for conda-broker users and provider plugins."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from .exceptions import BrokerNotRunningError, IpcError
from .ipc import call, ping
from .paths import ServicePaths
from .registry import discover_services
from .state import StateStore

if TYPE_CHECKING:
    from typing import Any

    from .models import ServiceEvent


def _paths(paths: ServicePaths | None = None) -> ServicePaths:
    return paths or ServicePaths.resolve()


def broker_running(paths: ServicePaths | None = None) -> bool:
    """Return whether the broker is reachable without starting it."""
    resolved = _paths(paths)
    return ping(resolved.server_file)


def start_broker(
    paths: ServicePaths | None = None,
    *,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Start the broker if needed and wait until it accepts IPC."""
    resolved = _paths(paths)
    resolved.ensure()
    if broker_running(resolved):
        return {"broker": {"running": True, "started": False}}

    env = {
        **os.environ,
        "CONDA_BROKER_RUNTIME_DIR": str(resolved.runtime_dir),
        "CONDA_BROKER_LOG_DIR": str(resolved.log_dir),
    }
    log = resolved.broker_log_file.open("a", encoding="utf-8")
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "conda_broker.broker",
            "--runtime-dir",
            str(resolved.runtime_dir),
            "--log-dir",
            str(resolved.log_dir),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=(os.name != "nt"),
    )
    log.close()

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if broker_running(resolved):
            return {"broker": {"running": True, "started": True}}
        time.sleep(0.1)
    raise BrokerNotRunningError("Timed out waiting for conda-broker broker")


def status(
    service: str | None = None,
    *,
    paths: ServicePaths | None = None,
) -> dict[str, Any]:
    """Return broker and service status without starting the broker."""
    resolved = _paths(paths)
    try:
        return call(
            resolved.server_file,
            "status",
            {"service": service} if service else {},
        )
    except BrokerNotRunningError:
        registry = discover_services()
        state = StateStore(resolved)
        enabled = state.enabled_services()
        services = [
            {
                **registered.to_dict(),
                "enabled": registered.name in enabled,
                "state": "stopped",
                "running": False,
                "pid": None,
                "health": "unknown",
            }
            for registered in registry.all()
            if service is None or registered.name == service
        ]
        return {"broker": {"running": False}, "services": services}


def service_status(
    service: str,
    *,
    paths: ServicePaths | None = None,
) -> dict[str, Any] | None:
    """Return one service status without starting the broker."""
    payload = status(service, paths=paths)
    services = payload.get("services", [])
    if not services:
        return None
    first = services[0]
    return first if isinstance(first, dict) else None


def is_service_running(
    service: str,
    *,
    paths: ServicePaths | None = None,
) -> bool:
    """Return whether *service* is running, without starting the broker."""
    current = service_status(service, paths=paths)
    return bool(current and current.get("running"))


def start(
    services: list[str] | tuple[str, ...] = (),
    *,
    paths: ServicePaths | None = None,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Ensure the broker is running, then start selected services."""
    resolved = _paths(paths)
    broker = start_broker(resolved, timeout_s=timeout_s)["broker"]
    result = call(
        resolved.server_file,
        "start_services",
        {"services": list(services) if services else None},
    )
    return {"broker": broker, **result}


def stop(
    services: list[str] | tuple[str, ...] = (),
    *,
    paths: ServicePaths | None = None,
) -> dict[str, Any]:
    """Stop selected services, or stop the broker when no service is given."""
    resolved = _paths(paths)
    if services:
        return call(
            resolved.server_file,
            "stop_services",
            {"services": list(services)},
        )
    return call(resolved.server_file, "shutdown")


def restart(
    services: list[str] | tuple[str, ...] = (),
    *,
    paths: ServicePaths | None = None,
    timeout_s: float = 5.0,
) -> dict[str, Any]:
    """Restart selected services, or restart the broker when no service is given."""
    resolved = _paths(paths)
    if services:
        start_broker(resolved, timeout_s=timeout_s)
        return call(
            resolved.server_file,
            "restart_services",
            {"services": list(services)},
        )
    if broker_running(resolved):
        stop(paths=resolved)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline and broker_running(resolved):
            time.sleep(0.1)
    return start_broker(resolved, timeout_s=timeout_s)


def list_services(*, paths: ServicePaths | None = None) -> dict[str, Any]:
    resolved = _paths(paths)
    try:
        return call(resolved.server_file, "list_services")
    except BrokerNotRunningError:
        registry = discover_services()
        state = StateStore(resolved)
        return {
            "services": [service.to_dict() for service in registry.all()],
            "enabled": sorted(state.enabled_services()),
        }


def set_enabled(
    services: list[str] | tuple[str, ...],
    enabled: bool,
    *,
    paths: ServicePaths | None = None,
) -> dict[str, Any]:
    resolved = _paths(paths)
    if broker_running(resolved):
        return call(
            resolved.server_file,
            "set_enabled",
            {"services": list(services), "enabled": enabled},
        )
    state = StateStore(resolved)
    state.set_enabled(services, enabled)
    for service in services:
        state.emit(
            "service.enabled" if enabled else "service.disabled",
            service=service,
        )
    return {"enabled": sorted(state.enabled_services())}


def events(
    *,
    paths: ServicePaths | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    resolved = _paths(paths)
    if broker_running(resolved):
        return call(resolved.server_file, "events", {"limit": limit})
    return {"events": StateStore(resolved).read_events(limit=limit)}


def emit_event(
    event_type: str,
    *,
    service: str | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
    paths: ServicePaths | None = None,
) -> ServiceEvent | dict[str, Any]:
    """Record a provider event without forcing broker startup."""
    resolved = _paths(paths)
    if broker_running(resolved):
        try:
            return call(
                resolved.server_file,
                "emit_event",
                {
                    "type": event_type,
                    "service": service,
                    "message": message,
                    "data": data or {},
                },
            )["event"]
        except IpcError:
            pass
    return StateStore(resolved).emit(
        event_type,
        service=service,
        message=message,
        data=data,
    )
