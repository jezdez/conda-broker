"""Tests for broker dispatch behavior."""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest

from conda_broker.broker import BrokerLease, BrokerServer
from conda_broker.exceptions import IpcAuthError, UnknownServiceError
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry
from conda_broker.state import StateStore

if TYPE_CHECKING:
    from conda_broker.paths import ServicePaths


def _sleeping_service() -> CondaService:
    return CondaService(
        name="api",
        summary="API",
        source="tests",
        process=ProcessSpec(
            argv=(
                sys.executable,
                "-c",
                "import time; print('ready', flush=True); time.sleep(30)",
            ),
            grace_period_s=1,
        ),
        health_check=HealthCheck(type="process", interval_s=0.01),
        endpoints=(
            EndpointSpec(
                protocol="http",
                host="127.0.0.1",
                port=8765,
                path="/health",
            ),
        ),
    )


def test_dispatch_rejects_bad_token(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    with pytest.raises(IpcAuthError):
        broker.dispatch({"token": "bad", "method": "ping", "params": {}})


def test_dispatch_ping(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    assert broker.dispatch({"token": broker.token, "method": "ping"}) == {
        "status": "ok"
    }


def test_dispatch_status_uses_broker_payload(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    payload = broker.dispatch({"token": broker.token, "method": "status"})

    assert payload["broker"] == {"running": True}
    assert payload["services"] == []


def test_dispatch_endpoint_reports_static_endpoint(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    registry = ServiceRegistry([_sleeping_service()])
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: registry),
    )
    broker = BrokerServer(service_paths)

    payload = broker.dispatch(
        {
            "token": broker.token,
            "method": "endpoint",
            "params": {"service": "api", "endpoint": "default"},
        }
    )

    assert payload["endpoint"]["url"] == "http://127.0.0.1:8765/health"


def test_dispatch_wait_service_reports_ready(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    registry = ServiceRegistry([_sleeping_service()])
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: registry),
    )
    broker = BrokerServer(service_paths)

    try:
        broker.dispatch(
            {
                "token": broker.token,
                "method": "start_services",
                "params": {"services": ["api"]},
            }
        )
        payload = broker.dispatch(
            {
                "token": broker.token,
                "method": "wait_service",
                "params": {"service": "api", "timeout_s": 3},
            }
        )

        assert payload["services"][0]["ready"] is True
    finally:
        broker.supervisor.stop_services(["api"])


def test_dispatch_rejects_unknown_service_enable(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    with pytest.raises(UnknownServiceError):
        broker.dispatch(
            {
                "token": broker.token,
                "method": "set_enabled",
                "params": {"services": ["missing"], "enabled": True},
            }
        )

    assert StateStore(service_paths).enabled_services() == set()


def test_unheld_stale_lock_is_recovered(service_paths: ServicePaths) -> None:
    service_paths.lock_file.write_text("stale\n", encoding="utf-8")
    lease = BrokerLease(service_paths, "current")

    try:
        lease.acquire()

        assert service_paths.lock_file.exists()
    finally:
        lease.release()

    assert service_paths.lock_file.exists()
    assert lease.instance_id in service_paths.lock_file.read_text(encoding="utf-8")


def test_held_lock_prevents_second_broker(service_paths: ServicePaths) -> None:
    lock = service_paths.lock(service_paths.lock_file, blocking=False).acquire()
    lease = BrokerLease(service_paths, "current")

    try:
        with pytest.raises(SystemExit):
            lease.acquire()
    finally:
        lock.release()
        lease.release()


def test_cleanup_does_not_remove_successor_metadata(
    service_paths: ServicePaths,
) -> None:
    old = BrokerLease(service_paths, "old")
    new = BrokerLease(service_paths, "new")
    old.acquire()
    assert old.lock is not None
    old.lock.release()
    old.lock = None

    new.acquire()
    service_paths.write_json(
        service_paths.pid_file,
        {"pid": os.getpid(), "instance_id": new.instance_id},
    )
    service_paths.write_json(
        service_paths.server_file,
        {"instance_id": new.instance_id},
    )

    try:
        old.release()

        assert service_paths.pid_file.exists()
        assert service_paths.server_file.exists()
    finally:
        new.release()
