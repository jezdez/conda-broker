"""Tests for provider-facing broker API helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import conda_broker.api as broker_api
from conda_broker import Broker
from conda_broker.exceptions import UnknownServiceError
from conda_broker.models import CondaService, EndpointSpec, ProcessSpec
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


def test_set_enabled_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(broker_api, "discover_services", ServiceRegistry)

    with pytest.raises(UnknownServiceError):
        Broker.current(service_paths).set_enabled("missing", True)

    assert not service_paths.enabled_file.exists()
