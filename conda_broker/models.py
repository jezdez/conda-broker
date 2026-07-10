"""Typed service models shared by providers, API users, and the supervisor."""

from __future__ import annotations

import re
import signal
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

SERVICE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
ENV_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

START_POLICIES = {"manual", "enabled"}
RESTART_POLICIES = {"never", "on-failure", "always"}
HEALTH_CHECK_TYPES = {"process", "tcp", "http", "exec"}
ENDPOINT_PROTOCOLS = {"tcp", "http"}


class ServiceName(str):
    """A validated service or endpoint name."""

    def __new__(cls, value: str) -> ServiceName:
        if not SERVICE_NAME_RE.fullmatch(value):
            raise ValueError(
                "Service names must contain only letters, numbers, '.', '_', and '-' "
                f"and must not be empty: {value!r}"
            )
        return super().__new__(cls, value)

    @property
    def environment_slug(self) -> str:
        return (
            "".join(char if char.isalnum() else "_" for char in self.upper()).strip("_")
            or "DEFAULT"
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
        if not isfinite(self.interval_s) or self.interval_s <= 0:
            raise ValueError("Health check interval must be positive")
        if not isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("Health check timeout must be positive")
        if not isfinite(self.start_period_s) or self.start_period_s < 0:
            raise ValueError("Health check start period must not be negative")
        if self.endpoint is not None:
            ServiceName(self.endpoint)
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
        object.__setattr__(self, "name", ServiceName(self.name))
        if self.protocol not in ENDPOINT_PROTOCOLS:
            raise ValueError(f"Unknown endpoint protocol: {self.protocol}")
        if not self.host:
            raise ValueError("Endpoint host must not be empty")
        if self.port is not None and not 0 < self.port < 65536:
            raise ValueError("Endpoint port must be between 1 and 65535")
        if self.protocol == "http" and not self.path.startswith("/"):
            raise ValueError("HTTP endpoint paths must start with '/'")
        for env_name in (self.port_env, self.url_env):
            if env_name is not None and not ENV_NAME_RE.fullmatch(env_name):
                raise ValueError(f"Invalid environment variable name: {env_name!r}")

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
            url_host = (
                f"[{self.host}]"
                if ":" in self.host and not self.host.startswith("[")
                else self.host
            )
            url = (
                f"http://{url_host}:{resolved_port}{self.path}"
                if self.protocol == "http"
                else f"{self.protocol}://{url_host}:{resolved_port}"
            )
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

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EndpointStatus:
        """Build an endpoint status from a JSON payload."""
        port_value = data.get("port")
        try:
            port = int(port_value) if port_value is not None else None
        except (TypeError, ValueError):
            port = None
        url_value = data.get("url")
        return cls(
            name=str(data.get("name", "default")),
            protocol=str(data.get("protocol", "tcp")),
            host=str(data.get("host", "127.0.0.1")),
            port=port,
            path=str(data.get("path", "/")),
            url=str(url_value) if url_value is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "path": self.path,
            "url": self.url,
        }


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
        environment = {str(key): str(value) for key, value in self.env.items()}
        for key, value in environment.items():
            if not ENV_NAME_RE.fullmatch(key):
                raise ValueError(f"Invalid environment variable name: {key!r}")
            if "\0" in value:
                raise ValueError(f"Environment variable {key!r} contains a null byte")
        object.__setattr__(self, "env", environment)
        if not self.argv:
            raise ValueError("Process services require a non-empty argv")
        if not isfinite(self.grace_period_s) or self.grace_period_s <= 0:
            raise ValueError("Process grace period must be positive")
        _ = self.signal_number

    @property
    def signal_number(self) -> int:
        """Return the configured stop signal as an OS signal number."""
        name = self.stop_signal.upper()
        candidates = (name,) if name.startswith("SIG") else (name, f"SIG{name}")
        for candidate in candidates:
            value = getattr(signal, candidate, None)
            if isinstance(value, int):
                return int(value)
        raise ValueError(f"Unknown process stop signal: {self.stop_signal}")

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
        object.__setattr__(self, "name", ServiceName(self.name))
        object.__setattr__(
            self,
            "dependencies",
            tuple(ServiceName(name) for name in self.dependencies),
        )
        object.__setattr__(self, "endpoints", tuple(self.endpoints))
        environment = {str(key): str(value) for key, value in self.env.items()}
        for key, value in environment.items():
            if not ENV_NAME_RE.fullmatch(key):
                raise ValueError(f"Invalid environment variable name: {key!r}")
            if "\0" in value:
                raise ValueError(f"Environment variable {key!r} contains a null byte")
        object.__setattr__(self, "env", environment)
        if not SERVICE_NAME_RE.fullmatch(self.runtime):
            raise ValueError(f"Invalid runtime name: {self.runtime!r}")
        if self.start_policy not in START_POLICIES:
            raise ValueError(f"Unknown start policy: {self.start_policy}")
        if self.restart_policy not in RESTART_POLICIES:
            raise ValueError(f"Unknown restart policy: {self.restart_policy}")
        endpoint_names = [endpoint.name for endpoint in self.endpoints]
        if len(endpoint_names) != len(set(endpoint_names)):
            raise ValueError("Service endpoints must have unique names")
        endpoint_slugs = [ServiceName(name).environment_slug for name in endpoint_names]
        if len(endpoint_slugs) != len(set(endpoint_slugs)):
            raise ValueError(
                "Service endpoint names must have unique environment variable names"
            )
        automatic_env = {"CONDA_BROKER_SERVICE_NAME"}
        for slug in endpoint_slugs:
            prefix = f"CONDA_BROKER_ENDPOINT_{slug}"
            automatic_env.update(
                {
                    f"{prefix}_PROTOCOL",
                    f"{prefix}_HOST",
                    f"{prefix}_PORT",
                    f"{prefix}_URL",
                }
            )
        custom_env = [
            name
            for endpoint in self.endpoints
            for name in (endpoint.port_env, endpoint.url_env)
            if name is not None
        ]
        if len(custom_env) != len(set(custom_env)):
            raise ValueError("Service endpoint custom environment names must be unique")
        conflicts = sorted(set(custom_env) & automatic_env)
        if conflicts:
            raise ValueError(
                "Service endpoint custom environment names conflict with broker "
                f"variables: {', '.join(conflicts)}"
            )
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

    def endpoint_statuses(self) -> dict[str, dict[str, Any]]:
        """Return unresolved endpoint status rows for stopped services."""
        return {
            endpoint.name: endpoint.resolve().to_dict() for endpoint in self.endpoints
        }

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

    @staticmethod
    def parse_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceStatus:
        """Build a service status from a JSON payload."""
        endpoints = data.get("endpoints")
        endpoint_data = {
            str(name): dict(endpoint)
            for name, endpoint in (
                endpoints.items() if isinstance(endpoints, dict) else ()
            )
            if isinstance(endpoint, dict)
        }
        return cls(
            name=str(data.get("name", "")),
            summary=str(data.get("summary", "")),
            source=str(data.get("source", "")),
            runtime=str(data.get("runtime", "")),
            enabled=bool(data.get("enabled", False)),
            state=str(data.get("state", "unknown")),
            running=bool(data.get("running", False)),
            pid=cls.parse_int(data.get("pid")),
            exit_code=cls.parse_int(data.get("exit_code")),
            started_at=(
                str(data["started_at"]) if data.get("started_at") is not None else None
            ),
            restart_count=int(data.get("restart_count") or 0),
            health=str(data.get("health", "unknown")),
            ready=bool(data.get("ready", False)),
            endpoints=endpoint_data,
        )

    def endpoint(self, name: str = "default") -> EndpointStatus | None:
        """Return one typed endpoint status by name."""
        data = self.endpoints.get(name)
        if data is None:
            return None
        return EndpointStatus.from_dict(data)

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
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServiceEvent:
        """Build a service event from a JSON payload."""
        event_data = data.get("data")
        values: dict[str, Any] = {
            "type": str(data.get("type", "plugin.event")),
            "service": (
                str(data["service"]) if data.get("service") is not None else None
            ),
            "message": str(data.get("message", "")),
            "data": dict(event_data) if isinstance(event_data, dict) else {},
        }
        if data.get("timestamp") is not None:
            values["timestamp"] = str(data["timestamp"])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "service": self.service,
            "message": self.message,
            "data": dict(self.data),
        }
