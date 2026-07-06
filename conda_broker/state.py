"""Persistent broker state and event storage."""

from __future__ import annotations

import json
import threading
from collections import deque
from typing import TYPE_CHECKING

from .files import atomic_write_json, file_lock, restrict_permissions, rotate_file
from .models import ServiceEvent

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path
    from typing import Any

    from .paths import ServicePaths


class StateStore:
    """Small JSON-backed state store for enabled services and events."""

    def __init__(
        self, paths: ServicePaths, *, max_event_bytes: int = 5_000_000
    ) -> None:
        self.paths = paths
        self.max_event_bytes = max_event_bytes
        self._lock = threading.Lock()
        self.paths.ensure()

    def enabled_services(self) -> set[str]:
        with self._lock:
            with file_lock(self.paths.state_lock_file):
                return self._read_enabled()

    def set_enabled(self, services: Iterable[str], enabled: bool) -> set[str]:
        with self._lock:
            with file_lock(self.paths.state_lock_file):
                current = self._read_enabled()
                for service in services:
                    if enabled:
                        current.add(service)
                    else:
                        current.discard(service)
                atomic_write_json(
                    self.paths.enabled_file,
                    {"enabled": sorted(current)},
                )
                return current

    def seed_enabled_defaults(self, services: Iterable[str]) -> None:
        if self.paths.enabled_file.exists():
            return
        self.set_enabled(services, True)

    def emit(
        self,
        event_type: str,
        *,
        service: str | None = None,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> ServiceEvent:
        event = ServiceEvent(
            type=event_type,
            service=service,
            message=message,
            data=data or {},
        )
        line = json.dumps(event.to_dict(), sort_keys=True)
        with self._lock:
            with file_lock(self.paths.state_lock_file):
                rotate_file(self.paths.events_file, max_bytes=self.max_event_bytes)
                with self.paths.events_file.open("a", encoding="utf-8") as stream:
                    restrict_permissions(self.paths.events_file)
                    stream.write(line + "\n")
        return event

    def read_events(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        with self._lock:
            with file_lock(self.paths.state_lock_file):
                return self._read_events_unlocked(
                    self._event_paths(),
                    limit=limit,
                )

    def _read_enabled(self) -> set[str]:
        path = self.paths.enabled_file
        if not path.exists():
            return set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return set()
        enabled = data.get("enabled", [])
        if not isinstance(enabled, list):
            return set()
        return {str(item) for item in enabled}

    @staticmethod
    def _read_events_unlocked(
        paths: Iterable[Path],
        *,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        if limit is not None and limit <= 0:
            return []
        rows: deque[dict[str, Any]] = deque(maxlen=limit)
        for path in paths:
            if not path.exists():
                continue
            with path.open(encoding="utf-8") as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    rows.append(row)
        return list(rows)

    def _event_paths(self) -> list[Path]:
        previous = self.paths.events_file.with_name(f"{self.paths.events_file.name}.1")
        return [previous, self.paths.events_file]
