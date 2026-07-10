"""Tests for real subprocess supervision."""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import TYPE_CHECKING

import psutil
import pytest

import conda_broker.supervisor as supervisor_module
from conda_broker.exceptions import RuntimeUnavailableError
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry
from conda_broker.runtimes import process as process_runtime
from conda_broker.runtimes.process import ProcessRuntime
from conda_broker.state import StateStore
from conda_broker.supervisor import ManagedProcess, ServiceSupervisor

if TYPE_CHECKING:
    from pathlib import Path

    from conda_broker.paths import ServicePaths


def _sleeping_service(name: str, *, dependencies: tuple[str, ...] = ()) -> CondaService:
    return CondaService(
        name=name,
        summary=f"{name} service",
        source="tests",
        dependencies=dependencies,
        process=ProcessSpec(
            argv=(
                sys.executable,
                "-c",
                "import time; print('ready', flush=True); time.sleep(30)",
            ),
            grace_period_s=1,
        ),
    )


def require_process(supervisor: ServiceSupervisor, name: str) -> ManagedProcess:
    managed = supervisor.process(name)
    assert managed is not None
    return managed


def _flaky_service(
    name: str,
    count_file: Path,
    *,
    restart_policy: str,
) -> CondaService:
    code = (
        "import pathlib, sys, time; "
        f"p = pathlib.Path({str(count_file)!r}); "
        "n = int(p.read_text()) if p.exists() else 0; "
        "p.write_text(str(n + 1)); "
        "sys.exit(7) if n == 0 else time.sleep(30)"
    )
    return CondaService(
        name=name,
        summary=f"{name} service",
        source="tests",
        restart_policy=restart_policy,
        process=ProcessSpec(argv=(sys.executable, "-c", code), grace_period_s=1),
    )


def _http_service(name: str) -> CondaService:
    code = (
        "import http.server\n"
        "import os\n"
        "port = int(os.environ['PORT'])\n"
        "url = os.environ['URL']\n"
        "class Handler(http.server.BaseHTTPRequestHandler):\n"
        "    def do_GET(self):\n"
        "        self.send_response(200)\n"
        "        self.end_headers()\n"
        "        self.wfile.write(b'ok')\n"
        "    def log_message(self, *args):\n"
        "        pass\n"
        "print(f'serving {port} {url}', flush=True)\n"
        "http.server.ThreadingHTTPServer(\n"
        "    ('127.0.0.1', port), Handler\n"
        ").serve_forever()\n"
    )
    return CondaService(
        name=name,
        summary=f"{name} API",
        source="tests",
        process=ProcessSpec(argv=(sys.executable, "-c", code), grace_period_s=1),
        health_check=HealthCheck(
            type="http",
            endpoint="default",
            interval_s=0.05,
            timeout_s=1,
        ),
        endpoints=(
            EndpointSpec(
                protocol="http",
                path="/health",
                port_env="PORT",
                url_env="URL",
            ),
        ),
    )


def _process_is_alive(pid: int) -> bool:
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


@pytest.mark.parametrize(
    ("force", "expected"),
    [
        (False, ["taskkill", "/PID", "42", "/T"]),
        (True, ["taskkill", "/PID", "42", "/T", "/F"]),
    ],
)
def test_windows_taskkill_targets_process_tree(
    monkeypatch,
    force: bool,
    expected: list[str],
) -> None:
    commands: list[list[str]] = []

    class Result:
        returncode = 0

    def run(command, **kwargs):
        commands.append(command)
        return Result()

    monkeypatch.setattr(process_runtime.subprocess, "run", run)

    assert ProcessRuntime.taskkill(42, force=force) is True
    assert commands == [expected]


def test_supervisor_start_stop_real_process(service_paths: ServicePaths) -> None:
    service = _sleeping_service("sleeper")
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        statuses = supervisor.start_services(["sleeper"])
        assert statuses[0].running is True
        assert supervisor.is_running("sleeper") is True

        deadline = time.monotonic() + 3
        lines = []
        while time.monotonic() < deadline:
            lines = supervisor.logs.read_lines("sleeper", lines=10)
            if "ready" in lines:
                break
            time.sleep(0.1)
        assert "ready" in lines
    finally:
        statuses = supervisor.stop_services(["sleeper"])

    assert statuses[0].running is False
    assert supervisor.is_running("sleeper") is False


def test_supervisor_stops_process_tree(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    child_pid_file = tmp_path / "child.pid"
    code = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_file)!r}).write_text(str(child.pid)); "
        "time.sleep(30)"
    )
    service = CondaService(
        name="process-tree",
        summary="Process tree",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", code),
            grace_period_s=1,
        ),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        supervisor.start_services([service.name])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not child_pid_file.exists():
            time.sleep(0.05)
        child_pid = int(child_pid_file.read_text())

        supervisor.stop_services([service.name])

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and _process_is_alive(child_pid):
            time.sleep(0.05)
        assert _process_is_alive(child_pid) is False
    finally:
        supervisor.stop_services([service.name])


def test_stop_services_continues_after_one_stop_fails(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    first = _sleeping_service("first")
    second = _sleeping_service("second")
    supervisor = ServiceSupervisor(
        ServiceRegistry([first, second]),
        StateStore(service_paths),
        service_paths,
    )
    original_stop = ManagedProcess.stop

    def fail_first(managed: ManagedProcess) -> int | None:
        if managed.service.name == first.name:
            raise RuntimeError("stop failed")
        return original_stop(managed)

    try:
        supervisor.start_services([first.name, second.name])
        monkeypatch.setattr(ManagedProcess, "stop", fail_first)

        with pytest.raises(RuntimeError, match="stop failed"):
            supervisor.stop_services([first.name, second.name])

        assert supervisor.is_running(first.name) is True
        assert supervisor.is_running(second.name) is False
        assert any(
            event["type"] == "service.stop_failed"
            for event in supervisor.state.read_events()
        )
    finally:
        monkeypatch.setattr(ManagedProcess, "stop", original_stop)
        supervisor.stop_services()


def test_supervisor_reports_endpoint_readiness(service_paths: ServicePaths) -> None:
    service = _http_service("api")
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        statuses = supervisor.start_services(["api"])

        assert statuses[0].state == "starting"
        status = supervisor.wait_until_ready("api", timeout_s=3)

        endpoint = status.endpoints["default"]
        assert status.ready is True
        assert status.state == "ready"
        assert status.health == "healthy"
        assert endpoint["protocol"] == "http"
        assert endpoint["port"] is not None
        assert endpoint["url"] == f"http://127.0.0.1:{endpoint['port']}/health"
        assert supervisor.is_ready("api") is True
        assert any(
            event["type"] == "service.started"
            and "default" in event["data"]["endpoints"]
            for event in state.read_events(limit=None)
        )
    finally:
        supervisor.stop_services(["api"])


def test_health_events_are_emitted_only_on_transitions(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    service = CondaService(
        name="transitions",
        summary="Health transitions",
        source="tests",
        restart_policy="never",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            grace_period_s=1,
        ),
        health_check=HealthCheck(interval_s=0.01, start_period_s=0),
    )
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)
    outcomes = iter((True, True, False, False, True))
    monkeypatch.setattr(ManagedProcess, "check_health", lambda managed: next(outcomes))

    try:
        supervisor.start_services([service.name])
        for _ in range(5):
            require_process(supervisor, service.name).last_health_check = 0
            supervisor.monitor_once()

        transitions = [
            event["type"]
            for event in state.read_events()
            if event["type"] in {"service.healthy", "service.unhealthy"}
        ]
        assert transitions == [
            "service.healthy",
            "service.unhealthy",
            "service.healthy",
        ]
    finally:
        supervisor.stop_services([service.name])


def test_restart_backoff_resets_only_after_healthy_runtime(
    service_paths: ServicePaths,
) -> None:
    service = _sleeping_service("backoff-health")
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services([service.name])
        managed = require_process(supervisor, service.name)
        managed.backoff_s = 8
        managed.started_monotonic = time.monotonic() - 600

        supervisor.schedule_restart(service.name, managed, reason="test")
        managed.healthy_since_monotonic = time.monotonic() - 301
        supervisor.schedule_restart(service.name, managed, reason="test")

        delays = [
            event["data"]["delay_s"]
            for event in state.read_events()
            if event["type"] == "service.restart_scheduled"
        ]
        assert delays == [8, 1.0]
    finally:
        supervisor.stop_services([service.name])


def test_health_failure_preserves_runtime_for_backoff_reset(
    service_paths: ServicePaths,
) -> None:
    service = _sleeping_service("health-backoff-reset")
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services([service.name])
        managed = require_process(supervisor, service.name)
        managed.health = "healthy"
        managed.backoff_s = 8
        now = time.monotonic()
        managed.started_monotonic = now - 301
        managed.healthy_since_monotonic = now - 301

        supervisor.record_health(service.name, managed, now, False)

        scheduled = [
            event
            for event in state.read_events()
            if event["type"] == "service.restart_scheduled"
        ]
        assert scheduled[-1]["data"]["delay_s"] == 1.0
    finally:
        supervisor.stop_services([service.name])


def test_exec_health_check_inherits_service_environment_and_cwd(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    code = (
        "import os, pathlib, sys; "
        f"expected = pathlib.Path({str(tmp_path)!r}); "
        "ok = (pathlib.Path.cwd() == expected "
        "and os.environ.get('SERVICE_FLAG') == 'yes' "
        "and os.environ.get('CONDA_BROKER_ENDPOINT_API_PORT')); "
        "sys.exit(0 if ok else 1)"
    )
    service = CondaService(
        name="exec-health-env",
        summary="Exec health environment",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            env={"SERVICE_FLAG": "yes"},
            cwd=str(tmp_path),
            grace_period_s=1,
        ),
        health_check=HealthCheck(
            type="exec",
            command=(sys.executable, "-c", code),
            interval_s=0.01,
            start_period_s=0,
        ),
        endpoints=(EndpointSpec(name="api"),),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        supervisor.start_services([service.name])
        status = supervisor.wait_until_ready(service.name, timeout_s=2)

        assert status.ready is True
    finally:
        supervisor.stop_services([service.name])


@pytest.mark.parametrize(
    ("status_code", "healthy"),
    [(200, True), (399, True), (400, False), (500, False)],
)
def test_http_health_status_contract(
    monkeypatch,
    service_paths: ServicePaths,
    status_code: int,
    healthy: bool,
) -> None:
    class Response:
        status = status_code

        def __enter__(self):
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    service = CondaService(
        name="http-contract",
        summary="HTTP health status contract",
        source="tests",
        restart_policy="never",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            grace_period_s=1,
        ),
        health_check=HealthCheck(type="http", url="http://127.0.0.1/health"),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )
    monkeypatch.setattr(
        "conda_broker.supervisor.urllib.request.urlopen",
        lambda *args, **kwargs: Response(),
    )

    try:
        supervisor.start_services([service.name])
        managed = require_process(supervisor, service.name)

        assert managed.check_health() is healthy
    finally:
        supervisor.stop_services([service.name])


def test_supervisor_restarts_failed_process(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    service = _flaky_service(
        "flaky",
        tmp_path / "flaky-count.txt",
        restart_policy="on-failure",
    )
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services(["flaky"])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            supervisor.monitor_once()
            if state.read_events(limit=1)[-1]["type"] == "service.restart_scheduled":
                break
            time.sleep(0.05)
        time.sleep(1.1)
        supervisor.monitor_once()

        status = supervisor.status_many(["flaky"])[0]
        assert status.running is True
        assert status.restart_count == 1
    finally:
        supervisor.stop_services(["flaky"])


def test_explicit_start_replaces_unobserved_exited_process(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    service = _flaky_service(
        "explicit-restart",
        tmp_path / "explicit-restart-count.txt",
        restart_policy="never",
    )
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services([service.name])
        first = require_process(supervisor, service.name).process
        first.wait(timeout=2)

        status = supervisor.start_services([service.name])[0]

        assert status.running is True
        assert status.pid != first.pid
        assert any(event["type"] == "service.exited" for event in state.read_events())
    finally:
        supervisor.stop_services([service.name])


def test_failed_start_bookkeeping_terminates_child(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    service = _sleeping_service("bookkeeping-failure")
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)
    original = state.set_managed_process
    launched_pid: list[int] = []

    def fail_write(name, process, *, instance_id=None):
        if process is not None:
            launched_pid.append(int(process["pid"]))
            raise OSError("state write failed")
        return original(name, process, instance_id=instance_id)

    monkeypatch.setattr(state, "set_managed_process", fail_write)

    with pytest.raises(OSError, match="state write failed"):
        supervisor.start_services([service.name])

    assert launched_pid
    assert psutil.pid_exists(launched_pid[0]) is False
    assert supervisor.status_many([service.name])[0].running is False
    assert state.managed_processes() == {}


def test_failed_process_identity_capture_terminates_child(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    class RecordingRuntime(ProcessRuntime):
        def __init__(self) -> None:
            self.pids: list[int] = []

        def start(self, *args, **kwargs):
            process = super().start(*args, **kwargs)
            self.pids.append(process.pid)
            return process

    def deny_process(_pid: int):
        raise psutil.AccessDenied(_pid)

    service = _sleeping_service("identity-failure")
    runtime = RecordingRuntime()
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
        runtime=runtime,
    )
    monkeypatch.setattr(supervisor_module.psutil, "Process", deny_process)

    with pytest.raises(RuntimeError, match="record process identity"):
        supervisor.start_services([service.name])

    assert runtime.pids
    assert psutil.pid_exists(runtime.pids[0]) is False


def test_multi_service_start_rolls_back_after_launch_failure(
    service_paths: ServicePaths,
) -> None:
    class FailingSecondRuntime(ProcessRuntime):
        def __init__(self) -> None:
            self.starts = 0

        def start(self, *args, **kwargs):
            self.starts += 1
            if self.starts == 2:
                raise OSError("second launch failed")
            return super().start(*args, **kwargs)

    first = _sleeping_service("first")
    second = _sleeping_service("second")
    supervisor = ServiceSupervisor(
        ServiceRegistry([first, second]),
        StateStore(service_paths),
        service_paths,
        runtime=FailingSecondRuntime(),
    )

    with pytest.raises(OSError, match="second launch failed"):
        supervisor.start_services([first.name, second.name])

    assert supervisor.is_running(first.name) is False
    assert supervisor.is_running(second.name) is False


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal timing")
def test_status_reports_stopping_during_grace_period(
    service_paths: ServicePaths,
) -> None:
    code = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(30)"
    )
    service = CondaService(
        name="slow-stop",
        summary="Slow stop",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", code),
            grace_period_s=1,
        ),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )
    supervisor.start_services([service.name])
    supervisor.monitor_once()
    time.sleep(0.2)
    stop = threading.Thread(target=supervisor.stop_services, args=([service.name],))

    stop.start()
    deadline = time.monotonic() + 1
    while (
        time.monotonic() < deadline
        and require_process(supervisor, service.name).stop_reason is None
    ):
        time.sleep(0.01)
    status = supervisor.status_many([service.name])[0]

    assert status.state == "stopping"
    assert status.running is True
    assert status.ready is False
    stop.join(timeout=3)
    assert not stop.is_alive()


def test_monitor_survives_failed_restart_launch(
    service_paths: ServicePaths,
) -> None:
    class FailingRestartRuntime(ProcessRuntime):
        def __init__(self) -> None:
            self.starts = 0

        def start(self, *args, **kwargs):
            self.starts += 1
            if self.starts > 1:
                raise OSError("simulated restart failure")
            return super().start(*args, **kwargs)

    service = CondaService(
        name="restart-launch-failure",
        summary="Fails while relaunching",
        source="tests",
        process=ProcessSpec(argv=(sys.executable, "-c", "raise SystemExit(1)")),
    )
    state = StateStore(service_paths)
    runtime = FailingRestartRuntime()
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        state,
        service_paths,
        runtime=runtime,
    )

    try:
        supervisor.start_services([service.name])
        supervisor.start_monitor()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            if any(
                event["type"] == "service.start_failed" for event in state.read_events()
            ):
                break
            time.sleep(0.05)

        assert supervisor.monitor_running is True
        assert runtime.starts >= 2
        assert supervisor.status_many([service.name])[0].state == "backing-off"
    finally:
        supervisor.shutdown()


def test_health_check_does_not_block_status(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "health-started"
    health_code = (
        f"import pathlib, time; pathlib.Path({str(marker)!r}).touch(); time.sleep(1)"
    )
    service = CondaService(
        name="slow-health",
        summary="Slow health check",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            grace_period_s=1,
        ),
        health_check=HealthCheck(
            type="exec",
            command=(sys.executable, "-c", health_code),
            interval_s=0.01,
            timeout_s=2,
        ),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        supervisor.start_services([service.name])
        monitor = threading.Thread(target=supervisor.monitor_once)
        monitor.start()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.01)

        started = time.monotonic()
        status = supervisor.status_many([service.name])[0]
        elapsed = time.monotonic() - started

        assert marker.exists()
        assert status.running is True
        assert elapsed < 0.2
        monitor.join(timeout=2)
        assert not monitor.is_alive()
    finally:
        supervisor.stop_services([service.name])


def test_supervisor_never_restart_policy_does_not_restart(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    service = _flaky_service(
        "never",
        tmp_path / "never-count.txt",
        restart_policy="never",
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    supervisor.start_services(["never"])
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        supervisor.monitor_once()
        if not supervisor.is_running("never"):
            break
        time.sleep(0.05)

    status = supervisor.status_many(["never"])[0]
    assert status.running is False
    assert status.restart_count == 0


def test_supervisor_always_restarts_clean_exit(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    count_file = tmp_path / "always-count.txt"
    code = (
        "import pathlib, sys, time; "
        f"p = pathlib.Path({str(count_file)!r}); "
        "n = int(p.read_text()) if p.exists() else 0; "
        "p.write_text(str(n + 1)); "
        "sys.exit(0) if n == 0 else time.sleep(30)"
    )
    service = CondaService(
        name="always",
        summary="Always restart",
        source="tests",
        restart_policy="always",
        process=ProcessSpec(argv=(sys.executable, "-c", code), grace_period_s=1),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        supervisor.start_services(["always"])
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            supervisor.monitor_once()
            if supervisor.status_many(["always"])[0].state == "backing-off":
                break
            time.sleep(0.05)
        time.sleep(1.1)
        supervisor.monitor_once()

        assert supervisor.status_many(["always"])[0].running is True
    finally:
        supervisor.stop_services(["always"])


def test_supervisor_starts_dependencies(service_paths: ServicePaths) -> None:
    dependency = _sleeping_service("dependency")
    service = _sleeping_service("app", dependencies=("dependency",))
    supervisor = ServiceSupervisor(
        ServiceRegistry([dependency, service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        statuses = supervisor.start_services(["app"])

        assert statuses[0].running is True
        assert supervisor.is_running("dependency") is True
        assert supervisor.is_running("app") is True
    finally:
        supervisor.stop_services(["app", "dependency"])


def test_supervisor_rejects_unavailable_runtime(
    service_paths: ServicePaths,
) -> None:
    service = CondaService(
        name="containerized",
        summary="Future runtime",
        source="tests",
        runtime="docker",
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    with pytest.raises(RuntimeUnavailableError, match="docker"):
        supervisor.start_services([service.name])


def test_dynamic_endpoint_ports_are_unique(service_paths: ServicePaths) -> None:
    service = CondaService(
        name="multi-endpoint",
        summary="Two dynamic ports",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            grace_period_s=1,
        ),
        endpoints=(EndpointSpec(name="api"), EndpointSpec(name="metrics")),
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry([service]),
        StateStore(service_paths),
        service_paths,
    )

    try:
        status = supervisor.start_services([service.name])[0]
        ports = {endpoint["port"] for endpoint in status.endpoints.values()}

        assert len(ports) == 2
        assert None not in ports
    finally:
        supervisor.stop_services([service.name])


def test_start_enabled_services_ignores_stale_enabled_entries(
    service_paths: ServicePaths,
) -> None:
    service = _sleeping_service("known")
    state = StateStore(service_paths)
    state.set_enabled(["known", "missing"], True)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        statuses = supervisor.start_enabled_services()

        assert [status.name for status in statuses] == ["known"]
        assert supervisor.is_running("known") is True
    finally:
        supervisor.stop_services(["known"])


def test_start_enabled_services_isolates_failures(
    service_paths: ServicePaths,
) -> None:
    unavailable = CondaService(
        name="a-unavailable",
        summary="Unavailable runtime",
        source="tests",
        runtime="docker",
    )
    healthy = _sleeping_service("z-healthy")
    state = StateStore(service_paths)
    state.set_enabled([unavailable.name, healthy.name], True)
    supervisor = ServiceSupervisor(
        ServiceRegistry([unavailable, healthy]),
        state,
        service_paths,
    )

    try:
        statuses = supervisor.start_enabled_services()

        assert [status.name for status in statuses] == [healthy.name]
        assert supervisor.is_running(healthy.name) is True
        assert any(
            event["type"] == "service.start_failed"
            and event["service"] == unavailable.name
            and event["data"]["reason"] == "autostart"
            for event in state.read_events()
        )
    finally:
        supervisor.stop_services([healthy.name])


def test_supervisor_reaps_process_from_previous_broker(
    service_paths: ServicePaths,
) -> None:
    service = _sleeping_service("orphan")
    state = StateStore(service_paths)
    old = ServiceSupervisor(
        ServiceRegistry([service]),
        state,
        service_paths,
        instance_id="old",
    )
    new = ServiceSupervisor(
        ServiceRegistry([service]),
        state,
        service_paths,
        instance_id="new",
    )

    old.start_services(["orphan"])
    pid = old.status_many(["orphan"])[0].pid
    assert pid is not None

    try:
        new.reconcile_stale_processes()

        assert psutil.pid_exists(pid) is False
        assert state.managed_processes() == {}
        assert any(
            event["type"] == "service.orphan_reaped" for event in state.read_events()
        )
    finally:
        old.stop_services(["orphan"])


def test_supervisor_does_not_kill_reused_pid_record(
    service_paths: ServicePaths,
) -> None:
    state = StateStore(service_paths)
    state.set_managed_process(
        "stale",
        {
            "pid": os.getpid(),
            "create_time": psutil.Process().create_time() + 1,
            "instance_id": "old",
        },
    )
    supervisor = ServiceSupervisor(
        ServiceRegistry(),
        state,
        service_paths,
        instance_id="new",
    )

    supervisor.reconcile_stale_processes()

    assert psutil.pid_exists(os.getpid()) is True
    assert state.managed_processes() == {}


def test_supervisor_health_failure_restarts(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "health-marker"
    health_code = (
        "import pathlib, sys; "
        f"p = pathlib.Path({str(marker)!r}); "
        "ok = p.exists(); "
        "p.touch(); "
        "sys.exit(0 if ok else 1)"
    )
    service = CondaService(
        name="unhealthy",
        summary="Fails health once",
        source="tests",
        process=ProcessSpec(
            argv=(sys.executable, "-c", "import time; time.sleep(30)"),
            grace_period_s=1,
        ),
        health_check=HealthCheck(
            type="exec",
            interval_s=0.01,
            timeout_s=1,
            start_period_s=0,
            command=(sys.executable, "-c", health_code),
        ),
    )
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services(["unhealthy"])
        supervisor.monitor_once()

        assert any(
            event["type"] == "service.unhealthy"
            for event in state.read_events(limit=None)
        )

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            supervisor.monitor_once()
            if supervisor.status_many(["unhealthy"])[0].state == "backing-off":
                break
            time.sleep(0.05)
        time.sleep(1.1)
        supervisor.monitor_once()

        status = supervisor.status_many(["unhealthy"])[0]
        assert status.running is True
        assert status.restart_count == 1
    finally:
        supervisor.stop_services(["unhealthy"])


@pytest.mark.skipif(
    os.name == "nt",
    reason="Windows terminate does not run the Python SIGTERM handler.",
)
def test_health_failure_restarts_even_when_stop_exits_cleanly(
    service_paths: ServicePaths,
    tmp_path: Path,
) -> None:
    marker = tmp_path / "health-marker"
    health_code = (
        "import pathlib, sys; "
        f"p = pathlib.Path({str(marker)!r}); "
        "ok = p.exists(); "
        "p.touch(); "
        "sys.exit(0 if ok else 1)"
    )
    service_code = (
        "import signal, sys, time; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        "time.sleep(30)"
    )
    service = CondaService(
        name="clean-health-restart",
        summary="Health failure restarts after clean stop",
        source="tests",
        restart_policy="on-failure",
        process=ProcessSpec(
            argv=(sys.executable, "-c", service_code),
            grace_period_s=1,
        ),
        health_check=HealthCheck(
            type="exec",
            interval_s=0.01,
            timeout_s=1,
            start_period_s=0,
            command=(sys.executable, "-c", health_code),
        ),
    )
    state = StateStore(service_paths)
    supervisor = ServiceSupervisor(ServiceRegistry([service]), state, service_paths)

    try:
        supervisor.start_services(["clean-health-restart"])
        supervisor.monitor_once()

        restart_events = [
            event
            for event in state.read_events(limit=None)
            if event["type"] == "service.restart_scheduled"
        ]
        assert restart_events
        assert restart_events[-1]["data"]["reason"] == "health"
        assert restart_events[-1]["data"]["exit_code"] == 0

        time.sleep(1.1)
        supervisor.monitor_once()

        status = supervisor.status_many(["clean-health-restart"])[0]
        assert status.running is True
        assert status.restart_count == 1
    finally:
        supervisor.stop_services(["clean-health-restart"])
