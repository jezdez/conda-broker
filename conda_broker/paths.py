"""Path resolution for conda-broker state and logs."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .files import FileLock

if TYPE_CHECKING:
    from typing import Any


@dataclass(frozen=True)
class ServicePaths:
    """Resolved filesystem locations used by one user-scoped broker."""

    runtime_dir: Path
    log_dir: Path

    @classmethod
    def default_runtime_dir(cls) -> Path:
        """Return the default runtime directory in the conda namespace."""
        try:
            import platformdirs
        except ImportError:
            base = None
        else:
            value = platformdirs.user_runtime_dir("conda")
            base = Path(value) if value else None
        if base is not None:
            return base / "broker"
        if os.name == "nt":
            root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
            return Path(root) / "conda" / "broker"
        xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
        if xdg_runtime:
            return Path(xdg_runtime) / "conda" / "broker"
        return Path(tempfile.gettempdir()) / f"conda-{os.getuid()}" / "broker"

    @classmethod
    def default_log_dir(cls) -> Path:
        """Return the default log directory in the conda namespace."""
        try:
            import platformdirs
        except ImportError:
            base = None
        else:
            value = platformdirs.user_log_dir("conda")
            base = Path(value) if value else None
        if base is not None:
            return base / "broker"
        if os.name == "nt":
            root = os.environ.get("LOCALAPPDATA") or Path.home()
            return Path(root) / "conda" / "broker" / "logs"
        xdg_state = os.environ.get("XDG_STATE_HOME")
        root = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
        return root / "conda" / "broker" / "logs"

    @classmethod
    def resolve(
        cls,
        runtime_dir: Path | str | None = None,
        log_dir: Path | str | None = None,
    ) -> ServicePaths:
        runtime_setting = None
        log_setting = None
        try:
            from conda.base.context import context
        except ImportError:
            pass
        else:
            runtime_setting = getattr(context, "broker_runtime_dir", None)
            log_setting = getattr(context, "broker_log_dir", None)
        runtime = (
            Path(runtime_dir)
            if runtime_dir is not None
            else Path(
                os.environ.get("CONDA_BROKER_RUNTIME_DIR")
                or runtime_setting
                or cls.default_runtime_dir()
            )
        )
        logs = (
            Path(log_dir)
            if log_dir is not None
            else Path(
                os.environ.get("CONDA_BROKER_LOG_DIR")
                or log_setting
                or cls.default_log_dir()
            )
        )
        return cls(
            runtime_dir=Path(os.path.abspath(os.path.expanduser(str(runtime)))),
            log_dir=Path(os.path.abspath(os.path.expanduser(str(logs)))),
        )

    @property
    def server_file(self) -> Path:
        return self.runtime_dir / "server.json"

    @property
    def pid_file(self) -> Path:
        return self.runtime_dir / "broker.pid"

    @property
    def lock_file(self) -> Path:
        return self.runtime_dir / "broker.lock"

    @property
    def startup_lock_file(self) -> Path:
        return self.runtime_dir / "broker.start.lock"

    @property
    def enabled_file(self) -> Path:
        return self.runtime_dir / "enabled.json"

    @property
    def events_file(self) -> Path:
        return self.runtime_dir / "events.jsonl"

    @property
    def processes_file(self) -> Path:
        return self.runtime_dir / "processes.json"

    @property
    def state_lock_file(self) -> Path:
        return self.runtime_dir / "state.lock"

    @property
    def broker_log_file(self) -> Path:
        return self.log_dir / "broker.log"

    def ensure(self) -> None:
        for path in (self.runtime_dir, self.log_dir):
            try:
                path.mkdir(parents=True)
                path.chmod(0o700)
            except FileExistsError:
                pass
            if path.is_symlink() or not path.is_dir():
                raise OSError(f"Broker path is not a directory: {path}")
            if os.name != "nt":
                stat = path.stat()
                if stat.st_uid != os.getuid():
                    raise PermissionError(
                        f"Broker path is not owned by the current user: {path}"
                    )
                if stat.st_mode & 0o077:
                    raise PermissionError(f"Broker path must have mode 0700: {path}")

    def secure(self, path: Path) -> None:
        """Restrict a file in this namespace to its owner where supported."""
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def write_json(self, path: Path, data: dict[str, Any]) -> None:
        """Atomically write a private JSON file in this namespace."""
        self.write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def write_text(self, path: Path, text: str) -> None:
        """Atomically write a private text file in this namespace."""
        self.ensure()
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
            self.secure(tmp)
            tmp.replace(path)
        except Exception:
            tmp.unlink(missing_ok=True)
            raise

    def rotate(self, path: Path, *, max_bytes: int) -> Path | None:
        """Rotate a private file to ``.1`` after it reaches its size limit."""
        if max_bytes <= 0:
            return None
        try:
            if path.stat().st_size < max_bytes:
                return None
        except FileNotFoundError:
            return None
        previous = path.with_name(f"{path.name}.1")
        try:
            previous.unlink(missing_ok=True)
            path.replace(previous)
        except OSError:
            return None
        self.secure(previous)
        return previous

    def lock(self, path: Path, *, blocking: bool = True) -> FileLock:
        self.ensure()
        return FileLock(path, blocking=blocking)

    def lock_available(self, path: Path) -> bool:
        lock = self.lock(path, blocking=False)
        try:
            lock.acquire()
        except BlockingIOError:
            return False
        lock.release()
        return True
