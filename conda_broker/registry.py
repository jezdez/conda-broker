"""Service discovery and validation."""

from __future__ import annotations

from importlib.metadata import entry_points
from typing import TYPE_CHECKING

import pluggy

from .exceptions import (
    DuplicateServiceError,
    ServiceValidationError,
    UnknownServiceError,
)
from .hookspec import ENTRY_POINT_GROUP, PROJECT_NAME
from .models import CondaService

if TYPE_CHECKING:
    from collections.abc import Iterable


class ServiceRegistry(pluggy.PluginManager):
    """Pluggy manager plus validated service registry keyed by service name."""

    def __init__(self, services: Iterable[CondaService] = ()) -> None:
        super().__init__(PROJECT_NAME)
        from . import hookspec as broker_hookspec

        self.add_hookspecs(broker_hookspec)
        self._services: dict[str, CondaService] = {}
        for service in services:
            self.add(service)
        self.validate_dependencies()

    def load_provider_entry_points(self) -> None:
        discovered = entry_points()
        if hasattr(discovered, "select"):
            selected = discovered.select(group=ENTRY_POINT_GROUP)
        else:
            selected = discovered.get(ENTRY_POINT_GROUP, [])

        for entry_point in selected:
            plugin = entry_point.load()
            self.register(plugin, name=entry_point.name)

    def collect_provider_services(self) -> None:
        for result in self.hook.conda_broker_services():
            for service in result or ():
                self.add(service)
        self.validate_dependencies()

    def add(self, service: CondaService) -> None:
        if not isinstance(service, CondaService):
            raise ServiceValidationError(
                "conda_broker_services() must yield CondaService objects, "
                f"got {service!r}"
            )
        existing = self._services.get(service.name)
        if existing is not None:
            raise DuplicateServiceError(
                f"Service {service.name!r} provided by both "
                f"{existing.source!r} and {service.source!r}"
            )
        self._services[service.name] = service

    def get(self, name: str) -> CondaService:
        try:
            return self._services[name]
        except KeyError as exc:
            raise UnknownServiceError(f"Unknown service: {name}") from exc

    def all(self) -> list[CondaService]:
        return [self._services[name] for name in sorted(self._services)]

    def names(self) -> list[str]:
        return sorted(self._services)

    def enabled_defaults(self) -> list[str]:
        return [service.name for service in self.all() if service.enabled_by_default]

    def validate_dependencies(self) -> None:
        """Reject unknown dependencies and cycles before the supervisor starts."""
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str, stack: tuple[str, ...] = ()) -> None:
            if name in visited:
                return
            if name in visiting:
                cycle = " -> ".join((*stack, name))
                raise ServiceValidationError(f"Service dependency cycle: {cycle}")
            service = self.get(name)
            visiting.add(name)
            try:
                for dependency in service.dependencies:
                    if dependency not in self._services:
                        raise ServiceValidationError(
                            f"Service {name!r} depends on unknown service "
                            f"{dependency!r}"
                        )
                    visit(dependency, (*stack, name))
            finally:
                visiting.remove(name)
            visited.add(name)

        for name in self.names():
            visit(name)

    def __contains__(self, name: str) -> bool:
        return name in self._services


def discover_services() -> ServiceRegistry:
    """Load provider entry points from the private conda-broker pluggy group."""
    registry = ServiceRegistry()
    registry.load_provider_entry_points()
    registry.collect_provider_services()
    return registry
