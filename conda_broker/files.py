"""Cross-platform advisory file locking."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


@dataclass
class FileLock:
    """One held advisory file lock."""

    path: Path
    blocking: bool = True
    _stream: TextIO | None = field(default=None, init=False, repr=False)

    @property
    def stream(self) -> TextIO:
        if self._stream is None:
            raise RuntimeError("File lock is not acquired")
        return self._stream

    def acquire(self) -> FileLock:
        if self._stream is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.path.parent.chmod(0o700)
        except OSError:
            pass
        stream = self.path.open("a+", encoding="utf-8")
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        try:
            if os.name == "nt":
                stream.seek(0, os.SEEK_END)
                if stream.tell() == 0:
                    stream.write("\0")
                    stream.flush()
                stream.seek(0)
                mode = msvcrt.LK_LOCK if self.blocking else msvcrt.LK_NBLCK
                try:
                    msvcrt.locking(stream.fileno(), mode, 1)
                except OSError as exc:
                    if not self.blocking:
                        raise BlockingIOError from exc
                    raise
            else:
                operation = fcntl.LOCK_EX | (0 if self.blocking else fcntl.LOCK_NB)
                fcntl.flock(stream.fileno(), operation)
        except BaseException:
            stream.close()
            raise
        self._stream = stream
        return self

    def release(self) -> None:
        if self._stream is None:
            return
        try:
            if os.name == "nt":
                self._stream.seek(0)
                msvcrt.locking(self._stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._stream.fileno(), fcntl.LOCK_UN)
        finally:
            self._stream.close()
            self._stream = None

    def __enter__(self) -> FileLock:
        return self.acquire()

    def __exit__(self, *exc_info: object) -> None:
        self.release()
