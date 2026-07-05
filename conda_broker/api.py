"""Broker object API for conda-broker users and provider plugins."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .exceptions import BrokerNotRunningError, IpcError, UnknownServiceError
from .ipc import call, ping
from .models import ServiceStatus
from .paths import ServicePaths
from .registry import discover_services
from .state import StateStore

if TYPE_CHECKING:
    from typing import Any

    from .models import EndpointStatus, ServiceEvent


@dataclass(frozen=True)
class BrokerState:
    """Reachability state for the local broker process."""

    running: bool
    started: bool | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BrokerState:
        return cls(
            running=bool(data.get("running", False)),
            started=(
                bool(data["started"])
                if "started" in data and data["started"] is not None
                else None
            ),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        data["running"] = self.running
        if self.started is not None or "started" in data:
            data["started"] = self.started
        return data


@dataclass(frozen=True)
class StatusSnapshot:
    """Broker and service status returned by API queries."""

    broker: BrokerState | None = None
    services: tuple[ServiceStatus, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StatusSnapshot:
        broker_data = data.get("broker")
        services = data.get("services")
        return cls(
            broker=(
                BrokerState.from_dict(broker_data)
                if isinstance(broker_data, dict)
                else None
            ),
            services=tuple(
                ServiceStatus.from_dict(service)
                for service in (services if isinstance(services, list) else [])
                if isinstance(service, dict)
            ),
            raw=dict(data),
        )

    def to_dict(self) -> dict[str, Any]:
        data = dict(self.raw)
        if self.broker is not None:
            data["broker"] = self.broker.to_dict()
        data["services"] = [service.to_dict() for service in self.services]
        return data


@dataclass(frozen=True)
class ServiceCheck:
    """Compact status report for plugin CLIs and optional integrations."""

    name: str
    available: bool
    running: bool = False
    ready: bool = False
    enabled: bool = False
    state: str = "unknown"
    health: str = "unknown"
    endpoint: EndpointStatus | None = None
    reason: str | None = None
    status: ServiceStatus | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "available": self.available,
            "running": self.running,
            "ready": self.ready,
            "enabled": self.enabled,
            "state": self.state,
            "health": self.health,
            "endpoint": self.endpoint.to_dict() if self.endpoint else None,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Broker:
    """Client for the current user's conda-broker process."""

    paths: ServicePaths = field(default_factory=ServicePaths.resolve)

    @classmethod
    def current(cls, paths: ServicePaths | None = None) -> Broker:
        """Return a broker handle for the current conda-broker user context."""
        return cls(_paths(paths))

    def running(self) -> bool:
        """Return whether the broker is reachable without starting it."""
        return ping(self.paths.server_file)

    def start(self, *, timeout_s: float = 5.0) -> BrokerState:
        """Start the broker if needed and wait until it accepts IPC."""
        return BrokerState.from_dict(
            _start_broker_payload(self.paths, timeout_s=timeout_s)["broker"]
        )

    def started(
        self,
        *,
        timeout_s: float = 5.0,
        stop_timeout_s: float = 5.0,
    ) -> BrokerContext:
        """Return a context manager that keeps the broker running.

        The context manager stops the broker on exit only when it started the
        broker on entry.
        """
        return BrokerContext(
            self,
            timeout_s=timeout_s,
            stop_timeout_s=stop_timeout_s,
        )

    def stop(self) -> dict[str, Any]:
        """Stop the broker process."""
        return call(self.paths.server_file, "shutdown")

    def restart(self, *, timeout_s: float = 5.0) -> BrokerState:
        """Restart the broker process."""
        if self.running():
            self.stop()
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline and self.running():
                time.sleep(0.1)
        return self.start(timeout_s=timeout_s)

    def status(self, service: str | None = None) -> StatusSnapshot:
        """Return broker and service status without starting the broker."""
        return StatusSnapshot.from_dict(_status_payload(service, paths=self.paths))

    def service(self, name: str) -> Service:
        """Return a lightweight handle for one service name."""
        return Service(self, name)

    def list_services(self) -> dict[str, Any]:
        """List discovered service definitions."""
        return _list_services_payload(self.paths)

    def start_services(
        self,
        services: str | list[str] | tuple[str, ...] = (),
        *,
        timeout_s: float = 5.0,
    ) -> StatusSnapshot:
        """Start selected services, starting the broker first if needed."""
        names = _service_names(services)
        broker = _start_broker_payload(self.paths, timeout_s=timeout_s)["broker"]
        result = call(
            self.paths.server_file,
            "start_services",
            {"services": names if names else None},
        )
        return StatusSnapshot.from_dict({"broker": broker, **result})

    def stop_services(
        self,
        services: str | list[str] | tuple[str, ...],
    ) -> StatusSnapshot:
        """Stop selected services without stopping the broker."""
        result = call(
            self.paths.server_file,
            "stop_services",
            {"services": _service_names(services)},
        )
        return StatusSnapshot.from_dict(result)

    def restart_services(
        self,
        services: str | list[str] | tuple[str, ...],
        *,
        timeout_s: float = 5.0,
    ) -> StatusSnapshot:
        """Restart selected services, starting the broker first if needed."""
        self.start(timeout_s=timeout_s)
        result = call(
            self.paths.server_file,
            "restart_services",
            {"services": _service_names(services)},
        )
        return StatusSnapshot.from_dict(result)

    def wait(
        self,
        service: str,
        *,
        timeout_s: float = 30.0,
        start_service: bool = False,
    ) -> StatusSnapshot:
        """Wait for one service to become ready.

        The broker is only started when ``start_service`` is true.
        """
        if start_service:
            self.start_services(service, timeout_s=timeout_s)
        result = call(
            self.paths.server_file,
            "wait_service",
            {"service": service, "timeout_s": timeout_s},
        )
        return StatusSnapshot.from_dict(result)

    def set_enabled(
        self,
        services: str | list[str] | tuple[str, ...],
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable services for broker startup."""
        return _set_enabled_payload(self.paths, services, enabled)

    def events(self, *, limit: int | None = None) -> dict[str, Any]:
        """Read broker and service events without starting the broker."""
        return _events_payload(self.paths, limit=limit)

    def emit_event(
        self,
        event_type: str,
        *,
        service: str | None = None,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> ServiceEvent | dict[str, Any]:
        """Record a provider event without forcing broker startup."""
        return _emit_event(
            self.paths,
            event_type,
            service=service,
            message=message,
            data=data,
        )


@dataclass(frozen=True)
class Service:
    """Handle for one broker-managed service."""

    broker: Broker
    name: str

    def status(self) -> ServiceStatus | None:
        """Return service status, or ``None`` when unavailable.

        This query never starts the broker and is safe for opportunistic plugin
        fast paths.
        """
        try:
            snapshot = self.broker.status(self.name)
        except (BrokerNotRunningError, IpcError, UnknownServiceError):
            return None
        return snapshot.services[0] if snapshot.services else None

    def check(self, endpoint: str = "default") -> ServiceCheck:
        """Return a compact service report without starting the broker.

        This is intended for plugin ``status`` or ``doctor`` commands that want
        stable JSON and human output without reimplementing broker-state logic.
        """
        try:
            snapshot = self.broker.status(self.name)
        except UnknownServiceError:
            return ServiceCheck(
                name=self.name,
                available=False,
                reason="unknown-service",
            )
        except (BrokerNotRunningError, IpcError):
            return ServiceCheck(
                name=self.name,
                available=False,
                reason="broker-unavailable",
            )
        if not snapshot.services:
            return ServiceCheck(
                name=self.name,
                available=False,
                reason="unknown-service",
            )

        status = snapshot.services[0]
        reason = None if status.ready else status.state
        return ServiceCheck(
            name=self.name,
            available=True,
            running=status.running,
            ready=status.ready,
            enabled=status.enabled,
            state=status.state,
            health=status.health,
            endpoint=status.endpoint(endpoint),
            reason=reason,
            status=status,
        )

    def running(self) -> bool:
        """Return whether the service process is running."""
        status = self.status()
        return bool(status and status.running)

    def ready(self) -> bool:
        """Return whether the service is ready for use."""
        status = self.status()
        return bool(status and status.ready)

    def endpoint(
        self,
        name: str = "default",
        *,
        ready: bool = False,
    ) -> EndpointStatus | None:
        """Return a resolved endpoint.

        When ``ready`` is true, this returns ``None`` unless the service is
        already ready and the selected endpoint has a resolved URL.
        """
        status = self.status()
        if status is None or (ready and not status.ready):
            return None
        endpoint = status.endpoint(name)
        if ready and (endpoint is None or endpoint.url is None):
            return None
        return endpoint

    def start(self, *, timeout_s: float = 5.0) -> StatusSnapshot:
        """Start this service, starting the broker first if needed."""
        return self.broker.start_services(self.name, timeout_s=timeout_s)

    def started(
        self,
        *,
        timeout_s: float = 5.0,
        wait: bool = False,
        wait_timeout_s: float = 30.0,
        stop_timeout_s: float = 5.0,
    ) -> ServiceContext:
        """Return a context manager that keeps this service running.

        The context manager stops the service on exit only when it started the
        service on entry. If starting the service also started the broker, the
        broker is stopped on exit as well.
        """
        return ServiceContext(
            self,
            timeout_s=timeout_s,
            wait=wait,
            wait_timeout_s=wait_timeout_s,
            stop_timeout_s=stop_timeout_s,
        )

    def stop(self) -> StatusSnapshot:
        """Stop this service."""
        return self.broker.stop_services(self.name)

    def restart(self, *, timeout_s: float = 5.0) -> StatusSnapshot:
        """Restart this service, starting the broker first if needed."""
        return self.broker.restart_services(self.name, timeout_s=timeout_s)

    def wait(
        self,
        *,
        timeout_s: float = 30.0,
        start: bool = False,
    ) -> StatusSnapshot:
        """Wait for this service to become ready."""
        return self.broker.wait(
            self.name,
            timeout_s=timeout_s,
            start_service=start,
        )

    def enable(self) -> dict[str, Any]:
        """Enable this service for broker startup."""
        return self.broker.set_enabled(self.name, True)

    def disable(self) -> dict[str, Any]:
        """Disable this service for broker startup."""
        return self.broker.set_enabled(self.name, False)

    def emit_event(
        self,
        event_type: str,
        *,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> ServiceEvent | dict[str, Any]:
        """Record an event for this service without forcing broker startup."""
        return self.broker.emit_event(
            event_type,
            service=self.name,
            message=message,
            data=data,
        )


@dataclass
class BrokerContext:
    """Context manager returned by ``Broker.started()``."""

    broker: Broker
    timeout_s: float = 5.0
    stop_timeout_s: float = 5.0
    _started_broker: bool = False

    def __enter__(self) -> Broker:
        self._started_broker = not self.broker.running()
        try:
            self.broker.start(timeout_s=self.timeout_s)
        except Exception:
            if self._started_broker and self.broker.running():
                self.broker.stop()
                _wait_until_stopped(self.broker, timeout_s=self.stop_timeout_s)
            raise
        return self.broker

    def __exit__(self, *exc_info: object) -> None:
        if self._started_broker and self.broker.running():
            self.broker.stop()
            _wait_until_stopped(self.broker, timeout_s=self.stop_timeout_s)


@dataclass
class ServiceContext:
    """Context manager returned by ``Service.started()``."""

    service: Service
    timeout_s: float = 5.0
    wait: bool = False
    wait_timeout_s: float = 30.0
    stop_timeout_s: float = 5.0
    _started_broker: bool = False
    _started_service: bool = False

    def __enter__(self) -> Service:
        self._started_broker = not self.service.broker.running()
        status = self.service.status()
        self._started_service = not (status and status.running)
        try:
            self.service.start(timeout_s=self.timeout_s)
            if self.wait:
                self.service.wait(timeout_s=self.wait_timeout_s)
        except Exception:
            self._cleanup()
            raise
        return self.service

    def __exit__(self, *exc_info: object) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        try:
            if self._started_service:
                self.service.stop()
        finally:
            if self._started_broker and self.service.broker.running():
                self.service.broker.stop()
                _wait_until_stopped(
                    self.service.broker,
                    timeout_s=self.stop_timeout_s,
                )


def _paths(paths: ServicePaths | None = None) -> ServicePaths:
    return paths or ServicePaths.resolve()


def _service_names(services: str | list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(services, str):
        return [services]
    return list(services)


def _start_broker_payload(
    paths: ServicePaths,
    *,
    timeout_s: float,
) -> dict[str, Any]:
    paths.ensure()
    if ping(paths.server_file):
        return {"broker": {"running": True, "started": False}}

    env = {
        **os.environ,
        "CONDA_BROKER_RUNTIME_DIR": str(paths.runtime_dir),
        "CONDA_BROKER_LOG_DIR": str(paths.log_dir),
    }
    log = paths.broker_log_file.open("a", encoding="utf-8")
    subprocess.Popen(
        [
            sys.executable,
            "-m",
            "conda_broker.broker",
            "--runtime-dir",
            str(paths.runtime_dir),
            "--log-dir",
            str(paths.log_dir),
        ],
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=(os.name != "nt"),
    )
    log.close()

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if ping(paths.server_file):
            return {"broker": {"running": True, "started": True}}
        time.sleep(0.1)
    raise BrokerNotRunningError("Timed out waiting for conda-broker broker")


def _status_payload(
    service: str | None,
    *,
    paths: ServicePaths,
) -> dict[str, Any]:
    try:
        return call(
            paths.server_file,
            "status",
            {"service": service} if service else {},
        )
    except BrokerNotRunningError:
        registry = discover_services()
        if service is not None and service not in registry:
            raise UnknownServiceError(f"Unknown service: {service}")
        state = StateStore(paths)
        enabled = state.enabled_services()
        services = [
            {
                **registered.to_dict(),
                "enabled": registered.name in enabled,
                "state": "stopped",
                "running": False,
                "pid": None,
                "health": "unknown",
                "ready": False,
                "endpoints": {
                    endpoint.name: endpoint.resolve().to_dict()
                    for endpoint in registered.endpoints
                },
            }
            for registered in registry.all()
            if service is None or registered.name == service
        ]
        return {"broker": {"running": False}, "services": services}


def _list_services_payload(paths: ServicePaths) -> dict[str, Any]:
    try:
        return call(paths.server_file, "list_services")
    except BrokerNotRunningError:
        registry = discover_services()
        state = StateStore(paths)
        return {
            "services": [service.to_dict() for service in registry.all()],
            "enabled": sorted(state.enabled_services()),
        }


def _set_enabled_payload(
    paths: ServicePaths,
    services: str | list[str] | tuple[str, ...],
    enabled: bool,
) -> dict[str, Any]:
    names = _service_names(services)
    if ping(paths.server_file):
        return call(
            paths.server_file,
            "set_enabled",
            {"services": names, "enabled": enabled},
        )
    registry = discover_services()
    for service in names:
        if service not in registry:
            raise UnknownServiceError(f"Unknown service: {service}")
    state = StateStore(paths)
    state.set_enabled(names, enabled)
    for service in names:
        state.emit(
            "service.enabled" if enabled else "service.disabled",
            service=service,
        )
    return {"enabled": sorted(state.enabled_services())}


def _events_payload(
    paths: ServicePaths,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    if ping(paths.server_file):
        return call(paths.server_file, "events", {"limit": limit})
    return {"events": StateStore(paths).read_events(limit=limit)}


def _emit_event(
    paths: ServicePaths,
    event_type: str,
    *,
    service: str | None = None,
    message: str = "",
    data: dict[str, Any] | None = None,
) -> ServiceEvent | dict[str, Any]:
    if ping(paths.server_file):
        try:
            return call(
                paths.server_file,
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
    return StateStore(paths).emit(
        event_type,
        service=service,
        message=message,
        data=data,
    )


def _wait_until_stopped(broker: Broker, *, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and broker.running():
        time.sleep(0.1)
