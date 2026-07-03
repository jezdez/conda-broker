"""Tests for real subprocess supervision."""

from __future__ import annotations

import sys
import time
from typing import TYPE_CHECKING

from conda_broker.models import CondaService, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry
from conda_broker.state import StateStore
from conda_broker.supervisor import ServiceSupervisor

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
            if supervisor.status_many(["always"])[0].state == "restarting":
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
            if supervisor.status_many(["unhealthy"])[0].state == "restarting":
                break
            time.sleep(0.05)
        time.sleep(1.1)
        supervisor.monitor_once()

        status = supervisor.status_many(["unhealthy"])[0]
        assert status.running is True
        assert status.restart_count == 1
    finally:
        supervisor.stop_services(["unhealthy"])
