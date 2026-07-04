"""Process supervision for conda service definitions."""

from __future__ import annotations

import socket
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .exceptions import RuntimeUnavailableError, UnknownServiceError
from .logs import LogManager
from .models import ServiceStatus, utc_now
from .runtimes import ProcessRuntime

HEALTHY_BACKOFF_RESET_S = 300.0

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import TextIO

    from .models import CondaService, EndpointStatus
    from .paths import ServicePaths
    from .registry import ServiceRegistry
    from .state import StateStore


@dataclass
class ManagedProcess:
    service: CondaService
    process: subprocess.Popen[str]
    log_file: TextIO
    started_at: str
    started_monotonic: float
    restart_count: int = 0
    backoff_s: float = 1.0
    stop_requested: bool = False
    health: str = "unknown"
    last_health_check: float = 0.0
    endpoints: dict[str, EndpointStatus] | None = None


@dataclass
class PendingRestart:
    service: CondaService
    due_at: float
    restart_count: int
    backoff_s: float


class ServiceSupervisor:
    """Run, observe, and restart local service processes."""

    def __init__(
        self,
        registry: ServiceRegistry,
        state: StateStore,
        paths: ServicePaths,
    ) -> None:
        self.registry = registry
        self.registry.validate_dependencies()
        self.state = state
        self.paths = paths
        self.logs = LogManager(paths)
        self._runtime = ProcessRuntime()
        self._managed: dict[str, ManagedProcess] = {}
        self._pending: dict[str, PendingRestart] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None

    def start_monitor(self) -> None:
        with self._lock:
            if self._monitor and self._monitor.is_alive():
                return
            self._stop.clear()
            self._monitor = threading.Thread(
                target=self._monitor_loop,
                name="conda-broker-monitor",
                daemon=True,
            )
            self._monitor.start()

    def shutdown(self) -> None:
        self._stop.set()
        self.stop_services()
        monitor = self._monitor
        if monitor and monitor.is_alive():
            monitor.join(timeout=2)

    def start_enabled_services(self) -> list[ServiceStatus]:
        enabled = self.state.enabled_services()
        known_enabled = [name for name in self.registry.names() if name in enabled]
        return self.start_services(known_enabled)

    def start_services(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        targets = list(names) if names is not None else self.registry.names()
        with self._lock:
            for name in targets:
                self._start_service(
                    name,
                    restart_count=0,
                    backoff_s=1.0,
                    visiting=(),
                )
            return self.status_many(targets)

    def stop_services(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        with self._lock:
            targets = list(names) if names is not None else list(self._managed)
            for name in targets:
                self._pending.pop(name, None)
                managed = self._managed.get(name)
                if managed is None:
                    if name not in self.registry:
                        raise UnknownServiceError(f"Unknown service: {name}")
                    continue
                managed.stop_requested = True
                exit_code = self._stop_managed_process(managed)
                if managed.process.poll() is not None:
                    self._close_managed(name, exit_code=exit_code)
                    self.state.emit("service.stopped", service=name)
            return self.status_many(targets)

    def restart_services(
        self,
        names: Iterable[str] | None = None,
    ) -> list[ServiceStatus]:
        targets = list(names) if names is not None else self.registry.names()
        self.stop_services(targets)
        return self.start_services(targets)

    def status_many(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        targets = list(names) if names is not None else self.registry.names()
        enabled = self.state.enabled_services()
        statuses = []
        for name in targets:
            service = self.registry.get(name)
            managed = self._managed.get(name)
            pending = self._pending.get(name)
            if managed is not None:
                running = managed.process.poll() is None
                ready = running and managed.health == "healthy"
                statuses.append(
                    ServiceStatus(
                        name=service.name,
                        summary=service.summary,
                        source=service.source,
                        runtime=service.runtime,
                        enabled=service.name in enabled,
                        state=_state_for(running=running, health=managed.health),
                        running=running,
                        pid=managed.process.pid if running else None,
                        exit_code=managed.process.returncode,
                        started_at=managed.started_at,
                        restart_count=managed.restart_count,
                        health=managed.health,
                        ready=ready,
                        endpoints=_endpoint_dict(
                            managed.endpoints or _unresolved_endpoints(service)
                        ),
                    )
                )
            elif pending is not None:
                statuses.append(
                    ServiceStatus(
                        name=service.name,
                        summary=service.summary,
                        source=service.source,
                        runtime=service.runtime,
                        enabled=service.name in enabled,
                        state="backing-off",
                        restart_count=pending.restart_count,
                        health="unknown",
                        endpoints=_endpoint_dict(_unresolved_endpoints(service)),
                    )
                )
            else:
                statuses.append(
                    ServiceStatus(
                        name=service.name,
                        summary=service.summary,
                        source=service.source,
                        runtime=service.runtime,
                        enabled=service.name in enabled,
                        state="stopped",
                        endpoints=_endpoint_dict(_unresolved_endpoints(service)),
                    )
                )
        return statuses

    def status(self, name: str | None = None) -> dict[str, object]:
        with self._lock:
            return {
                "broker": {"running": True},
                "services": [
                    status.to_dict()
                    for status in self.status_many([name] if name else None)
                ],
            }

    def is_running(self, name: str) -> bool:
        with self._lock:
            managed = self._managed.get(name)
            return bool(managed and managed.process.poll() is None)

    def is_ready(self, name: str) -> bool:
        with self._lock:
            managed = self._managed.get(name)
            return bool(
                managed
                and managed.process.poll() is None
                and managed.health == "healthy"
            )

    def wait_until_ready(self, name: str, *, timeout_s: float) -> ServiceStatus:
        deadline = time.monotonic() + timeout_s
        status = self.status_many([name])[0]
        while time.monotonic() < deadline:
            self.monitor_once()
            status = self.status_many([name])[0]
            if status.ready or (not status.running and status.state != "backing-off"):
                return status
            time.sleep(0.1)
        return status

    def _start_service(
        self,
        name: str,
        *,
        restart_count: int,
        backoff_s: float,
        visiting: tuple[str, ...],
    ) -> None:
        if name in visiting:
            cycle = " -> ".join((*visiting, name))
            raise RuntimeError(f"Service dependency cycle: {cycle}")
        service = self.registry.get(name)
        if service.runtime != "process":
            raise RuntimeUnavailableError(f"Runtime {service.runtime!r} is not active")
        managed = self._managed.get(name)
        if managed and managed.process.poll() is None:
            return
        for dependency in service.dependencies:
            self._start_service(
                dependency,
                restart_count=0,
                backoff_s=1.0,
                visiting=(*visiting, name),
            )
        self._pending.pop(name, None)
        endpoints, endpoint_env = self._resolve_endpoints(service)
        log_file = self.logs.open_for_service(name)
        try:
            process = self._runtime.start(service, log_file, extra_env=endpoint_env)
        except Exception:
            log_file.close()
            raise
        self._managed[name] = ManagedProcess(
            service=service,
            process=process,
            log_file=log_file,
            started_at=utc_now(),
            started_monotonic=time.monotonic(),
            restart_count=restart_count,
            backoff_s=backoff_s,
            endpoints=endpoints,
        )
        self.state.emit(
            "service.started",
            service=name,
            data={
                "pid": process.pid,
                "restart_count": restart_count,
                "endpoints": _endpoint_dict(endpoints),
            },
        )

    def _resolve_endpoints(
        self,
        service: CondaService,
    ) -> tuple[dict[str, EndpointStatus], dict[str, str]]:
        endpoints: dict[str, EndpointStatus] = {}
        env = {"CONDA_BROKER_SERVICE_NAME": service.name}
        for endpoint in service.endpoints:
            port = endpoint.port
            if port is None:
                port = _allocate_local_port(endpoint.host)
            resolved = endpoint.resolve(port=port)
            endpoints[endpoint.name] = resolved
            env.update(_endpoint_env(endpoint.name, resolved))
            if endpoint.port_env and resolved.port is not None:
                env[endpoint.port_env] = str(resolved.port)
            if endpoint.url_env and resolved.url is not None:
                env[endpoint.url_env] = resolved.url
        return endpoints, env

    def _close_managed(self, name: str, *, exit_code: int | None) -> None:
        managed = self._managed.pop(name, None)
        if managed is None:
            return
        try:
            managed.log_file.flush()
        finally:
            managed.log_file.close()
        managed.process.returncode = exit_code

    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            self.monitor_once()
            self._stop.wait(1.0)

    def monitor_once(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._process_pending_restarts(now)
            for name, managed in list(self._managed.items()):
                returncode = managed.process.poll()
                if returncode is not None:
                    self._handle_exit(name, managed, returncode)
                    continue
                self._check_managed_health(name, managed, now)

    def _process_pending_restarts(self, now: float) -> None:
        for name, pending in list(self._pending.items()):
            if pending.due_at > now:
                continue
            self._pending.pop(name, None)
            self._start_service(
                name,
                restart_count=pending.restart_count,
                backoff_s=pending.backoff_s,
                visiting=(),
            )

    def _handle_exit(
        self,
        name: str,
        managed: ManagedProcess,
        returncode: int,
    ) -> None:
        self._close_managed(name, exit_code=returncode)
        if managed.stop_requested:
            return
        self.state.emit(
            "service.exited",
            service=name,
            data={"exit_code": returncode},
        )
        should_restart = managed.service.restart_policy == "always" or (
            managed.service.restart_policy == "on-failure" and returncode != 0
        )
        if not should_restart:
            return
        self._schedule_restart(
            name,
            managed,
            reason="exit",
            data={"exit_code": returncode},
        )

    def _schedule_restart(
        self,
        name: str,
        managed: ManagedProcess,
        *,
        reason: str,
        data: dict[str, object] | None = None,
    ) -> None:
        runtime_s = time.monotonic() - managed.started_monotonic
        delay_s = 1.0 if runtime_s >= HEALTHY_BACKOFF_RESET_S else managed.backoff_s
        next_backoff = min(60.0, delay_s * 2)
        self._pending[name] = PendingRestart(
            service=managed.service,
            due_at=time.monotonic() + delay_s,
            restart_count=managed.restart_count + 1,
            backoff_s=next_backoff,
        )
        self.state.emit(
            "service.restart_scheduled",
            service=name,
            data={"delay_s": delay_s, "reason": reason, **(data or {})},
        )

    def _check_managed_health(
        self,
        name: str,
        managed: ManagedProcess,
        now: float,
    ) -> None:
        check = managed.service.health_check
        if now - managed.last_health_check < check.interval_s:
            return
        managed.last_health_check = now
        healthy = self._health_is_ok(managed)
        if healthy:
            managed.health = "healthy"
            return
        if now - managed.started_monotonic < check.start_period_s:
            managed.health = "unknown"
            return
        managed.health = "unhealthy"
        if managed.service.restart_policy == "never":
            return
        self.state.emit("service.unhealthy", service=name)
        exit_code = self._stop_managed_process(managed)
        if managed.process.poll() is None:
            return
        self._close_managed(name, exit_code=exit_code)
        self._schedule_restart(
            name,
            managed,
            reason="health",
            data={"exit_code": exit_code},
        )

    def _stop_managed_process(self, managed: ManagedProcess) -> int | None:
        self._runtime.stop(managed.process, managed.service)
        try:
            managed.process.wait(
                timeout=managed.service.merged_process().grace_period_s
            )
        except subprocess.TimeoutExpired:
            self._runtime.kill(managed.process)
            try:
                managed.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                return managed.process.poll()
        return managed.process.returncode

    def _health_is_ok(self, managed: ManagedProcess) -> bool:
        check = managed.service.health_check
        if check.type == "process":
            return managed.process.poll() is None
        if check.type == "tcp":
            endpoint = _health_endpoint(managed) if check.endpoint else None
            host = endpoint.host if endpoint else check.host
            port = endpoint.port if endpoint else check.port
            if host is None or port is None:
                return False
            try:
                with socket.create_connection(
                    (host, port),
                    timeout=check.timeout_s,
                ):
                    return True
            except OSError:
                return False
        if check.type == "http":
            endpoint = _health_endpoint(managed) if check.endpoint else None
            url = endpoint.url if endpoint else check.url
            if url is None:
                return False
            try:
                with urllib.request.urlopen(url, timeout=check.timeout_s) as res:
                    return 200 <= res.status < 500
            except OSError:
                return False
        if check.type == "exec":
            try:
                result = subprocess.run(
                    check.command,
                    timeout=check.timeout_s,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.TimeoutExpired):
                return False
            return result.returncode == 0
        return False


def _health_endpoint(managed: ManagedProcess) -> EndpointStatus | None:
    endpoint_name = managed.service.health_check.endpoint
    if endpoint_name is None or managed.endpoints is None:
        return None
    return managed.endpoints.get(endpoint_name)


def _unresolved_endpoints(service: CondaService) -> dict[str, EndpointStatus]:
    return {endpoint.name: endpoint.resolve() for endpoint in service.endpoints}


def _endpoint_dict(
    endpoints: dict[str, EndpointStatus],
) -> dict[str, dict[str, object]]:
    return {name: endpoint.to_dict() for name, endpoint in endpoints.items()}


def _state_for(*, running: bool, health: str) -> str:
    if not running:
        return "failed"
    if health == "healthy":
        return "ready"
    if health == "unhealthy":
        return "degraded"
    return "starting"


def _allocate_local_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


def _endpoint_env(name: str, endpoint: EndpointStatus) -> dict[str, str]:
    slug = "".join(char if char.isalnum() else "_" for char in name.upper()).strip("_")
    if not slug:
        slug = "DEFAULT"
    prefix = f"CONDA_BROKER_ENDPOINT_{slug}"
    env = {f"{prefix}_HOST": endpoint.host, f"{prefix}_PROTOCOL": endpoint.protocol}
    if endpoint.port is not None:
        env[f"{prefix}_PORT"] = str(endpoint.port)
    if endpoint.url is not None:
        env[f"{prefix}_URL"] = endpoint.url
    return env
