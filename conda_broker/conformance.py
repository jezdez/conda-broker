"""Provider service conformance checks for development workflows."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .paths import ServicePaths
from .registry import discover_services
from .state import StateStore
from .supervisor import ServiceSupervisor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from .models import CondaService, ServiceStatus
    from .registry import ServiceRegistry

SCENARIOS = {"start-stop", "health", "crash"}


@dataclass
class CheckResult:
    """One provider conformance check result."""

    name: str
    status: str
    message: str
    data: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in {"pass", "warn", "skip"}

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "message": self.message,
            "data": dict(self.data),
        }


@dataclass
class ConformanceResult:
    """Structured result for one conformance command."""

    service: str
    command: str
    scenario: str | None = None
    workspace: str | None = None
    kept: bool = False
    checks: list[CheckResult] = field(default_factory=list)
    status: dict[str, object] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(check.ok for check in self.checks)

    def add(
        self,
        status: str,
        name: str,
        message: str,
        **data: object,
    ) -> None:
        self.checks.append(CheckResult(name, status, message, data))

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "service": self.service,
            "command": self.command,
            "scenario": self.scenario,
            "workspace": self.workspace,
            "kept": self.kept,
            "checks": [check.to_dict() for check in self.checks],
            "status": self.status,
            "events": self.events,
            "logs": self.logs,
        }


def validate(
    service_name: str,
    *,
    registry: ServiceRegistry | None = None,
) -> ConformanceResult:
    """Run static provider conformance checks for one service."""
    resolved_registry = registry or discover_services()
    service = resolved_registry.get(service_name)
    result = ConformanceResult(service=service.name, command="validate")
    _validate_service(service, resolved_registry, result)
    return result


def run(
    service_name: str,
    *,
    registry: ServiceRegistry | None = None,
    duration_s: float = 3.0,
    timeout_s: float = 5.0,
    keep: bool = False,
) -> ConformanceResult:
    """Run one service briefly in an isolated broker workspace."""
    resolved_registry = registry or discover_services()
    service = resolved_registry.get(service_name)
    with _workspace(keep=keep) as (root, paths):
        result = ConformanceResult(
            service=service.name,
            command="run",
            scenario="start-stop",
            workspace=str(root),
            kept=keep,
        )
        _validate_service(service, resolved_registry, result)
        _scenario_start_stop(
            service.name,
            resolved_registry,
            paths,
            result,
            timeout_s=timeout_s,
            observe_s=duration_s,
        )
        return result


def test(
    service_name: str,
    *,
    registry: ServiceRegistry | None = None,
    scenario: str = "start-stop",
    timeout_s: float = 5.0,
    keep: bool = False,
) -> ConformanceResult:
    """Run one conformance scenario for a service in an isolated workspace."""
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown conformance scenario: {scenario}")
    resolved_registry = registry or discover_services()
    service = resolved_registry.get(service_name)
    with _workspace(keep=keep) as (root, paths):
        result = ConformanceResult(
            service=service.name,
            command="test",
            scenario=scenario,
            workspace=str(root),
            kept=keep,
        )
        _validate_service(service, resolved_registry, result)
        if scenario == "start-stop":
            _scenario_start_stop(
                service.name,
                resolved_registry,
                paths,
                result,
                timeout_s=timeout_s,
            )
        elif scenario == "health":
            _scenario_health(
                service.name,
                resolved_registry,
                paths,
                result,
                timeout_s=timeout_s,
            )
        else:
            _scenario_crash(
                service.name,
                resolved_registry,
                paths,
                result,
                timeout_s=timeout_s,
            )
        return result


def report(
    service_name: str,
    *,
    registry: ServiceRegistry | None = None,
    timeout_s: float = 5.0,
    keep: bool = False,
) -> dict[str, object]:
    """Run the complete provider conformance report for one service."""
    resolved_registry = registry or discover_services()
    service = resolved_registry.get(service_name)
    results: list[ConformanceResult] = [
        validate(service.name, registry=resolved_registry),
        run(
            service.name,
            registry=resolved_registry,
            duration_s=min(timeout_s, 3.0),
            timeout_s=timeout_s,
            keep=keep,
        ),
    ]
    for scenario in ("health", "crash"):
        results.append(
            test(
                service.name,
                registry=resolved_registry,
                scenario=scenario,
                timeout_s=timeout_s,
                keep=keep,
            )
        )
    return {
        "ok": all(result.ok for result in results),
        "service": service.name,
        "command": "report",
        "results": [result.to_dict() for result in results],
    }


def _validate_service(
    service: CondaService,
    registry: ServiceRegistry,
    result: ConformanceResult,
) -> None:
    result.add("pass", "service.discovered", "service is discoverable")
    if service.summary.strip():
        result.add("pass", "service.summary", "summary is present")
    else:
        result.add("warn", "service.summary", "summary is empty")

    if service.runtime == "process":
        result.add("pass", "runtime.process", "process runtime is supported")
    else:
        result.add(
            "fail",
            "runtime.supported",
            f"runtime {service.runtime!r} is not supported by this broker",
        )
        return

    process = service.merged_process()
    result.add(
        "pass",
        "process.argv",
        "process argv is configured",
        argv=list(process.argv),
    )
    _check_command("process.command", process.argv, result)

    if process.cwd is None:
        result.add("pass", "process.cwd", "service does not require a cwd")
    elif Path(process.cwd).exists():
        result.add("pass", "process.cwd", "configured cwd exists", cwd=process.cwd)
    else:
        result.add(
            "fail",
            "process.cwd",
            "configured cwd does not exist",
            cwd=process.cwd,
        )

    if process.grace_period_s <= 30:
        result.add(
            "pass",
            "process.grace_period",
            "grace period is operator-friendly",
            seconds=process.grace_period_s,
        )
    else:
        result.add(
            "warn",
            "process.grace_period",
            "long grace periods slow down stop and restart workflows",
            seconds=process.grace_period_s,
        )

    for dependency in service.dependencies:
        if dependency in registry:
            result.add(
                "pass",
                "dependency.known",
                f"dependency {dependency!r} is discoverable",
                dependency=dependency,
            )
        else:
            result.add(
                "fail",
                "dependency.known",
                f"dependency {dependency!r} is missing",
                dependency=dependency,
            )

    _validate_health_check(service, result)


def _validate_health_check(service: CondaService, result: ConformanceResult) -> None:
    check = service.health_check
    result.add(
        "pass",
        "health.type",
        f"{check.type} health check is configured",
        type=check.type,
    )
    if check.timeout_s <= service.merged_process().grace_period_s:
        result.add(
            "pass",
            "health.timeout",
            "health timeout is bounded by the stop grace period",
            timeout_s=check.timeout_s,
        )
    else:
        result.add(
            "warn",
            "health.timeout",
            "health timeout is longer than the stop grace period",
            timeout_s=check.timeout_s,
            grace_period_s=service.merged_process().grace_period_s,
        )

    if check.type == "exec":
        _check_command("health.exec.command", check.command, result)
    elif check.type == "tcp" and check.host is not None:
        _check_loopback_host("health.tcp.host", check.host, result)
    elif check.type == "http" and check.url is not None:
        host = urlparse(check.url).hostname or ""
        _check_loopback_host("health.http.host", host, result)


def _check_command(
    name: str,
    argv: tuple[str, ...],
    result: ConformanceResult,
) -> None:
    executable = argv[0]
    if _command_exists(executable):
        result.add("pass", name, "command appears executable", command=executable)
    else:
        result.add(
            "warn",
            name,
            "command was not found on PATH or as an absolute path",
            command=executable,
        )


def _command_exists(command: str) -> bool:
    path = Path(command)
    if path.is_absolute() or os.sep in command or (os.altsep and os.altsep in command):
        return path.exists()
    return shutil.which(command) is not None


def _check_loopback_host(
    name: str,
    host: str,
    result: ConformanceResult,
) -> None:
    if host == "localhost":
        result.add("pass", name, "health endpoint is loopback", host=host)
        return
    try:
        if ip_address(host).is_loopback:
            result.add("pass", name, "health endpoint is loopback", host=host)
            return
    except ValueError:
        pass
    result.add(
        "warn",
        name,
        "health endpoint is not obviously loopback",
        host=host,
    )


def _scenario_start_stop(
    service_name: str,
    registry: ServiceRegistry,
    paths: ServicePaths,
    result: ConformanceResult,
    *,
    timeout_s: float,
    observe_s: float = 0.0,
) -> None:
    state = StateStore(paths)
    supervisor = ServiceSupervisor(registry, state, paths)
    stopped = None
    try:
        try:
            status = _start_and_observe(supervisor, service_name, timeout_s=timeout_s)
        except Exception as exc:
            result.add(
                "fail",
                "runtime.start",
                "service failed to start",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return
        result.status = status.to_dict()
        if status.running:
            result.add("pass", "runtime.start", "service started", pid=status.pid)
        else:
            result.add(
                "fail",
                "runtime.start",
                "service did not remain running",
                state=status.state,
                exit_code=status.exit_code,
            )
        if observe_s > 0:
            _observe(supervisor, observe_s)
        lines = supervisor.logs.read_lines(service_name, lines=20)
        result.logs = lines
        if lines:
            result.add("pass", "logs.capture", "service wrote log output")
        else:
            result.add("warn", "logs.capture", "service log is empty")
    finally:
        try:
            stopped_statuses = supervisor.stop_services()
            stopped = stopped_statuses[0] if stopped_statuses else None
        finally:
            result.events = state.read_events(limit=50)
        if stopped is not None and not stopped.running:
            result.add("pass", "runtime.stop", "service stopped cleanly")


def _scenario_health(
    service_name: str,
    registry: ServiceRegistry,
    paths: ServicePaths,
    result: ConformanceResult,
    *,
    timeout_s: float,
) -> None:
    state = StateStore(paths)
    supervisor = ServiceSupervisor(registry, state, paths)
    try:
        try:
            status = _start_and_observe(supervisor, service_name, timeout_s=timeout_s)
        except Exception as exc:
            result.add(
                "fail",
                "health.setup",
                "service failed to start before health check",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return
        result.status = status.to_dict()
        if status.health == "healthy":
            result.add("pass", "health.observed", "health check reported healthy")
        elif status.health == "unknown":
            result.add("fail", "health.observed", "health check did not run")
        else:
            result.add("fail", "health.observed", "health check reported unhealthy")
    finally:
        try:
            supervisor.stop_services()
        finally:
            result.events = state.read_events(limit=50)
            result.logs = supervisor.logs.read_lines(service_name, lines=20)


def _scenario_crash(
    service_name: str,
    registry: ServiceRegistry,
    paths: ServicePaths,
    result: ConformanceResult,
    *,
    timeout_s: float,
) -> None:
    state = StateStore(paths)
    supervisor = ServiceSupervisor(registry, state, paths)
    service = registry.get(service_name)
    try:
        try:
            status = _start_and_observe(supervisor, service_name, timeout_s=timeout_s)
        except Exception as exc:
            result.add(
                "fail",
                "crash.setup",
                "service failed to start before crash scenario",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return
        if not status.running:
            result.add("fail", "crash.setup", "service was not running before crash")
            return
        managed = supervisor._managed.get(service_name)
        if managed is None:
            result.add("fail", "crash.setup", "service process was not tracked")
            return
        supervisor._runtime.kill(managed.process)
        deadline = time.monotonic() + timeout_s
        final = status
        while time.monotonic() < deadline:
            supervisor.monitor_once()
            final = supervisor.status_many([service_name])[0]
            if service.restart_policy == "never" and not final.running:
                break
            if final.running and final.restart_count > status.restart_count:
                break
            time.sleep(0.1)
        result.status = final.to_dict()
        if service.restart_policy == "never":
            if not final.running and final.restart_count == 0:
                result.add(
                    "pass",
                    "crash.restart_policy",
                    "service stayed stopped as restart_policy=never requires",
                )
            else:
                result.add(
                    "fail",
                    "crash.restart_policy",
                    "service restarted despite restart_policy=never",
                )
        elif final.running and final.restart_count > status.restart_count:
            result.add(
                "pass",
                "crash.restart_policy",
                "service restarted after a crash",
                restart_count=final.restart_count,
            )
        else:
            result.add(
                "fail",
                "crash.restart_policy",
                "service did not restart after a crash before timeout",
                restart_policy=service.restart_policy,
            )
    finally:
        try:
            supervisor.stop_services()
        finally:
            result.events = state.read_events(limit=50)
            result.logs = supervisor.logs.read_lines(service_name, lines=20)


def _start_and_observe(
    supervisor: ServiceSupervisor,
    service_name: str,
    *,
    timeout_s: float,
) -> ServiceStatus:
    supervisor.start_services([service_name])
    deadline = time.monotonic() + timeout_s
    status = supervisor.status_many([service_name])[0]
    while time.monotonic() < deadline:
        supervisor.monitor_once()
        status = supervisor.status_many([service_name])[0]
        if status.running and status.health != "unknown":
            return status
        if not status.running and status.state != "restarting":
            return status
        time.sleep(0.1)
    return status


def _observe(supervisor: ServiceSupervisor, duration_s: float) -> None:
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        supervisor.monitor_once()
        time.sleep(0.1)


@contextmanager
def _workspace(*, keep: bool) -> Iterator[tuple[Path, ServicePaths]]:
    root = Path(tempfile.mkdtemp(prefix="conda-broker-dev-"))
    paths = ServicePaths(
        runtime_dir=root / "runtime" / "conda" / "broker",
        log_dir=root / "logs" / "conda" / "broker",
    )
    try:
        yield root, paths
    finally:
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
