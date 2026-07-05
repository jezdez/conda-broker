"""Tests for service models and registry validation."""

from __future__ import annotations

import pluggy
import pytest

from conda_broker.exceptions import (
    DuplicateServiceError,
    ServiceValidationError,
    UnknownServiceError,
)
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry


def test_process_service_to_dict() -> None:
    service = CondaService(
        name="package-cache",
        summary="Package metadata cache",
        source="conda-package-cache",
        start_policy="enabled",
        process=ProcessSpec(
            argv=("python", "-m", "conda_package_cache", "--serve"),
            env={"CONDA_JSON": "true"},
        ),
        health_check=HealthCheck(type="process"),
    )

    assert service.enabled_by_default is True
    assert service.to_dict()["process"]["argv"] == [
        "python",
        "-m",
        "conda_package_cache",
        "--serve",
    ]
    assert service.merged_process().env["CONDA_JSON"] == "true"


def test_endpoint_service_to_dict() -> None:
    service = CondaService(
        name="api",
        summary="HTTP API",
        source="tests",
        process=ProcessSpec(argv=("python", "-m", "http.server")),
        health_check=HealthCheck(type="http", endpoint="default"),
        endpoints=(
            EndpointSpec(
                protocol="http",
                path="/health",
                port_env="PORT",
                url_env="URL",
            ),
        ),
    )

    endpoint = service.to_dict()["endpoints"][0]
    assert endpoint["protocol"] == "http"
    assert endpoint["port"] is None
    assert service.endpoints[0].resolve(1234).to_dict()["url"] == (
        "http://127.0.0.1:1234/health"
    )


def test_health_check_rejects_unknown_endpoint() -> None:
    with pytest.raises(ValueError, match="unknown endpoint"):
        CondaService(
            name="bad-health",
            summary="Bad health",
            source="tests",
            process=ProcessSpec(argv=("python", "-V")),
            health_check=HealthCheck(type="tcp", endpoint="missing"),
        )


@pytest.mark.parametrize(
    "name",
    ["", "has space", "/path", "semi;colon"],
    ids=["empty", "space", "slash", "semicolon"],
)
def test_invalid_service_names_raise(name: str) -> None:
    with pytest.raises(ValueError):
        CondaService(
            name=name,
            summary="bad",
            source="tests",
            process=ProcessSpec(argv=("python", "-V")),
        )


def test_unsupported_runtime_raises() -> None:
    with pytest.raises(ValueError, match="Unknown runtime"):
        CondaService(
            name="containerized",
            summary="Future runtime",
            source="tests",
            runtime="docker",
        )


def test_registry_rejects_duplicates() -> None:
    service = CondaService(
        name="package-cache",
        summary="Package metadata cache",
        source="one",
        process=ProcessSpec(argv=("python", "-V")),
    )

    with pytest.raises(DuplicateServiceError):
        ServiceRegistry(
            [
                service,
                CondaService(
                    name="package-cache",
                    summary="Duplicate",
                    source="two",
                    process=ProcessSpec(argv=("python", "-V")),
                ),
            ]
        )


def test_registry_get_unknown_raises() -> None:
    registry = ServiceRegistry()

    with pytest.raises(UnknownServiceError):
        registry.get("missing")


def test_registry_rejects_unknown_dependencies() -> None:
    with pytest.raises(ServiceValidationError, match="unknown service"):
        ServiceRegistry(
            [
                CondaService(
                    name="app",
                    summary="App",
                    source="tests",
                    dependencies=("database",),
                    process=ProcessSpec(argv=("python", "-V")),
                )
            ]
        )


def test_registry_rejects_dependency_cycles() -> None:
    with pytest.raises(ServiceValidationError, match="dependency cycle"):
        ServiceRegistry(
            [
                CondaService(
                    name="app",
                    summary="App",
                    source="tests",
                    dependencies=("worker",),
                    process=ProcessSpec(argv=("python", "-V")),
                ),
                CondaService(
                    name="worker",
                    summary="Worker",
                    source="tests",
                    dependencies=("app",),
                    process=ProcessSpec(argv=("python", "-V")),
                ),
            ]
        )


def test_registry_is_pluggy_manager() -> None:
    registry = ServiceRegistry()

    assert isinstance(registry, pluggy.PluginManager)
    assert hasattr(registry.hook, "conda_broker_services")


def test_registry_collects_registered_provider_services() -> None:
    class Provider:
        @hookimpl
        def conda_broker_services(self):
            yield CondaService(
                name="package-cache",
                summary="Package metadata cache",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
            )

    registry = ServiceRegistry()
    registry.register(Provider(), name="provider")
    registry.collect_provider_services()

    assert registry.get_plugin("provider") is not None
    assert registry.names() == ["package-cache"]
