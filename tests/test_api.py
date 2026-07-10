"""Tests for provider-facing broker API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conda_broker import Broker, BrokerState, Service, StatusSnapshot
from conda_broker.exceptions import (
    BrokerNotRunningError,
    IpcError,
    ServiceNotReadyError,
    ServiceValidationError,
    UnknownServiceError,
)
from conda_broker.ipc import IpcClient
from conda_broker.models import (
    CondaService,
    ProcessSpec,
    ServiceEvent,
    ServiceStatus,
)
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
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: registry),
    )

    service = Broker.current(service_paths).service("package-cache")

    assert service.running() is False
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_ready_and_endpoint_queries_do_not_start_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    def fail_discovery() -> ServiceRegistry:
        raise AssertionError("service query performed provider discovery")

    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: fail_discovery()),
    )

    service = Broker.current(service_paths).service("api")
    endpoint = service.endpoint()

    assert service.ready() is False
    assert endpoint is None
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


def test_emit_event_with_broker_returns_typed_event(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(IpcClient, "ping", lambda self: True)
    monkeypatch.setattr(
        IpcClient,
        "call",
        lambda *args, **kwargs: {
            "event": {
                "type": "plugin.event",
                "service": "api",
                "message": "online",
                "data": {},
                "timestamp": "2026-01-01T00:00:00+00:00",
            }
        },
    )

    event = Broker.current(service_paths).service("api").emit_event("plugin.event")

    assert isinstance(event, ServiceEvent)
    assert event.service == "api"


def test_emit_event_falls_back_when_broker_stops_during_call(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(IpcClient, "ping", lambda self: True)

    def broker_stopped(*args, **kwargs):
        raise BrokerNotRunningError("broker stopped")

    monkeypatch.setattr(IpcClient, "call", broker_stopped)

    event = Broker.current(service_paths).emit_event("plugin.event")

    assert isinstance(event, ServiceEvent)
    assert service_paths.events_file.exists()


def test_status_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: ServiceRegistry()),
    )

    with pytest.raises(UnknownServiceError):
        Broker.current(service_paths).status("missing")


def test_unknown_service_handle_returns_false(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: ServiceRegistry()),
    )

    service = Broker.current(service_paths).service("missing")

    assert service.status() is None
    assert service.running() is False


def test_service_check_reports_known_offline_service(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    def fail_discovery() -> ServiceRegistry:
        raise AssertionError("service check performed provider discovery")

    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: fail_discovery()),
    )

    check = Broker.current(service_paths).service("api").check()

    assert check.available is False
    assert check.running is False
    assert check.ready is False
    assert check.state == "unknown"
    assert check.reason == "broker-unavailable"
    assert check.endpoint is None
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_service_check_reports_unknown_service(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    def fail_discovery() -> ServiceRegistry:
        raise AssertionError("service check performed provider discovery")

    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: fail_discovery()),
    )

    check = Broker.current(service_paths).service("missing").check()

    assert check.available is False
    assert check.reason == "broker-unavailable"
    assert check.to_dict()["running"] is False


def test_service_check_reports_broker_unavailable(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    def raise_ipc(self: Broker, service: str | None = None) -> StatusSnapshot:
        raise IpcError("bad response")

    monkeypatch.setattr(Broker, "status", raise_ipc)
    monkeypatch.setattr(Broker, "running", lambda self: True)

    check = Broker.current(service_paths).service("api").check()

    assert check.available is False
    assert check.reason == "broker-unavailable"


def test_set_enabled_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(
        ServiceRegistry,
        "discover",
        classmethod(lambda cls: ServiceRegistry()),
    )

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

    def stop(self: Broker, *, timeout_s: float = 5.0) -> dict[str, bool]:
        calls.append(("stop", timeout_s))
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "running", running)
    monkeypatch.setattr(Broker, "start", start)
    monkeypatch.setattr(Broker, "stop", stop)

    with Broker.current(service_paths).started(
        timeout_s=1.5,
        stop_timeout_s=0.25,
    ):
        assert broker_running["value"] is True

    assert calls == [("start", 1.5), ("stop", 0.25)]


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
        lambda self, *, timeout_s=5.0: calls.append("stop") or {"stopping": True},
    )

    with Broker.current(service_paths).started():
        pass

    assert calls == ["start"]


def test_broker_started_context_cleans_up_after_start_error(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    calls: list[str] = []

    monkeypatch.setattr(
        Broker,
        "running",
        lambda self: broker_running["value"],
    )

    def start(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        broker_running["value"] = True
        raise RuntimeError("startup response failed")

    def stop(self: Broker, *, timeout_s: float = 5.0) -> dict[str, bool]:
        calls.append("stop")
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "start", start)
    monkeypatch.setattr(Broker, "stop", stop)

    with pytest.raises(RuntimeError, match="startup response failed"):
        with Broker.current(service_paths).started():
            pass

    assert calls == ["stop"]


def test_context_rejects_invalid_cleanup_timeout_before_start(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        Broker,
        "start",
        lambda self, *, timeout_s=5.0: calls.append("start"),
    )

    with pytest.raises(ValueError, match="positive finite"):
        with Broker.current(service_paths).started(stop_timeout_s=0):
            pass

    assert calls == []


def test_service_started_context_cleans_up_started_service_and_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    service_running = {"value": False}
    calls: list[tuple[str, float | None]] = []

    def broker_is_running(self: Broker) -> bool:
        return broker_running["value"]

    def start_broker(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        calls.append(("broker.start", timeout_s))
        broker_running["value"] = True
        return BrokerState(running=True, started=True)

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
        return StatusSnapshot(
            broker=BrokerState(running=True, started=True),
            raw={"started": [self.name]},
        )

    def wait(
        self: Service,
        *,
        timeout_s: float = 30.0,
        start: bool = False,
    ) -> StatusSnapshot:
        calls.append(("service.wait", timeout_s))
        return StatusSnapshot(
            services=(
                ServiceStatus(
                    name=self.name,
                    summary="API service",
                    source="tests",
                    runtime="process",
                    enabled=False,
                    state="ready",
                    running=True,
                    ready=True,
                ),
            )
        )

    def stop_service(self: Service) -> StatusSnapshot:
        calls.append(("service.stop", None))
        service_running["value"] = False
        return StatusSnapshot()

    def stop_broker(self: Broker, *, timeout_s: float = 5.0) -> dict[str, bool]:
        calls.append(("broker.stop", timeout_s))
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "running", broker_is_running)
    monkeypatch.setattr(Broker, "start", start_broker)
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
        ("broker.start", 2.0),
        ("service.start", 2.0),
        ("service.wait", 3.0),
        ("service.stop", None),
        ("broker.stop", 5.0),
    ]


def test_service_started_context_leaves_existing_service_running(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    calls: list[str] = []

    monkeypatch.setattr(Broker, "running", lambda self: True)
    monkeypatch.setattr(
        Broker,
        "start",
        lambda self, *, timeout_s=5.0: (
            calls.append("broker.start") or BrokerState(running=True, started=False)
        ),
    )
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
        lambda self, *, timeout_s=5.0: (
            calls.append("broker.stop") or {"stopping": True}
        ),
    )

    with Broker.current(service_paths).service("api").started():
        pass

    assert calls == ["broker.start", "start"]


def test_start_services_requires_a_name(service_paths: ServicePaths) -> None:
    with pytest.raises(ServiceValidationError, match="at least one service"):
        Broker.current(service_paths).start_services([])


@pytest.mark.parametrize("timeout_s", [0, -1, float("nan"), float("inf")])
def test_broker_start_rejects_invalid_timeout_without_side_effects(
    service_paths: ServicePaths,
    timeout_s: float,
) -> None:
    broker = Broker.current(service_paths)

    with pytest.raises(ValueError, match="positive finite"):
        broker.start(timeout_s=timeout_s)

    assert not broker.running()
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_service_started_context_raises_when_service_is_not_ready(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    calls: list[str] = []

    monkeypatch.setattr(
        Broker,
        "running",
        lambda self: broker_running["value"],
    )

    def start_broker(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        broker_running["value"] = True
        return BrokerState(running=True, started=True)

    def start(self: Service, *, timeout_s: float = 5.0) -> StatusSnapshot:
        broker_running["value"] = True
        return StatusSnapshot(
            broker=BrokerState(running=True, started=True),
            raw={"started": [self.name]},
        )

    monkeypatch.setattr(Broker, "start", start_broker)
    monkeypatch.setattr(Service, "start", start)
    monkeypatch.setattr(
        Service,
        "wait",
        lambda self, *, timeout_s=30.0, start=False: StatusSnapshot(
            services=(
                ServiceStatus(
                    name=self.name,
                    summary="API service",
                    source="tests",
                    runtime="process",
                    enabled=False,
                    state="degraded",
                    running=True,
                    health="unhealthy",
                ),
            )
        ),
    )
    monkeypatch.setattr(
        Service,
        "stop",
        lambda self: calls.append("service.stop") or StatusSnapshot(),
    )

    def stop_broker(self: Broker, *, timeout_s: float = 5.0) -> dict[str, bool]:
        calls.append("broker.stop")
        broker_running["value"] = False
        return {"stopping": True}

    monkeypatch.setattr(Broker, "stop", stop_broker)

    service = Broker.current(service_paths).service("api")
    with pytest.raises(ServiceNotReadyError):
        with service.started(wait=True):
            pass

    assert calls == ["service.stop", "broker.stop"]


def test_service_context_does_not_claim_concurrently_started_broker(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    broker_running = {"value": False}
    calls: list[str] = []

    monkeypatch.setattr(
        Broker,
        "running",
        lambda self: broker_running["value"],
    )

    def start_broker(self: Broker, *, timeout_s: float = 5.0) -> BrokerState:
        broker_running["value"] = True
        return BrokerState(running=True, started=False)

    monkeypatch.setattr(Broker, "start", start_broker)
    monkeypatch.setattr(
        Broker,
        "stop",
        lambda self, *, timeout_s=5.0: (
            calls.append("broker.stop") or {"stopping": True}
        ),
    )
    monkeypatch.setattr(
        Service,
        "start",
        lambda self, *, timeout_s=5.0: (_ for _ in ()).throw(
            RuntimeError("service failed")
        ),
    )

    service = Broker.current(service_paths).service("api")
    with pytest.raises(RuntimeError, match="service failed"):
        with service.started():
            pass

    assert calls == []
