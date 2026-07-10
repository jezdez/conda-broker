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
    service = CondaService(
        name="containerized",
        summary="Future runtime",
        source="tests",
        runtime="docker",
    )

    assert service.runtime == "docker"
    assert service.process is None


def test_invalid_runtime_name_raises() -> None:
    with pytest.raises(ValueError, match="Invalid runtime name"):
        CondaService(
            name="containerized",
            summary="Future runtime",
            source="tests",
            runtime="docker runtime",
        )


def test_process_rejects_unknown_stop_signal() -> None:
    with pytest.raises(ValueError, match="Unknown process stop signal"):
        ProcessSpec(argv=("python", "-V"), stop_signal="NOT_A_SIGNAL")


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_health_check_rejects_invalid_intervals(value: float) -> None:
    with pytest.raises(ValueError, match="interval"):
        HealthCheck(interval_s=value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), 0, -1])
def test_process_rejects_invalid_grace_period(value: float) -> None:
    with pytest.raises(ValueError, match="grace period"):
        ProcessSpec(argv=("python", "-V"), grace_period_s=value)


def test_process_rejects_invalid_environment_name() -> None:
    with pytest.raises(ValueError, match="environment variable name"):
        ProcessSpec(argv=("python", "-V"), env={"BAD=NAME": "value"})


def test_service_rejects_colliding_endpoint_environment_names() -> None:
    with pytest.raises(ValueError, match="unique environment variable names"):
        CondaService(
            name="api",
            summary="API",
            source="tests",
            process=ProcessSpec(argv=("python", "-V")),
            endpoints=(
                EndpointSpec(name="public-api"),
                EndpointSpec(name="public_api"),
            ),
        )


def test_endpoint_url_brackets_ipv6_host() -> None:
    endpoint = EndpointSpec(protocol="http", host="::1", port=8000, path="/health")

    assert endpoint.resolve().url == "http://[::1]:8000/health"


def test_service_rejects_custom_endpoint_environment_collisions() -> None:
    with pytest.raises(ValueError, match="conflict with broker variables"):
        CondaService(
            name="api",
            summary="API",
            source="tests",
            process=ProcessSpec(argv=("python", "-V")),
            endpoints=(
                EndpointSpec(
                    port_env="CONDA_BROKER_ENDPOINT_DEFAULT_URL",
                ),
            ),
        )

    with pytest.raises(ValueError, match="custom environment names must be unique"):
        CondaService(
            name="api",
            summary="API",
            source="tests",
            process=ProcessSpec(argv=("python", "-V")),
            endpoints=(
                EndpointSpec(name="api", port_env="PORT"),
                EndpointSpec(name="metrics", port_env="PORT"),
            ),
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


def test_registry_resolves_startup_order() -> None:
    database = CondaService(
        name="database",
        summary="Database",
        source="tests",
        process=ProcessSpec(argv=("python", "-V")),
    )
    app = CondaService(
        name="app",
        summary="App",
        source="tests",
        dependencies=(database.name,),
        process=ProcessSpec(argv=("python", "-V")),
    )
    registry = ServiceRegistry([app, database])

    assert [service.name for service in registry.startup_order([app.name])] == [
        database.name,
        app.name,
    ]


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


def test_registry_isolates_failing_providers() -> None:
    class GoodProvider:
        @hookimpl
        def conda_broker_services(self):
            yield CondaService(
                name="package-cache",
                summary="Package metadata cache",
                source="good-provider",
                process=ProcessSpec(argv=("python", "-V")),
            )

    class BadProvider:
        @hookimpl
        def conda_broker_services(self):
            raise RuntimeError("provider failed")
            yield

    registry = ServiceRegistry()
    registry.register(BadProvider(), name="bad-provider")
    registry.register(GoodProvider(), name="good-provider")
    registry.collect_provider_services()

    assert registry.names() == ["package-cache"]
    assert registry.provider_errors == [
        {
            "provider": "bad-provider",
            "phase": "services",
            "error": "provider failed",
            "error_type": "RuntimeError",
        }
    ]


def test_registry_quarantines_services_with_invalid_dependencies() -> None:
    class Provider:
        @hookimpl
        def conda_broker_services(self):
            yield CondaService(
                name="api",
                summary="API",
                source="provider",
                dependencies=("database",),
                process=ProcessSpec(argv=("python", "-V")),
            )

    registry = ServiceRegistry()
    registry.register(Provider(), name="provider")
    registry.collect_provider_services()

    assert registry.names() == []
    assert registry.provider_errors[0]["provider"] == "provider"
    assert registry.provider_errors[0]["phase"] == "dependencies"
    assert "unknown service" in registry.provider_errors[0]["error"]


def test_registry_duplicate_does_not_remove_first_provider() -> None:
    class FirstProvider:
        @hookimpl
        def conda_broker_services(self):
            yield CondaService(
                name="shared",
                summary="First",
                source="first",
                process=ProcessSpec(argv=("python", "-V")),
            )

    class SecondProvider:
        @hookimpl
        def conda_broker_services(self):
            yield CondaService(
                name="temporary",
                summary="Rolled back",
                source="second",
                process=ProcessSpec(argv=("python", "-V")),
            )
            yield CondaService(
                name="shared",
                summary="Duplicate",
                source="second",
                process=ProcessSpec(argv=("python", "-V")),
            )

    registry = ServiceRegistry()
    registry.register(SecondProvider(), name="z-second")
    registry.register(FirstProvider(), name="a-first")
    registry.collect_provider_services()

    assert registry.names() == ["shared"]
    assert registry.get("shared").source == "first"
    assert registry.provider_errors[0]["provider"] == "z-second"
