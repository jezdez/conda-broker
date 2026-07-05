"""Tests for provider-facing broker API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import conda_broker.api as broker_api
from conda_broker import Broker, BrokerState, Service, StatusSnapshot
from conda_broker.exceptions import IpcError, UnknownServiceError
from conda_broker.models import CondaService, EndpointSpec, ProcessSpec, ServiceStatus
from conda_broker.registry import ServiceRegistry

if TYPE_CHECKING:
    from conda_broker.paths import ServicePaths


def test_running_query_does_not_start_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    registry = ServiceRegistry(
        [
            CondaService(
                name="package-cache",
                summary="Package metadata cache",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
            )
        ]
    )
    monkeypatch.setattr(broker_api, "discover_services", lambda: registry)

    service = Broker.current(service_paths).service("package-cache")

    assert service.running() is False
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_ready_and_endpoint_queries_do_not_start_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    registry = ServiceRegistry(
        [
            CondaService(
                name="api",
                summary="API service",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
                endpoints=(
                    EndpointSpec(
                        protocol="http",
                        host="127.0.0.1",
                        port=8765,
                        path="/health",
                    ),
                ),
            )
        ]
    )
    monkeypatch.setattr(broker_api, "discover_services", lambda: registry)

    service = Broker.current(service_paths).service("api")
    endpoint = service.endpoint()

    assert service.ready() is False
    assert endpoint is not None
    assert endpoint.url == "http://127.0.0.1:8765/health"
    assert service.endpoint(ready=True) is None
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_emit_event_without_broker_writes_local_event(
    service_paths: ServicePaths,
) -> None:
    event = (
        Broker.current(service_paths)
        .service("package-cache")
        .emit_event("plugin.event", message="offline")
    )

    assert event.to_dict()["message"] == "offline"
    assert service_paths.events_file.exists()


def test_status_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(broker_api, "discover_services", ServiceRegistry)

    with pytest.raises(UnknownServiceError):
        Broker.current(service_paths).status("missing")


def test_unknown_service_handle_returns_false(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(broker_api, "discover_services", ServiceRegistry)

    service = Broker.current(service_paths).service("missing")

    assert service.status() is None
    assert service.running() is False


def test_service_check_reports_known_offline_service(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    registry = ServiceRegistry(
        [
            CondaService(
                name="api",
                summary="API service",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
                endpoints=(
                    EndpointSpec(
                        protocol="http",
                        host="127.0.0.1",
                        port=8765,
                        path="/health",
                    ),
                ),
            )
        ]
    )
    monkeypatch.setattr(broker_api, "discover_services", lambda: registry)

    check = Broker.current(service_paths).service("api").check()

    assert check.available is True
    assert check.running is False
    assert check.ready is False
    assert check.state == "stopped"
    assert check.reason == "stopped"
    assert check.endpoint is not None
    assert check.endpoint.url == "http://127.0.0.1:8765/health"
    assert check.to_dict()["endpoint"]["url"] == "http://127.0.0.1:8765/health"
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_service_check_reports_unknown_service(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(broker_api, "discover_services", ServiceRegistry)

    check = Broker.current(service_paths).service("missing").check()

    assert check.available is False
    assert check.reason == "unknown-service"
    assert check.to_dict()["running"] is False


def test_service_check_reports_broker_unavailable(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    def raise_ipc(self: Broker, service: str | None = None) -> StatusSnapshot:
        raise IpcError("bad response")

    monkeypatch.setattr(Broker, "status", raise_ipc)

    check = Broker.current(service_paths).service("api").check()

    assert check.available is False
    assert check.reason == "broker-unavailable"


def test_set_enabled_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(broker_api, "discover_services", ServiceRegistry)

    with pytest.raises(UnknownServiceError):
        Broker.current(service_paths).set_enabled("missing", True)

    assert not service_paths.enabled_file.exists()


def test_broker_started_context_stops_only_when_it_started(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    calls: list[tuple[str, float | None]] = []

    def running(self: Broker) -> bool:
        return broker_running["value"]

    def start(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        calls.append(("start", timeout_s))
        broker_running["value"] = True
        return BrokerState(running=True, started=True)

    def stop(self: Broker) -> dict[str, bool]:
        calls.append(("stop", None))
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "running", running)
    monkeypatch.setattr(Broker, "start", start)
    monkeypatch.setattr(Broker, "stop", stop)

    with Broker.current(service_paths).started(timeout_s=1.5, stop_timeout_s=0):
        assert broker_running["value"] is True

    assert calls == [("start", 1.5), ("stop", None)]


def test_broker_started_context_leaves_existing_broker_running(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(Broker, "running", lambda self: True)
    monkeypatch.setattr(
        Broker,
        "start",
        lambda self, *, timeout_s=5.0: (
            calls.append("start") or BrokerState(running=True, started=False)
        ),
    )
    monkeypatch.setattr(
        Broker,
        "stop",
        lambda self: calls.append("stop") or {"stopping": True},
    )

    with Broker.current(service_paths).started():
        pass

    assert calls == ["start"]


def test_service_started_context_cleans_up_started_service_and_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    service_running = {"value": False}
    calls: list[tuple[str, float | None]] = []

    def broker_is_running(self: Broker) -> bool:
        return broker_running["value"]

    def status(self: Service) -> ServiceStatus:
        return ServiceStatus(
            name=self.name,
            summary="API service",
            source="tests",
            runtime="process",
            enabled=False,
            state="running" if service_running["value"] else "stopped",
            running=service_running["value"],
            ready=service_running["value"],
        )

    def start(self: Service, *, timeout_s: float = 5.0) -> StatusSnapshot:
        calls.append(("service.start", timeout_s))
        broker_running["value"] = True
        service_running["value"] = True
        return StatusSnapshot()

    def wait(
        self: Service,
        *,
        timeout_s: float = 30.0,
        start: bool = False,
    ) -> StatusSnapshot:
        calls.append(("service.wait", timeout_s))
        return StatusSnapshot()

    def stop_service(self: Service) -> StatusSnapshot:
        calls.append(("service.stop", None))
        service_running["value"] = False
        return StatusSnapshot()

    def stop_broker(self: Broker) -> dict[str, bool]:
        calls.append(("broker.stop", None))
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "running", broker_is_running)
    monkeypatch.setattr(Broker, "stop", stop_broker)
    monkeypatch.setattr(Service, "status", status)
    monkeypatch.setattr(Service, "start", start)
    monkeypatch.setattr(Service, "wait", wait)
    monkeypatch.setattr(Service, "stop", stop_service)

    service = Broker.current(service_paths).service("api")
    with service.started(timeout_s=2.0, wait=True, wait_timeout_s=3.0):
        assert broker_running["value"] is True
        assert service_running["value"] is True

    assert calls == [
        ("service.start", 2.0),
        ("service.wait", 3.0),
        ("service.stop", None),
        ("broker.stop", None),
    ]


def test_service_started_context_leaves_existing_service_running(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(Broker, "running", lambda self: True)
    monkeypatch.setattr(
        Service,
        "status",
        lambda self: ServiceStatus(
            name=self.name,
            summary="API service",
            source="tests",
            runtime="process",
            enabled=False,
            state="running",
            running=True,
            ready=True,
        ),
    )
    monkeypatch.setattr(
        Service,
        "start",
        lambda self, *, timeout_s=5.0: calls.append("start") or StatusSnapshot(),
    )
    monkeypatch.setattr(
        Service,
        "stop",
        lambda self: calls.append("stop") or StatusSnapshot(),
    )
    monkeypatch.setattr(
        Broker,
        "stop",
        lambda self: calls.append("broker.stop") or {"stopping": True},
    )

    with Broker.current(service_paths).service("api").started():
        pass

    assert calls == ["start"]
