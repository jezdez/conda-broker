"""Service log file helpers."""

from __future__ import annotations

import threading
import time
import traceback
from collections import deque
from contextlib import suppress
from typing import TYPE_CHECKING

from .models import ServiceName

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path
    from typing import IO, TextIO

    from .paths import ServicePaths


class LogManager:
    """Per-service log files with simple size-based rotation."""

    def __init__(self, paths: ServicePaths, *, max_bytes: int = 5_000_000) -> None:
        self.paths = paths
        self.max_bytes = max_bytes
        self.paths.ensure()

    def path_for(self, service: str) -> Path:
        ServiceName(service)
        return self.paths.log_dir / f"{service}.log"

    def open_for_service(self, service: str) -> TextIO:
        path = self.path_for(service)
        self.paths.ensure()
        self.paths.rotate(path, max_bytes=self.max_bytes)
        stream = path.open("a", encoding="utf-8")
        self.paths.secure(path)
        return stream

    def start_capture(self, service: str, source: IO[bytes]) -> threading.Thread:
        """Copy process output into a rotating service log on a background thread."""
        thread = threading.Thread(
            target=self.capture,
            args=(service, source),
            name=f"conda-broker-log-{service}",
            daemon=True,
        )
        thread.start()
        return thread

    def capture(self, service: str, source: IO[bytes]) -> None:
        read = getattr(source, "read1", source.read)
        writer: RotatingLog | None = None
        try:
            try:
                writer = RotatingLog(
                    self.path_for(service),
                    max_bytes=self.max_bytes,
                    paths=self.paths,
                )
            except OSError:
                traceback.print_exc()
                self.drain(read)
                return
            while chunk := read(64 * 1024):
                try:
                    writer.write(chunk)
                except OSError:
                    traceback.print_exc()
                    with suppress(OSError):
                        writer.close()
                    writer = None
                    self.drain(read)
                    return
        except (OSError, ValueError):
            traceback.print_exc()
        finally:
            if writer is not None:
                with suppress(OSError):
                    writer.close()
            with suppress(OSError, ValueError):
                source.close()

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
        self.paths.ensure()
        stream = path.open("a+", encoding="utf-8")
        try:
            self.paths.secure(path)
            identity = self.file_identity(path)
            stream.seek(0, 2)
            while True:
                line = stream.readline()
                if line:
                    yield line.rstrip("\n")
                elif self.should_reopen(path, identity, stream.tell()):
                    stream.close()
                    self.paths.ensure()
                    stream = path.open("a+", encoding="utf-8")
                    self.paths.secure(path)
                    identity = self.file_identity(path)
                    stream.seek(0)
                else:
                    time.sleep(0.25)
        finally:
            stream.close()

    @staticmethod
    def file_identity(path: Path) -> tuple[int, int] | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_dev, stat.st_ino)

    @staticmethod
    def should_reopen(
        path: Path,
        identity: tuple[int, int] | None,
        position: int,
    ) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return True
        if identity is not None and (stat.st_dev, stat.st_ino) != identity:
            return True
        return stat.st_size < position

    @staticmethod
    def drain(read) -> None:
        try:
            while read(64 * 1024):
                pass
        except (OSError, ValueError):
            pass


class RotatingLog:
    def __init__(
        self,
        path: Path,
        *,
        max_bytes: int,
        paths: ServicePaths,
    ) -> None:
        self.path = path
        self.max_bytes = max_bytes
        self.paths = paths
        paths.ensure()
        paths.rotate(path, max_bytes=max_bytes)
        self._stream = path.open("ab", buffering=0)
        paths.secure(path)
        self._size = path.stat().st_size

    def write(self, data: bytes) -> None:
        if self.max_bytes <= 0:
            self._stream.write(data)
            self._size += len(data)
            return
        offset = 0
        while offset < len(data):
            if self._size >= self.max_bytes and not self.rotate():
                chunk = data[offset:]
                self._stream.write(chunk)
                self._size += len(chunk)
                return
            remaining = self.max_bytes - self._size
            chunk = data[offset : offset + remaining]
            self._stream.write(chunk)
            self._size += len(chunk)
            offset += len(chunk)

    def close(self) -> None:
        if not self._stream.closed:
            self._stream.close()

    def rotate(self) -> bool:
        self._stream.close()
        rotated = self.paths.rotate(self.path, max_bytes=self.max_bytes)
        self._stream = self.path.open("ab", buffering=0)
        self.paths.secure(self.path)
        self._size = self.path.stat().st_size
        return rotated is not None
