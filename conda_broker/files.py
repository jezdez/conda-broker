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

PRIVATE_DIR_MODE = 0o700
PRIVATE_FILE_MODE = 0o600


def ensure_private_dir(path: Path, *, mode: int = PRIVATE_DIR_MODE) -> None:
    """Create a directory and restrict traversal where the platform allows."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(mode)
    except OSError:
        pass


def restrict_permissions(path: Path, *, mode: int = PRIVATE_FILE_MODE) -> None:
    """Restrict file permissions where the platform allows."""
    try:
        path.chmod(mode)
    except OSError:
        pass


def atomic_write_json(path: Path, data: dict[str, Any], *, mode: int = 0o600) -> None:
    """Atomically write JSON and restrict permissions where the platform allows."""
    ensure_private_dir(path.parent)
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
        restrict_permissions(tmp, mode=mode)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    """Atomically write text and restrict permissions where the platform allows."""
    ensure_private_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
        restrict_permissions(tmp, mode=mode)
        tmp.replace(path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def rotate_file(path: Path, *, max_bytes: int, mode: int = 0o600) -> Path | None:
    """Rotate *path* to ``<name>.1`` when it is larger than *max_bytes*."""
    if max_bytes <= 0:
        return None
    try:
        if path.stat().st_size <= max_bytes:
            return None
    except FileNotFoundError:
        return None

    previous = path.with_name(f"{path.name}.1")
    try:
        previous.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        return None
    try:
        path.replace(previous)
    except OSError:
        return None
    restrict_permissions(previous, mode=mode)
    return previous


@contextmanager
def file_lock(path: Path) -> Iterator[TextIO]:
    """Hold an exclusive cross-process advisory lock for a small state update."""
    ensure_private_dir(path.parent)
    with path.open("a+", encoding="utf-8") as stream:
        restrict_permissions(path)
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
