"""End-to-end tests through a detached broker process."""

from __future__ import annotations

import json
import os
import queue
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import psutil
import pytest

from conda_broker import Broker, BrokerState
from conda_broker.exceptions import UnknownServiceError
from conda_broker.ipc import MAX_MESSAGE_BYTES, ServerInfo
from conda_broker.state import StateStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from conda_broker.paths import ServicePaths


@pytest.fixture
def integration_provider(monkeypatch) -> Path:
    root = Path(__file__).parent / "fixtures" / "integration-provider"
    pythonpath = os.environ.get("PYTHONPATH")
    value = str(root) if not pythonpath else f"{root}{os.pathsep}{pythonpath}"
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv("PYTHONPATH", value)
    return root


def _run_cli(paths: ServicePaths, *args: str) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "conda_broker",
            "--runtime-dir",
            str(paths.runtime_dir),
            "--log-dir",
            str(paths.log_dir),
            "--json",
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _wait_until(predicate: Callable[[], bool], *, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition did not become true before timeout")


def _service_has_logged(paths: ServicePaths) -> bool:
    path = paths.log_dir / "integration-heartbeat.log"
    try:
        return "integration heartbeat ready" in path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False


def test_full_cli_broker_lifecycle(
    integration_provider: Path,
    service_paths: ServicePaths,
) -> None:
    broker = Broker.current(service_paths)
    try:
        started = _run_cli(
            service_paths,
            "start",
            "integration-heartbeat",
            "--timeout",
            "10",
        )
        assert started["broker"] == {"running": True, "started": True}
        assert started["started"] == ["integration-heartbeat"]

        waited = _run_cli(
            service_paths,
            "wait",
            "integration-heartbeat",
            "--timeout",
            "10",
        )
        first_pid = waited["services"][0]["pid"]
        assert waited["services"][0]["ready"] is True

        with pytest.raises(UnknownServiceError):
            broker.status("missing")

        _wait_until(lambda: _service_has_logged(service_paths))
        logs = _run_cli(
            service_paths,
            "logs",
            "integration-heartbeat",
            "--lines",
            "5",
        )
        assert any("heartbeat" in line for line in logs["lines"])

        _run_cli(service_paths, "restart", "integration-heartbeat", "--timeout", "10")
        restarted = _run_cli(
            service_paths,
            "wait",
            "integration-heartbeat",
            "--timeout",
            "10",
        )
        assert restarted["services"][0]["pid"] != first_pid

        stopped = _run_cli(service_paths, "stop", "integration-heartbeat")
        assert stopped["services"][0]["running"] is False
        _run_cli(service_paths, "stop")
    finally:
        if broker.running():
            broker.stop(timeout_s=10)

    assert service_paths.lock_available(service_paths.lock_file) is True
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_concurrent_broker_start_has_one_owner(
    integration_provider: Path,
    service_paths: ServicePaths,
) -> None:
    del integration_provider
    broker = Broker.current(service_paths)
    barrier = threading.Barrier(3)
    results: queue.Queue[object] = queue.Queue()

    def start() -> None:
        barrier.wait()
        try:
            results.put(broker.start(timeout_s=10))
        except BaseException as exc:
            results.put(exc)

    threads = [threading.Thread(target=start) for _ in range(2)]
    try:
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join(timeout=15)

        states = [results.get_nowait() for _ in threads]
        assert all(isinstance(state, BrokerState) for state in states)
        ownership = [
            state.started for state in states if isinstance(state, BrokerState)
        ]
        assert ownership.count(True) == 1
        assert ownership.count(False) == 1
    finally:
        if broker.running():
            broker.stop(timeout_s=10)


def test_broker_rejects_oversized_ipc_request(
    integration_provider: Path,
    service_paths: ServicePaths,
) -> None:
    del integration_provider
    broker = Broker.current(service_paths)
    try:
        broker.start(timeout_s=10)
        info = ServerInfo.read(service_paths.server_file)
        with socket.create_connection((info.host, info.port), timeout=2) as connection:
            connection.sendall(b"x" * (MAX_MESSAGE_BYTES + 1) + b"\n")
            with connection.makefile("rb") as stream:
                response = json.loads(stream.readline())

        assert response["ok"] is False
        assert response["error"]["message"] == "IPC request is too large"
    finally:
        if broker.running():
            broker.stop(timeout_s=10)


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal lifecycle")
def test_broker_sigterm_stops_managed_processes(
    integration_provider: Path,
    service_paths: ServicePaths,
) -> None:
    broker = Broker.current(service_paths)
    service = broker.service("integration-heartbeat")
    try:
        service.start(timeout_s=10)
        status = service.wait(timeout_s=10).services[0]
        assert status.pid is not None
        _wait_until(lambda: _service_has_logged(service_paths))
        broker_pid = json.loads(service_paths.pid_file.read_text(encoding="utf-8"))[
            "pid"
        ]

        os.kill(broker_pid, signal.SIGTERM)

        _wait_until(lambda: not broker.running())
        _wait_until(lambda: not psutil.pid_exists(status.pid))
        _wait_until(lambda: service_paths.lock_available(service_paths.lock_file))
        assert StateStore(service_paths).managed_processes() == {}
    finally:
        if broker.running():
            broker.stop(timeout_s=10)


@pytest.mark.skipif(os.name == "nt", reason="POSIX crash signal")
def test_new_broker_reaps_processes_after_broker_crash(
    integration_provider: Path,
    service_paths: ServicePaths,
) -> None:
    broker = Broker.current(service_paths)
    service = broker.service("integration-heartbeat")
    try:
        service.start(timeout_s=10)
        status = service.wait(timeout_s=10).services[0]
        assert status.pid is not None
        _wait_until(lambda: _service_has_logged(service_paths))
        broker_pid = json.loads(service_paths.pid_file.read_text(encoding="utf-8"))[
            "pid"
        ]

        os.kill(broker_pid, signal.SIGKILL)
        _wait_until(lambda: not broker.running())
        assert psutil.pid_exists(status.pid) is True

        broker.start(timeout_s=10)

        _wait_until(lambda: not psutil.pid_exists(status.pid))
        assert StateStore(service_paths).managed_processes() == {}
        assert any(
            event["type"] == "service.orphan_reaped"
            for event in broker.events()["events"]
        )
    finally:
        if broker.running():
            broker.stop(timeout_s=10)
