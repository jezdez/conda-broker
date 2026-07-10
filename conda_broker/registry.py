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
        self._service_providers: dict[str, str] = {}
        self.provider_errors: list[dict[str, str]] = []
        for service in services:
            self.add(service)
        self.validate_dependencies()

    @classmethod
    def discover(cls) -> ServiceRegistry:
        """Load services from the private conda-broker pluggy group."""
        registry = cls()
        registry.load_provider_entry_points()
        registry.collect_provider_services()
        return registry

    def load_provider_entry_points(self) -> None:
        discovered = entry_points()
        if hasattr(discovered, "select"):
            selected = discovered.select(group=ENTRY_POINT_GROUP)
        else:
            selected = discovered.get(ENTRY_POINT_GROUP, [])

        for entry_point in selected:
            try:
                plugin = entry_point.load()
                self.register(plugin, name=entry_point.name)
            except Exception as exc:
                self.record_provider_error(entry_point.name, "load", exc)

    def collect_provider_services(self) -> None:
        named_plugins = sorted(
            (
                (name, plugin)
                for name, plugin in self.list_name_plugin()
                if plugin is not None
            ),
            key=lambda item: item[0],
        )
        plugins = {plugin for _, plugin in named_plugins}
        for provider, plugin in named_plugins:
            existing = set(self._services)
            try:
                hook = self.subset_hook_caller(
                    "conda_broker_services",
                    remove_plugins=plugins - {plugin},
                )
                for result in hook():
                    for service in result or ():
                        self.add(service)
                        self._service_providers[service.name] = provider
            except Exception as exc:
                for name in set(self._services) - existing:
                    self._services.pop(name, None)
                    self._service_providers.pop(name, None)
                self.record_provider_error(provider, "services", exc)

        for name, message in self.dependency_errors().items():
            provider = self._service_providers.pop(name, "unknown")
            self._services.pop(name, None)
            self.provider_errors.append(
                {
                    "provider": provider,
                    "phase": "dependencies",
                    "error": message,
                    "error_type": "ServiceValidationError",
                }
            )

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

    def startup_order(self, names: Iterable[str]) -> tuple[CondaService, ...]:
        """Resolve services and dependencies in launch order."""
        ordered: list[CondaService] = []
        visited: set[str] = set()
        pending = [(name, False) for name in reversed(tuple(names))]
        while pending:
            name, expanded = pending.pop()
            if name in visited:
                continue
            service = self.get(name)
            if expanded:
                visited.add(name)
                ordered.append(service)
                continue
            pending.append((name, True))
            pending.extend(
                (dependency, False)
                for dependency in reversed(service.dependencies)
                if dependency not in visited
            )
        return tuple(ordered)

    def validate_dependencies(self) -> None:
        """Reject unknown dependencies and cycles before the supervisor starts."""
        errors = self.dependency_errors()
        if errors:
            raise ServiceValidationError(errors[sorted(errors)[0]])

    def dependency_errors(self) -> dict[str, str]:
        """Return dependency validation errors keyed by invalid service."""
        errors: dict[str, str] = {}
        for name in self.names():
            service = self._services[name]
            missing = next(
                (
                    dependency
                    for dependency in service.dependencies
                    if dependency not in self._services
                ),
                None,
            )
            if missing is not None:
                errors[name] = (
                    f"Service {name!r} depends on unknown service {missing!r}"
                )

        visited: set[str] = set()
        for root in self.names():
            if root in visited:
                continue
            path: list[str] = []
            positions: dict[str, int] = {}
            stack: list[tuple[str, int]] = [(root, 0)]
            while stack:
                name, dependency_index = stack[-1]
                if name not in positions:
                    positions[name] = len(path)
                    path.append(name)
                dependencies = self._services[name].dependencies
                if dependency_index >= len(dependencies):
                    stack.pop()
                    positions.pop(name)
                    path.pop()
                    visited.add(name)
                    continue
                dependency = dependencies[dependency_index]
                stack[-1] = (name, dependency_index + 1)
                if dependency not in self._services or dependency in visited:
                    continue
                if dependency in positions:
                    cycle_names = path[positions[dependency] :]
                    cycle = " -> ".join((*cycle_names, dependency))
                    for member in cycle_names:
                        errors[member] = f"Service dependency cycle: {cycle}"
                    continue
                stack.append((dependency, 0))

        changed = True
        while changed:
            changed = False
            for name in self.names():
                if name in errors:
                    continue
                invalid = next(
                    (
                        dependency
                        for dependency in self._services[name].dependencies
                        if dependency in errors
                    ),
                    None,
                )
                if invalid is not None:
                    errors[name] = (
                        f"Service {name!r} depends on invalid service {invalid!r}"
                    )
                    changed = True
        return errors

    def record_provider_error(
        self,
        provider: str,
        phase: str,
        exc: Exception,
    ) -> None:
        self.provider_errors.append(
            {
                "provider": provider,
                "phase": phase,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        )

    def __contains__(self, name: str) -> bool:
        return name in self._services
