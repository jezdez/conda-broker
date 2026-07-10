"""Process supervision for conda service definitions."""

from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
import traceback
import urllib.request
import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import psutil

from .exceptions import RuntimeUnavailableError, UnknownServiceError
from .logs import LogManager
from .models import ServiceName, ServiceStatus
from .runtimes import ProcessRuntime

HEALTHY_BACKOFF_RESET_S = 300.0

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import CondaService, EndpointStatus
    from .paths import ServicePaths
    from .registry import ServiceRegistry
    from .state import StateStore


@dataclass
class EndpointBindings:
    """Resolved service endpoints and their launch environment."""

    endpoints: dict[str, EndpointStatus]
    environment: dict[str, str]
    reservations: list[socket.socket] = field(default_factory=list, repr=False)

    @classmethod
    def allocate(cls, service: CondaService) -> EndpointBindings:
        endpoints: dict[str, EndpointStatus] = {}
        environment = {"CONDA_BROKER_SERVICE_NAME": service.name}
        reservations: list[socket.socket] = []
        try:
            for endpoint in service.endpoints:
                port = endpoint.port
                if port is None:
                    reservation = cls.reserve_port(endpoint.host)
                    reservations.append(reservation)
                    port = int(reservation.getsockname()[1])
                resolved = endpoint.resolve(port=port)
                endpoints[endpoint.name] = resolved
                environment.update(cls.endpoint_environment(endpoint.name, resolved))
                if endpoint.port_env and resolved.port is not None:
                    environment[endpoint.port_env] = str(resolved.port)
                if endpoint.url_env and resolved.url is not None:
                    environment[endpoint.url_env] = resolved.url
        except Exception:
            for reservation in reservations:
                reservation.close()
            raise
        return cls(endpoints, environment, reservations)

    @staticmethod
    def reserve_port(host: str) -> socket.socket:
        error: OSError | None = None
        for family, socktype, proto, _, address in socket.getaddrinfo(
            host,
            0,
            type=socket.SOCK_STREAM,
        ):
            reservation = socket.socket(family, socktype, proto)
            try:
                reservation.bind(address)
            except OSError as exc:
                error = exc
                reservation.close()
                continue
            return reservation
        raise OSError(f"Could not allocate a local port for {host!r}") from error

    @staticmethod
    def endpoint_environment(
        name: str,
        endpoint: EndpointStatus,
    ) -> dict[str, str]:
        slug = ServiceName(name).environment_slug
        prefix = f"CONDA_BROKER_ENDPOINT_{slug}"
        environment = {
            f"{prefix}_HOST": endpoint.host,
            f"{prefix}_PROTOCOL": endpoint.protocol,
        }
        if endpoint.port is not None:
            environment[f"{prefix}_PORT"] = str(endpoint.port)
        if endpoint.url is not None:
            environment[f"{prefix}_URL"] = endpoint.url
        return environment

    def release(self) -> None:
        for reservation in self.reservations:
            reservation.close()
        self.reservations.clear()


@dataclass
class ManagedProcess:
    """One launched service process and its supervision state."""

    service: CondaService
    process: subprocess.Popen[bytes]
    log_thread: threading.Thread
    runtime: ProcessRuntime = field(repr=False)
    state_store: StateStore = field(repr=False)
    instance_id: str = field(repr=False)
    started_at: str
    started_monotonic: float
    restart_count: int = 0
    backoff_s: float = 1.0
    stop_reason: str | None = None
    health: str = "unknown"
    healthy_since_monotonic: float | None = None
    last_health_check: float = 0.0
    endpoints: dict[str, EndpointStatus] | None = None
    health_env: dict[str, str] = field(default_factory=dict, repr=False)
    health_cwd: str | None = None
    operation_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def launch(
        cls,
        service: CondaService,
        *,
        runtime: ProcessRuntime,
        logs: LogManager,
        state_store: StateStore,
        instance_id: str,
        restart_count: int,
        backoff_s: float,
    ) -> ManagedProcess:
        bindings = EndpointBindings.allocate(service)
        bindings.release()
        process = runtime.start(service, extra_env=bindings.environment)
        log_thread: threading.Thread | None = None
        managed: ManagedProcess | None = None
        try:
            if process.stdout is None:
                raise RuntimeError(
                    f"Service {service.name!r} did not expose process output"
                )
            log_thread = logs.start_capture(service.name, process.stdout)
            process_spec = service.merged_process()
            managed = cls(
                service=service,
                process=process,
                log_thread=log_thread,
                runtime=runtime,
                state_store=state_store,
                instance_id=instance_id,
                started_at=datetime.now(timezone.utc).isoformat(),
                started_monotonic=time.monotonic(),
                restart_count=restart_count,
                backoff_s=backoff_s,
                endpoints=bindings.endpoints,
                health_env={
                    **os.environ,
                    **process_spec.env,
                    **bindings.environment,
                },
                health_cwd=process_spec.cwd,
            )
            try:
                create_time = psutil.Process(process.pid).create_time()
            except psutil.NoSuchProcess:
                create_time = None
            except psutil.Error as exc:
                raise RuntimeError(
                    f"Could not record process identity for service {service.name!r}"
                ) from exc
            state_store.set_managed_process(
                service.name,
                {
                    "pid": process.pid,
                    "create_time": create_time,
                    "instance_id": instance_id,
                },
            )
            state_store.emit(
                "service.started",
                service=service.name,
                data={
                    "pid": process.pid,
                    "restart_count": restart_count,
                    "endpoints": managed.endpoint_dict(),
                },
            )
            return managed
        except BaseException:
            if managed is not None:
                managed.stop_reason = "start-failed"
            with suppress(Exception):
                runtime.kill(process)
            with suppress(Exception):
                process.wait(timeout=2)
            if process.stdout is not None:
                with suppress(OSError, ValueError):
                    process.stdout.close()
            if log_thread is not None:
                log_thread.join(timeout=2)
            with suppress(Exception):
                state_store.set_managed_process(
                    service.name,
                    None,
                    instance_id=instance_id,
                )
            raise

    @property
    def running(self) -> bool:
        return self.process.poll() is None

    @property
    def ready(self) -> bool:
        return self.running and self.health == "healthy" and not self.stop_reason

    def endpoint_dict(self) -> dict[str, dict[str, object]]:
        return {
            name: endpoint.to_dict()
            for name, endpoint in (self.endpoints or {}).items()
        }

    def status(self, *, enabled: bool) -> ServiceStatus:
        running = self.running
        if self.stop_reason:
            state = "stopping"
        elif not running:
            state = "failed"
        elif self.health == "healthy":
            state = "ready"
        elif self.health == "unhealthy":
            state = "degraded"
        else:
            state = "starting"
        return ServiceStatus(
            name=self.service.name,
            summary=self.service.summary,
            source=self.service.source,
            runtime=self.service.runtime,
            enabled=enabled,
            state=state,
            running=running,
            pid=self.process.pid if running else None,
            exit_code=self.process.returncode,
            started_at=self.started_at,
            restart_count=self.restart_count,
            health=self.health,
            ready=self.ready,
            endpoints=(self.endpoint_dict() or self.service.endpoint_statuses()),
        )

    def check_health(self) -> bool:
        check = self.service.health_check
        if check.type == "process":
            return self.running
        if check.type == "tcp":
            endpoint = self.health_endpoint() if check.endpoint else None
            host = endpoint.host if endpoint else check.host
            port = endpoint.port if endpoint else check.port
            if host is None or port is None:
                return False
            try:
                with socket.create_connection((host, port), timeout=check.timeout_s):
                    return True
            except OSError:
                return False
        if check.type == "http":
            endpoint = self.health_endpoint() if check.endpoint else None
            url = endpoint.url if endpoint else check.url
            if url is None:
                return False
            try:
                with urllib.request.urlopen(url, timeout=check.timeout_s) as response:
                    return 200 <= response.status < 400
            except (OSError, ValueError):
                return False
        if check.type == "exec":
            try:
                result = subprocess.run(
                    check.command,
                    timeout=check.timeout_s,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    cwd=self.health_cwd,
                    env=self.health_env,
                )
            except (OSError, subprocess.TimeoutExpired):
                return False
            return result.returncode == 0
        return False

    def health_endpoint(self) -> EndpointStatus | None:
        endpoint_name = self.service.health_check.endpoint
        if endpoint_name is None or self.endpoints is None:
            return None
        return self.endpoints.get(endpoint_name)

    def stop(self) -> int | None:
        grace_period_s = self.service.merged_process().grace_period_s
        deadline = time.monotonic() + grace_period_s
        self.runtime.stop(self.process, self.service)
        try:
            self.process.wait(timeout=grace_period_s)
        except subprocess.TimeoutExpired:
            pass
        while self.runtime.is_active(self.process) and time.monotonic() < deadline:
            time.sleep(0.05)
        if self.runtime.is_active(self.process):
            self.runtime.kill(self.process)
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
        kill_deadline = time.monotonic() + 2
        while self.runtime.is_active(self.process) and time.monotonic() < kill_deadline:
            time.sleep(0.05)
        if self.runtime.is_active(self.process):
            raise RuntimeError(
                f"Could not terminate process tree for {self.service.name!r}"
            )
        return self.process.returncode

    def kill(self) -> None:
        """Immediately terminate the managed process tree."""
        self.runtime.kill(self.process)

    def close(self, *, exit_code: int | None) -> None:
        self.log_thread.join(timeout=2)
        if self.log_thread.is_alive() and self.process.stdout is not None:
            with suppress(OSError, ValueError):
                self.process.stdout.close()
            self.log_thread.join(timeout=1)
        self.process.returncode = exit_code
        self.state_store.set_managed_process(
            self.service.name,
            None,
            instance_id=self.instance_id,
        )


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
        *,
        instance_id: str | None = None,
        runtime: ProcessRuntime | None = None,
    ) -> None:
        self.registry = registry
        self.registry.validate_dependencies()
        self.state = state
        self.paths = paths
        self.instance_id = instance_id or uuid.uuid4().hex
        self.logs = LogManager(paths)
        self.runtime = runtime or ProcessRuntime()
        self._managed: dict[str, ManagedProcess] = {}
        self._pending: dict[str, PendingRestart] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._monitor: threading.Thread | None = None

    @staticmethod
    def matching_process(record: dict[str, object]) -> psutil.Process | None:
        try:
            pid = int(str(record["pid"]))
            create_time = float(str(record["create_time"]))
            process = psutil.Process(pid)
            if abs(process.create_time() - create_time) > 0.01:
                return None
            return process
        except (KeyError, TypeError, ValueError, psutil.Error):
            return None

    @staticmethod
    def terminate_process_tree(process: psutil.Process) -> None:
        try:
            processes = [*process.children(recursive=True), process]
        except psutil.Error:
            processes = [process]
        for candidate in processes:
            try:
                candidate.terminate()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(processes, timeout=2)
        for candidate in alive:
            try:
                candidate.kill()
            except psutil.Error:
                pass
        _, alive = psutil.wait_procs(alive, timeout=2)
        if alive:
            pids = ", ".join(str(candidate.pid) for candidate in alive)
            raise RuntimeError(f"Could not terminate stale service processes: {pids}")

    def reconcile_stale_processes(self) -> None:
        """Terminate service processes left by a previous broker instance."""
        for name, record in self.state.managed_processes().items():
            record_instance = str(record.get("instance_id", ""))
            if record_instance == self.instance_id:
                continue
            process = self.matching_process(record)
            if process is not None:
                self.terminate_process_tree(process)
                self.state.emit(
                    "service.orphan_reaped",
                    service=name,
                    data={"pid": process.pid, "instance_id": record_instance},
                )
            self.state.set_managed_process(
                name,
                None,
                instance_id=record_instance or None,
            )

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
        with self._lock:
            self._pending.clear()
        self.stop_services()
        monitor = self._monitor
        if monitor and monitor.is_alive():
            monitor.join(timeout=2)

    def process(self, name: str) -> ManagedProcess | None:
        """Return the currently managed process for one service."""
        with self._lock:
            return self._managed.get(name)

    @property
    def monitor_running(self) -> bool:
        return bool(self._monitor and self._monitor.is_alive())

    def start_enabled_services(self) -> list[ServiceStatus]:
        enabled = self.state.enabled_services()
        known_enabled = [name for name in self.registry.names() if name in enabled]
        statuses = []
        for name in known_enabled:
            try:
                statuses.extend(self.start_services([name]))
            except Exception as exc:
                self.state.emit(
                    "service.start_failed",
                    service=name,
                    message=str(exc),
                    data={
                        "reason": "autostart",
                        "error_type": type(exc).__name__,
                    },
                )
        return statuses

    def start_services(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        targets = list(names) if names is not None else self.registry.names()
        launch_order = self.registry.startup_order(targets)
        for service in launch_order:
            if service.runtime != "process":
                raise RuntimeUnavailableError(
                    f"Runtime {service.runtime!r} is not active"
                )
        started: list[str] = []
        try:
            with self._lock:
                existing = dict(self._managed)
                try:
                    for service in launch_order:
                        self.ensure_started(service)
                    return self.status_many(targets)
                except BaseException:
                    started = [
                        name
                        for name, managed in self._managed.items()
                        if existing.get(name) is not managed
                    ]
                    for name in started:
                        self._managed[name].stop_reason = "start-rollback"
                    raise
        except BaseException:
            with suppress(Exception):
                self.stop_services(started)
            raise

    def start_services_with_ownership(
        self,
        names: Iterable[str],
    ) -> tuple[list[ServiceStatus], list[str]]:
        """Start services and report which requested services were launched."""
        targets = list(names)
        with self._lock:
            already_running = {name for name in targets if self.is_running(name)}
            statuses = self.start_services(targets)
        started = [
            status.name
            for status in statuses
            if status.running and status.name not in already_running
        ]
        return statuses, started

    def stop_services(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        targets = list(names) if names is not None else None
        with self._lock:
            resolved_targets = targets if targets is not None else list(self._managed)
            managed_processes: list[tuple[str, ManagedProcess]] = []
            for name in resolved_targets:
                self._pending.pop(name, None)
                managed = self._managed.get(name)
                if managed is None:
                    if name not in self.registry:
                        raise UnknownServiceError(f"Unknown service: {name}")
                    continue
                managed.stop_reason = "user"
                managed_processes.append((name, managed))

        errors: list[Exception] = []
        for name, managed in managed_processes:
            try:
                with managed.operation_lock:
                    exit_code = managed.stop()
            except Exception as exc:
                errors.append(exc)
                with suppress(Exception):
                    self.state.emit(
                        "service.stop_failed",
                        service=name,
                        message=str(exc),
                        data={"error_type": type(exc).__name__},
                    )
                continue
            with self._lock:
                current = self._managed.get(name)
                if current is managed and not managed.running:
                    self._managed.pop(name)
                    managed.close(exit_code=exit_code)
                    self.state.emit("service.stopped", service=name)
        if errors:
            raise errors[0]
        return self.status_many(resolved_targets)

    def restart_services(
        self,
        names: Iterable[str] | None = None,
    ) -> list[ServiceStatus]:
        targets = list(names) if names is not None else self.registry.names()
        self.stop_services(targets)
        return self.start_services(targets)

    def status_many(self, names: Iterable[str] | None = None) -> list[ServiceStatus]:
        with self._lock:
            targets = list(names) if names is not None else self.registry.names()
            enabled = self.state.enabled_services()
            statuses = []
            for name in targets:
                service = self.registry.get(name)
                managed = self._managed.get(name)
                pending = self._pending.get(name)
                if managed is not None:
                    statuses.append(managed.status(enabled=service.name in enabled))
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
                            endpoints=service.endpoint_statuses(),
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
                            endpoints=service.endpoint_statuses(),
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
            return bool(managed and managed.running)

    def is_ready(self, name: str) -> bool:
        with self._lock:
            managed = self._managed.get(name)
            return bool(managed and managed.ready)

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

    def ensure_started(
        self,
        service: CondaService,
        *,
        restart_count: int = 0,
        backoff_s: float = 1.0,
    ) -> None:
        """Ensure one already-resolved service has a managed process."""
        with self._lock:
            if service.runtime != "process":
                raise RuntimeUnavailableError(
                    f"Runtime {service.runtime!r} is not active"
                )
            managed = self._managed.get(service.name)
            if managed:
                returncode = managed.process.poll()
                if returncode is None:
                    if managed.stop_reason:
                        raise RuntimeError(
                            f"Service {service.name!r} is currently stopping"
                        )
                    return
                self._managed.pop(service.name)
                managed.close(exit_code=returncode)
                if not managed.stop_reason:
                    self.state.emit(
                        "service.exited",
                        service=service.name,
                        data={"exit_code": returncode},
                    )
            self._pending.pop(service.name, None)
            self._managed[service.name] = ManagedProcess.launch(
                service,
                runtime=self.runtime,
                logs=self.logs,
                state_store=self.state,
                instance_id=self.instance_id,
                restart_count=restart_count,
                backoff_s=backoff_s,
            )

    def _monitor_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.monitor_once()
            except Exception as exc:
                traceback.print_exc()
                try:
                    self.state.emit(
                        "broker.monitor_error",
                        message=str(exc),
                        data={"error_type": type(exc).__name__},
                    )
                except Exception:
                    traceback.print_exc()
            self._stop.wait(1.0)

    def monitor_once(self) -> None:
        now = time.monotonic()
        self.start_due_restarts(now)
        with self._lock:
            managed_processes = list(self._managed.items())
        for name, managed in managed_processes:
            returncode = managed.process.poll()
            if returncode is not None:
                with self._lock:
                    if self._managed.get(name) is managed:
                        self.record_exit(name, managed, returncode)
                continue
            with self._lock:
                if self._managed.get(name) is not managed or managed.stop_reason:
                    continue
                check = managed.service.health_check
                if now - managed.last_health_check < check.interval_s:
                    continue
                managed.last_health_check = now
            healthy = managed.check_health()
            self.record_health(name, managed, now, healthy)

    def start_due_restarts(self, now: float) -> None:
        """Launch service restarts whose backoff period has elapsed."""
        with self._lock:
            due = [
                (name, pending)
                for name, pending in self._pending.items()
                if pending.due_at <= now
            ]
        for name, pending in due:
            try:
                with self._lock:
                    if self._pending.get(name) is not pending:
                        continue
                    self._pending.pop(name, None)
                    launch_order = self.registry.startup_order([name])
                    for service in launch_order:
                        if service.runtime != "process":
                            raise RuntimeUnavailableError(
                                f"Runtime {service.runtime!r} is not active"
                            )
                    for service in launch_order:
                        self.ensure_started(
                            service,
                            restart_count=(
                                pending.restart_count if service.name == name else 0
                            ),
                            backoff_s=(
                                pending.backoff_s if service.name == name else 1.0
                            ),
                        )
            except Exception as exc:
                delay_s = min(60.0, pending.backoff_s)
                with self._lock:
                    self._pending[name] = PendingRestart(
                        service=pending.service,
                        due_at=time.monotonic() + delay_s,
                        restart_count=pending.restart_count + 1,
                        backoff_s=min(60.0, delay_s * 2),
                    )
                self.state.emit(
                    "service.start_failed",
                    service=name,
                    message=str(exc),
                    data={
                        "delay_s": delay_s,
                        "error_type": type(exc).__name__,
                    },
                )

    def record_exit(
        self,
        name: str,
        managed: ManagedProcess,
        returncode: int,
    ) -> None:
        self._managed.pop(name, None)
        managed.close(exit_code=returncode)
        if managed.stop_reason:
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
        self.schedule_restart(
            name,
            managed,
            reason="exit",
            data={"exit_code": returncode},
        )

    def schedule_restart(
        self,
        name: str,
        managed: ManagedProcess,
        *,
        reason: str,
        data: dict[str, object] | None = None,
        healthy_runtime_s: float | None = None,
    ) -> None:
        if healthy_runtime_s is None:
            healthy_since = managed.healthy_since_monotonic
            healthy_runtime_s = (
                time.monotonic() - healthy_since if healthy_since is not None else 0.0
            )
        delay_s = (
            1.0 if healthy_runtime_s >= HEALTHY_BACKOFF_RESET_S else managed.backoff_s
        )
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

    def record_health(
        self,
        name: str,
        managed: ManagedProcess,
        now: float,
        healthy: bool,
    ) -> None:
        with self._lock:
            if self._managed.get(name) is not managed or managed.stop_reason:
                return
            check = managed.service.health_check
            if healthy:
                previous = managed.health
                managed.health = "healthy"
                if previous != "healthy":
                    managed.healthy_since_monotonic = now
                    self.state.emit("service.healthy", service=name)
                return
            if now - managed.started_monotonic < check.start_period_s:
                managed.health = "unknown"
                return
            previous = managed.health
            healthy_since = managed.healthy_since_monotonic
            healthy_runtime_s = (
                now - healthy_since if healthy_since is not None else 0.0
            )
            managed.health = "unhealthy"
            managed.healthy_since_monotonic = None
            if previous != "unhealthy":
                self.state.emit("service.unhealthy", service=name)
            if managed.service.restart_policy == "never":
                return
            managed.stop_reason = "health"

        with managed.operation_lock:
            exit_code = managed.stop()
        with self._lock:
            if self._managed.get(name) is not managed:
                return
            if managed.running:
                managed.stop_reason = None
                return
            stop_reason = managed.stop_reason
            self._managed.pop(name)
            managed.close(exit_code=exit_code)
            if stop_reason == "health":
                self.schedule_restart(
                    name,
                    managed,
                    reason="health",
                    data={"exit_code": exit_code},
                    healthy_runtime_s=healthy_runtime_s,
                )
            elif stop_reason == "user":
                self.state.emit("service.stopped", service=name)
