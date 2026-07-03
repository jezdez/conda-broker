"""Tests for provider-facing client helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conda_broker import client
from conda_broker.exceptions import UnknownServiceError
from conda_broker.models import CondaService, ProcessSpec
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
                name="presto",
                summary="Solver service",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
            )
        ]
    )
    monkeypatch.setattr(client, "discover_services", lambda: registry)

    assert client.is_service_running("presto", paths=service_paths) is False
    assert not service_paths.server_file.exists()
    assert not service_paths.pid_file.exists()


def test_emit_event_without_broker_writes_local_event(
    service_paths: ServicePaths,
) -> None:
    event = client.emit_event(
        "plugin.event",
        service="presto",
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
