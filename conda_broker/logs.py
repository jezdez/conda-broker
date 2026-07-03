"""Service log file helpers."""

from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING

from .models import validate_service_name

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import TextIO

    from .paths import ServicePaths


class LogManager:
    """Per-service log files with simple size-based rotation."""

    def __init__(self, paths: ServicePaths, *, max_bytes: int = 5_000_000) -> None:
        self.paths = paths
        self.max_bytes = max_bytes
        self.paths.ensure()

    def path_for(self, service: str) -> Path:
        validate_service_name(service)
        return self.paths.log_dir / f"{service}.log"

    def open_for_service(self, service: str) -> TextIO:
        path = self.path_for(service)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > self.max_bytes:
            previous = path.with_suffix(".log.1")
            if previous.exists():
                previous.unlink()
            path.replace(previous)
        return path.open("a", encoding="utf-8")

    def read_lines(
        self,
        service: str,
        *,
        lines: int = 50,
        include_previous: bool = False,
    ) -> list[str]:
        if lines <= 0:
            return []
        paths = []
        current = self.path_for(service)
        previous = current.with_suffix(".log.1")
        if include_previous and previous.exists():
            paths.append(previous)
        paths.append(current)

        buffer: deque[str] = deque(maxlen=lines)
        for path in paths:
            if not path.exists():
                continue
            with path.open(encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    buffer.append(line.rstrip("\n"))
        return list(buffer)

    def follow(self, service: str) -> Iterator[str]:
        path = self.path_for(service)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as stream:
            stream.seek(0, 2)
            while True:
                line = stream.readline()
                if line:
                    yield line.rstrip("\n")
                else:
                    time.sleep(0.25)
