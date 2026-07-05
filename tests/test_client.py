"""Tests for provider-facing client helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conda_broker import client
from conda_broker.exceptions import UnknownServiceError
from conda_broker.models import CondaService, EndpointSpec, ProcessSpec
from conda_broker.registry import ServiceRegistry

if TYPE_CHECKING:
    from conda_broker.paths import ServicePaths


def test_is_service_running_does_not_start_broker(
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
    monkeypatch.setattr(client, "discover_services", lambda: registry)

    assert client.is_service_running("package-cache", paths=service_paths) is False
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_service_ready_and_endpoint_helpers_do_not_start_broker(
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
    monkeypatch.setattr(client, "discover_services", lambda: registry)

    endpoint = client.get_service_endpoint("api", paths=service_paths)

    assert client.is_service_ready("api", paths=service_paths) is False
    assert endpoint is not None
    assert endpoint["url"] == "http://127.0.0.1:8765/health"
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_emit_event_without_broker_writes_local_event(
    service_paths: ServicePaths,
) -> None:
    event = client.emit_event(
        "plugin.event",
        service="package-cache",
        message="offline",
        paths=service_paths,
    )

    assert event.to_dict()["message"] == "offline"
    assert service_paths.events_file.exists()


def test_status_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(client, "discover_services", ServiceRegistry)

    with pytest.raises(UnknownServiceError):
        client.status("missing", paths=service_paths)


def test_is_service_running_unknown_service_returns_false(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(client, "discover_services", ServiceRegistry)

    assert client.service_status("missing", paths=service_paths) is None
    assert client.is_service_running("missing", paths=service_paths) is False


def test_set_enabled_unknown_service_offline_raises(
    monkeypatch,
    service_paths: ServicePaths,
) -> None:
    monkeypatch.setattr(client, "discover_services", ServiceRegistry)

    with pytest.raises(UnknownServiceError):
        client.set_enabled("missing", True, paths=service_paths)

    assert not service_paths.enabled_file.exists()
