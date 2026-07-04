"""Typed service models shared by providers, clients, and the supervisor."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")

START_POLICIES = {"manual", "enabled"}
RESTART_POLICIES = {"never", "on-failure", "always"}
RUNTIMES = {"process"}
HEALTH_CHECK_TYPES = {"process", "tcp", "http", "exec"}
ENDPOINT_PROTOCOLS = {"tcp", "http"}


def utc_now() -> str:
    """Return the current UTC timestamp in a stable ISO-8601 shape."""
    return datetime.now(timezone.utc).isoformat()


def validate_service_name(name: str) -> None:
    """Raise ``ValueError`` if *name* is not a portable service identifier."""
    if not SERVICE_NAME_RE.fullmatch(name):
        raise ValueError(
            "Service names must contain only letters, numbers, '.', '_', and '-' "
            f"and must not be empty: {name!r}"
        )


@dataclass(frozen=True)
class HealthCheck:
    """Health check definition for a service."""

    type: str = "process"
    interval_s: float = 30.0
    timeout_s: float = 5.0
    start_period_s: float = 5.0
    endpoint: str | None = None
    command: tuple[str, ...] = ()
    host: str | None = None
    port: int | None = None
    url: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(self.command))
        if self.type not in HEALTH_CHECK_TYPES:
            raise ValueError(f"Unknown health check type: {self.type}")
        if self.interval_s <= 0:
            raise ValueError("Health check interval must be positive")
        if self.timeout_s <= 0:
            raise ValueError("Health check timeout must be positive")
        if self.start_period_s < 0:
            raise ValueError("Health check start period must not be negative")
        if self.endpoint is not None:
            validate_service_name(self.endpoint)
        if (
            self.type == "tcp"
            and not self.endpoint
            and (not self.host or not self.port)
        ):
            raise ValueError("TCP health checks require host and port")
        if self.type == "http" and not self.endpoint and not self.url:
            raise ValueError("HTTP health checks require url")
        if self.type == "exec" and not self.command:
            raise ValueError("Exec health checks require command")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "interval_s": self.interval_s,
            "timeout_s": self.timeout_s,
            "start_period_s": self.start_period_s,
            "endpoint": self.endpoint,
            "command": list(self.command),
            "host": self.host,
            "port": self.port,
            "url": self.url,
        }


@dataclass(frozen=True)
class EndpointSpec:
    """Network endpoint contract exposed by a service."""

    name: str = "default"
    protocol: str = "tcp"
    host: str = "127.0.0.1"
    port: int | None = None
    path: str = "/"
    port_env: str | None = None
    url_env: str | None = None

    def __post_init__(self) -> None:
        validate_service_name(self.name)
        if self.protocol not in ENDPOINT_PROTOCOLS:
            raise ValueError(f"Unknown endpoint protocol: {self.protocol}")
        if not self.host:
            raise ValueError("Endpoint host must not be empty")
        if self.port is not None and not 0 < self.port < 65536:
            raise ValueError("Endpoint port must be between 1 and 65535")
        if self.protocol == "http" and not self.path.startswith("/"):
            raise ValueError("HTTP endpoint paths must start with '/'")

    @property
    def needs_port_allocation(self) -> bool:
        return self.port is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "port_env": self.port_env,
            "url_env": self.url_env,
        }

    def resolve(self, port: int | None = None) -> EndpointStatus:
        resolved_port = self.port if self.port is not None else port
        url = None
        if resolved_port is not None:
            url = endpoint_url(self.protocol, self.host, resolved_port, self.path)
        return EndpointStatus(
            name=self.name,
            protocol=self.protocol,
            host=self.host,
            port=resolved_port,
            path=self.path,
            url=url,
        )


@dataclass(frozen=True)
class EndpointStatus:
    """Resolved endpoint state reported for a service."""

    name: str
    protocol: str
    host: str
    port: int | None = None
    path: str = "/"
    url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "url": self.url,
        }


def endpoint_url(protocol: str, host: str, port: int, path: str = "/") -> str:
    """Return a client URL for an endpoint."""
    if protocol == "http":
        return f"http://{host}:{port}{path}"
    return f"{protocol}://{host}:{port}"


@dataclass(frozen=True)
class ProcessSpec:
    """Host process runtime definition."""

    argv: tuple[str, ...]
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None
    stop_signal: str = "TERM"
    grace_period_s: float = 5.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "argv", tuple(self.argv))
        object.__setattr__(
            self,
            "env",
            {str(key): str(value) for key, value in self.env.items()},
        )
        if not self.argv:
            raise ValueError("Process services require a non-empty argv")
        if self.grace_period_s <= 0:
            raise ValueError("Process grace period must be positive")

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": list(self.argv),
            "env": dict(self.env),
            "cwd": self.cwd,
            "stop_signal": self.stop_signal,
            "grace_period_s": self.grace_period_s,
        }


@dataclass(frozen=True)
class CondaService:
    """A service definition returned by a conda-broker provider."""

    name: str
    summary: str
    source: str
    process: ProcessSpec | None = None
    runtime: str = "process"
    start_policy: str = "manual"
    restart_policy: str = "on-failure"
    health_check: HealthCheck = field(default_factory=HealthCheck)
    endpoints: tuple[EndpointSpec, ...] = ()
    dependencies: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None

    def __post_init__(self) -> None:
        validate_service_name(self.name)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
        object.__setattr__(self, "endpoints", tuple(self.endpoints))
        object.__setattr__(
            self,
            "env",
            {str(key): str(value) for key, value in self.env.items()},
        )
        if self.runtime not in RUNTIMES:
            raise ValueError(f"Unknown runtime: {self.runtime}")
        if self.start_policy not in START_POLICIES:
            raise ValueError(f"Unknown start policy: {self.start_policy}")
        if self.restart_policy not in RESTART_POLICIES:
            raise ValueError(f"Unknown restart policy: {self.restart_policy}")
        for dependency in self.dependencies:
            validate_service_name(dependency)
        endpoint_names = [endpoint.name for endpoint in self.endpoints]
        if len(endpoint_names) != len(set(endpoint_names)):
            raise ValueError("Service endpoints must have unique names")
        if (
            self.health_check.endpoint
            and self.health_check.endpoint not in endpoint_names
        ):
            raise ValueError(
                "Health check references unknown endpoint: "
                f"{self.health_check.endpoint}"
            )
        if self.runtime == "process" and self.process is None:
            raise ValueError("'process' services require process")

    @property
    def enabled_by_default(self) -> bool:
        return self.start_policy == "enabled"

    def merged_process(self) -> ProcessSpec:
        """Return the process spec with service-level env/cwd defaults applied."""
        if self.process is None:
            raise ValueError(f"Service {self.name!r} has no process spec")
        env = dict(self.env)
        env.update(self.process.env)
        return ProcessSpec(
            argv=self.process.argv,
            env=env,
            cwd=self.process.cwd or self.cwd,
            stop_signal=self.process.stop_signal,
            grace_period_s=self.process.grace_period_s,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "source": self.source,
            "runtime": self.runtime,
            "start_policy": self.start_policy,
            "restart_policy": self.restart_policy,
            "health_check": self.health_check.to_dict(),
            "endpoints": [endpoint.to_dict() for endpoint in self.endpoints],
            "dependencies": list(self.dependencies),
            "env": dict(self.env),
            "cwd": self.cwd,
            "process": self.process.to_dict() if self.process else None,
        }


@dataclass(frozen=True)
class ServiceStatus:
    """Observed state for a registered service."""

    name: str
    summary: str
    source: str
    runtime: str
    enabled: bool
    state: str
    running: bool = False
    pid: int | None = None
    exit_code: int | None = None
    started_at: str | None = None
    restart_count: int = 0
    health: str = "unknown"
    ready: bool = False
    endpoints: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "summary": self.summary,
            "source": self.source,
            "runtime": self.runtime,
            "enabled": self.enabled,
            "state": self.state,
            "running": self.running,
            "pid": self.pid,
            "exit_code": self.exit_code,
            "started_at": self.started_at,
            "restart_count": self.restart_count,
            "health": self.health,
            "ready": self.ready,
            "endpoints": dict(self.endpoints),
        }


@dataclass(frozen=True)
class ServiceEvent:
    """Append-only event record."""

    type: str
    service: str | None = None
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "service": self.service,
            "message": self.message,
            "data": dict(self.data),
        }
