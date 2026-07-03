"""Small filesystem primitives shared by broker state and IPC."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator
    from typing import Any, TextIO

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def atomic_write_json(path: Path, data: dict[str, Any], *, mode: int = 0o600) -> None:
    """Atomically write JSON and restrict permissions where the platform allows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
        try:
            tmp.chmod(mode)
        except OSError:
            pass
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


@contextmanager
def file_lock(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive cross-process advisory lock for a small state update."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as stream:
        _lock_stream(stream)
        try:
            yield stream
        finally:
            _unlock_stream(stream)


def _lock_stream(stream: TextIO) -> None:
    if os.name == "nt":
        stream.seek(0)
        if stream.read(1) == "":
            stream.write("\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)


def _unlock_stream(stream: TextIO) -> None:
    if os.name == "nt":
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
