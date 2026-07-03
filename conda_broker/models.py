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
        if self.type == "tcp" and (not self.host or not self.port):
            raise ValueError("TCP health checks require host and port")
        if self.type == "http" and not self.url:
            raise ValueError("HTTP health checks require url")
        if self.type == "exec" and not self.command:
            raise ValueError("Exec health checks require command")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "interval_s": self.interval_s,
            "timeout_s": self.timeout_s,
            "command": list(self.command),
            "host": self.host,
            "port": self.port,
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
    dependencies: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: str | None = None

    def __post_init__(self) -> None:
        validate_service_name(self.name)
        object.__setattr__(self, "dependencies", tuple(self.dependencies))
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
