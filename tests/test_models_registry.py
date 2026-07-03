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
from conda_broker.models import CondaService, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry


def test_process_service_to_dict() -> None:
    service = CondaService(
        name="presto",
        summary="Solver service",
        source="conda-presto",
        start_policy="enabled",
        process=ProcessSpec(
            argv=("conda", "presto", "--serve"),
            env={"CONDA_JSON": "true"},
        ),
        health_check=HealthCheck(type="process"),
    )

    assert service.enabled_by_default is True
    assert service.to_dict()["process"]["argv"] == ["conda", "presto", "--serve"]
    assert service.merged_process().env["CONDA_JSON"] == "true"


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
        name="presto",
        summary="Solver service",
        source="one",
        process=ProcessSpec(argv=("python", "-V")),
    )

    with pytest.raises(DuplicateServiceError):
        ServiceRegistry(
            [
                service,
                CondaService(
                    name="presto",
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
                name="presto",
                summary="Solver service",
                source="tests",
                process=ProcessSpec(argv=("python", "-V")),
            )

    registry = ServiceRegistry()
    registry.register(Provider(), name="provider")
    registry.collect_provider_services()

    assert registry.get_plugin("provider") is not None
    assert registry.names() == ["presto"]
