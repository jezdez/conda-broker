"""Provider service conformance checks for development workflows."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import time
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from .paths import ServicePaths
from .registry import ServiceRegistry
from .state import StateStore
from .supervisor import ServiceSupervisor

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any

    from .models import CondaService, ServiceStatus

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


@dataclass
class ServiceValidation:
    """Static checks for one discovered service."""

    service: CondaService
    registry: ServiceRegistry
    result: ConformanceResult

    def run(self) -> None:
        service = self.service
        self.result.add("pass", "service.discovered", "service is discoverable")
        if service.summary.strip():
            self.result.add("pass", "service.summary", "summary is present")
        else:
            self.result.add("warn", "service.summary", "summary is empty")

        if service.runtime != "process":
            self.result.add(
                "fail",
                "runtime.supported",
                f"runtime {service.runtime!r} is not supported by this broker",
            )
            return
        self.result.add("pass", "runtime.process", "process runtime is supported")

        process = service.merged_process()
        self.result.add(
            "pass",
            "process.argv",
            "process argv is configured",
            argv=list(process.argv),
        )
        self.command("process.command", process.argv)

        if process.cwd is None:
            self.result.add("pass", "process.cwd", "service does not require a cwd")
        elif Path(process.cwd).exists():
            self.result.add(
                "pass", "process.cwd", "configured cwd exists", cwd=process.cwd
            )
        else:
            self.result.add(
                "fail",
                "process.cwd",
                "configured cwd does not exist",
                cwd=process.cwd,
            )

        if process.grace_period_s <= 30:
            self.result.add(
                "pass",
                "process.grace_period",
                "grace period is operator-friendly",
                seconds=process.grace_period_s,
            )
        else:
            self.result.add(
                "warn",
                "process.grace_period",
                "long grace periods slow down stop and restart workflows",
                seconds=process.grace_period_s,
            )

        for dependency in service.dependencies:
            if dependency in self.registry:
                self.result.add(
                    "pass",
                    "dependency.known",
                    f"dependency {dependency!r} is discoverable",
                    dependency=dependency,
                )
            else:
                self.result.add(
                    "fail",
                    "dependency.known",
                    f"dependency {dependency!r} is missing",
                    dependency=dependency,
                )

        self.health_check()
        self.endpoints()

    def health_check(self) -> None:
        check = self.service.health_check
        process = self.service.merged_process()
        self.result.add(
            "pass",
            "health.type",
            f"{check.type} health check is configured",
            type=check.type,
        )
        if check.timeout_s <= process.grace_period_s:
            self.result.add(
                "pass",
                "health.timeout",
                "health timeout is bounded by the stop grace period",
                timeout_s=check.timeout_s,
            )
        else:
            self.result.add(
                "warn",
                "health.timeout",
                "health timeout is longer than the stop grace period",
                timeout_s=check.timeout_s,
                grace_period_s=process.grace_period_s,
            )

        if check.endpoint:
            self.result.add(
                "pass",
                "health.endpoint",
                f"health check uses endpoint {check.endpoint!r}",
                endpoint=check.endpoint,
            )

        if check.type == "exec":
            self.command("health.exec.command", check.command)
        elif check.type == "tcp" and not check.endpoint and check.host is not None:
            self.loopback_host("health.tcp.host", check.host)
        elif check.type == "http" and not check.endpoint and check.url is not None:
            self.loopback_host("health.http.host", urlparse(check.url).hostname or "")

    def endpoints(self) -> None:
        if not self.service.endpoints:
            self.result.add(
                "skip", "endpoint.declared", "service declares no endpoints"
            )
            return

        for endpoint in self.service.endpoints:
            self.result.add(
                "pass",
                "endpoint.declared",
                f"endpoint {endpoint.name!r} is declared",
                endpoint=endpoint.name,
                protocol=endpoint.protocol,
            )
            self.loopback_host(f"endpoint.{endpoint.name}.host", endpoint.host)
            if endpoint.port is None:
                self.result.add(
                    "pass",
                    "endpoint.port",
                    "broker will allocate a dynamic port",
                    endpoint=endpoint.name,
                )
            else:
                self.result.add(
                    "pass",
                    "endpoint.port",
                    "endpoint uses a static port",
                    endpoint=endpoint.name,
                    port=endpoint.port,
                )
            if endpoint.port_env:
                self.result.add(
                    "pass",
                    "endpoint.port_env",
                    "service receives the endpoint port through a custom env var",
                    endpoint=endpoint.name,
                    env=endpoint.port_env,
                )
            if endpoint.url_env:
                self.result.add(
                    "pass",
                    "endpoint.url_env",
                    "service receives the endpoint URL through a custom env var",
                    endpoint=endpoint.name,
                    env=endpoint.url_env,
                )

    def command(self, name: str, argv: tuple[str, ...]) -> None:
        executable = argv[0]
        path = Path(executable)
        explicit_path = (
            path.is_absolute()
            or os.sep in executable
            or (os.altsep is not None and os.altsep in executable)
        )
        exists = (
            path.exists() if explicit_path else shutil.which(executable) is not None
        )
        if exists:
            self.result.add(
                "pass", name, "command appears executable", command=executable
            )
        else:
            self.result.add(
                "warn",
                name,
                "command was not found on PATH or as an absolute path",
                command=executable,
            )

    def loopback_host(self, name: str, host: str) -> None:
        if host == "localhost":
            loopback = True
        else:
            try:
                loopback = ip_address(host).is_loopback
            except ValueError:
                loopback = False
        if loopback:
            self.result.add("pass", name, "health endpoint is loopback", host=host)
        else:
            self.result.add(
                "warn",
                name,
                "health endpoint is not obviously loopback",
                host=host,
            )


@dataclass
class ConformanceScenario:
    """One service running in an isolated broker workspace."""

    service: CondaService
    registry: ServiceRegistry
    paths: ServicePaths
    result: ConformanceResult
    timeout_s: float
    state: StateStore = field(init=False)
    supervisor: ServiceSupervisor = field(init=False)

    def __post_init__(self) -> None:
        self.state = StateStore(self.paths)
        self.supervisor = ServiceSupervisor(self.registry, self.state, self.paths)

    def run(self, *, observe_s: float = 0.0) -> None:
        try:
            if self.result.scenario == "start-stop":
                self.start_stop(observe_s)
            elif self.result.scenario == "health":
                self.health()
            else:
                self.crash()
        finally:
            stopped = []
            try:
                stopped = self.supervisor.stop_services()
            finally:
                self.result.events = self.state.read_events(limit=50)
                self.result.logs = self.supervisor.logs.read_lines(
                    self.service.name, lines=20
                )
            if self.result.scenario == "start-stop":
                if self.result.logs:
                    self.result.add("pass", "logs.capture", "service wrote log output")
                else:
                    self.result.add("warn", "logs.capture", "service log is empty")
                if stopped and not stopped[0].running:
                    self.result.add("pass", "runtime.stop", "service stopped cleanly")

    def start_stop(self, observe_s: float) -> None:
        status = self.start("runtime.start", "service failed to start")
        if status is None:
            return
        self.result.status = status.to_dict()
        if status.running:
            self.result.add("pass", "runtime.start", "service started", pid=status.pid)
            self.check_endpoints(status)
        else:
            self.result.add(
                "fail",
                "runtime.start",
                "service did not remain running",
                state=status.state,
                exit_code=status.exit_code,
            )
        self.observe(observe_s)

    def health(self) -> None:
        status = self.start(
            "health.setup", "service failed to start before health check"
        )
        if status is None:
            return
        self.result.status = status.to_dict()
        if status.health == "healthy":
            self.result.add("pass", "health.observed", "health check reported healthy")
        elif status.health == "unknown":
            self.result.add("fail", "health.observed", "health check did not run")
        else:
            self.result.add(
                "fail", "health.observed", "health check reported unhealthy"
            )
        if status.ready:
            self.result.add("pass", "readiness.observed", "service reported ready")
        else:
            self.result.add("fail", "readiness.observed", "service was not ready")

    def crash(self) -> None:
        status = self.start(
            "crash.setup", "service failed to start before crash scenario"
        )
        if status is None:
            return
        if not status.running:
            self.result.add(
                "fail", "crash.setup", "service was not running before crash"
            )
            return
        process = self.supervisor.process(self.service.name)
        if process is None:
            self.result.add("fail", "crash.setup", "service process was not tracked")
            return
        process.kill()

        deadline = time.monotonic() + self.timeout_s
        final = status
        while time.monotonic() < deadline:
            self.supervisor.monitor_once()
            final = self.supervisor.status_many([self.service.name])[0]
            if self.service.restart_policy == "never" and not final.running:
                break
            if final.running and final.restart_count > status.restart_count:
                break
            time.sleep(0.1)
        self.result.status = final.to_dict()

        if self.service.restart_policy == "never":
            if not final.running and final.restart_count == 0:
                self.result.add(
                    "pass",
                    "crash.restart_policy",
                    "service stayed stopped as restart_policy=never requires",
                )
            else:
                self.result.add(
                    "fail",
                    "crash.restart_policy",
                    "service restarted despite restart_policy=never",
                )
        elif final.running and final.restart_count > status.restart_count:
            self.result.add(
                "pass",
                "crash.restart_policy",
                "service restarted after a crash",
                restart_count=final.restart_count,
            )
        else:
            self.result.add(
                "fail",
                "crash.restart_policy",
                "service did not restart after a crash before timeout",
                restart_policy=self.service.restart_policy,
            )

    def start(self, check: str, message: str) -> ServiceStatus | None:
        try:
            self.supervisor.start_services([self.service.name])
            deadline = time.monotonic() + self.timeout_s
            status = self.supervisor.status_many([self.service.name])[0]
            while time.monotonic() < deadline:
                self.supervisor.monitor_once()
                status = self.supervisor.status_many([self.service.name])[0]
                if status.running and status.health != "unknown":
                    return status
                if not status.running and status.state != "backing-off":
                    return status
                time.sleep(0.1)
            return status
        except Exception as exc:
            self.result.add(
                "fail",
                check,
                message,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return None

    def observe(self, duration_s: float) -> None:
        deadline = time.monotonic() + duration_s
        while time.monotonic() < deadline:
            self.supervisor.monitor_once()
            time.sleep(0.1)

    def check_endpoints(self, status: ServiceStatus) -> None:
        for endpoint in self.service.endpoints:
            data = status.endpoints.get(endpoint.name)
            if data is None:
                self.result.add(
                    "fail",
                    "endpoint.resolved",
                    f"endpoint {endpoint.name!r} was not reported in status",
                    endpoint=endpoint.name,
                )
                continue
            if data.get("port") is None:
                self.result.add(
                    "fail",
                    "endpoint.resolved",
                    f"endpoint {endpoint.name!r} has no resolved port",
                    endpoint=endpoint.name,
                )
                continue
            self.result.add(
                "pass",
                "endpoint.resolved",
                f"endpoint {endpoint.name!r} resolved",
                endpoint=endpoint.name,
                url=data.get("url"),
            )
            if self.endpoint_reachable(data):
                self.result.add(
                    "pass",
                    "endpoint.reachable",
                    f"endpoint {endpoint.name!r} accepted a connection",
                    endpoint=endpoint.name,
                    url=data.get("url"),
                )
            else:
                self.result.add(
                    "fail",
                    "endpoint.reachable",
                    f"endpoint {endpoint.name!r} was not reachable",
                    endpoint=endpoint.name,
                    url=data.get("url"),
                )

    def endpoint_reachable(self, endpoint: dict[str, object]) -> bool:
        protocol = endpoint.get("protocol")
        host = endpoint.get("host")
        port = endpoint.get("port")
        if not isinstance(host, str) or not isinstance(port, int):
            return False
        if protocol == "tcp":
            try:
                with socket.create_connection((host, port), timeout=1):
                    return True
            except OSError:
                return False
        if protocol == "http":
            url = endpoint.get("url")
            if not isinstance(url, str):
                return False
            try:
                with urllib.request.urlopen(url, timeout=1) as response:
                    return 200 <= response.status < 500
            except OSError:
                return False
        return False


@dataclass
class ConformanceSuite:
    """Run provider checks against a service registry."""

    registry: ServiceRegistry = field(default_factory=ServiceRegistry.discover)

    def validate(self, service_name: str) -> ConformanceResult:
        service = self.registry.get(service_name)
        result = ConformanceResult(service=service.name, command="validate")
        ServiceValidation(service, self.registry, result).run()
        return result

    def run(
        self,
        service_name: str,
        *,
        duration_s: float = 3.0,
        timeout_s: float = 5.0,
        keep: bool = False,
    ) -> ConformanceResult:
        return self.exercise(
            service_name,
            command="run",
            scenario="start-stop",
            timeout_s=timeout_s,
            observe_s=duration_s,
            keep=keep,
        )

    def test(
        self,
        service_name: str,
        *,
        scenario: str = "start-stop",
        timeout_s: float = 5.0,
        keep: bool = False,
    ) -> ConformanceResult:
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown conformance scenario: {scenario}")
        return self.exercise(
            service_name,
            command="test",
            scenario=scenario,
            timeout_s=timeout_s,
            keep=keep,
        )

    def report(
        self,
        service_name: str,
        *,
        timeout_s: float = 5.0,
        keep: bool = False,
    ) -> dict[str, object]:
        service = self.registry.get(service_name)
        results = [
            self.validate(service.name),
            self.run(
                service.name,
                duration_s=min(timeout_s, 3.0),
                timeout_s=timeout_s,
                keep=keep,
            ),
        ]
        for scenario in ("health", "crash"):
            results.append(
                self.test(
                    service.name,
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

    def exercise(
        self,
        service_name: str,
        *,
        command: str,
        scenario: str,
        timeout_s: float,
        observe_s: float = 0.0,
        keep: bool,
    ) -> ConformanceResult:
        service = self.registry.get(service_name)
        with self.workspace(keep=keep) as (root, paths):
            result = ConformanceResult(
                service=service.name,
                command=command,
                scenario=scenario,
                workspace=str(root),
                kept=keep,
            )
            ServiceValidation(service, self.registry, result).run()
            ConformanceScenario(
                service,
                self.registry,
                paths,
                result,
                timeout_s,
            ).run(observe_s=observe_s)
            return result

    @contextmanager
    def workspace(self, *, keep: bool) -> Iterator[tuple[Path, ServicePaths]]:
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
