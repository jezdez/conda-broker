"""Path resolution for conda-broker state and logs."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path


def _platformdirs_path(function_name: str, appname: str) -> Path | None:
    try:
        import platformdirs
    except ImportError:
        return None
    return Path(getattr(platformdirs, function_name)(appname))


def _fallback_runtime_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return Path(root) / "conda" / "broker"
    xdg_runtime = os.environ.get("XDG_RUNTIME_DIR")
    if xdg_runtime:
        return Path(xdg_runtime) / "conda" / "broker"
    return Path(tempfile.gettempdir()) / f"conda-{os.getuid()}" / "broker"


def _fallback_log_dir() -> Path:
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or Path.home()
        return Path(root) / "conda" / "broker" / "logs"
    xdg_state = os.environ.get("XDG_STATE_HOME")
    root = Path(xdg_state) if xdg_state else Path.home() / ".local" / "state"
    return root / "conda" / "broker" / "logs"


def default_runtime_dir() -> Path:
    """Return the default runtime dir below the conda app namespace."""
    base = _platformdirs_path("user_runtime_dir", "conda")
    return (base / "broker") if base else _fallback_runtime_dir()


def default_log_dir() -> Path:
    """Return the default log dir below the conda app namespace."""
    base = _platformdirs_path("user_log_dir", "conda")
    return (base / "broker") if base else _fallback_log_dir()


def _conda_context_value(name: str) -> str | None:
    try:
        from conda.base.context import context
    except ImportError:
        return None
    value = getattr(context, name, None)
    return str(value) if value else None


@dataclass(frozen=True)
class ServicePaths:
    """Resolved filesystem locations used by one user-scoped broker."""

    runtime_dir: Path
    log_dir: Path

    @classmethod
    def resolve(
        cls,
        runtime_dir: Path | str | None = None,
        log_dir: Path | str | None = None,
    ) -> ServicePaths:
        runtime = (
            Path(runtime_dir)
            if runtime_dir is not None
            else Path(
                os.environ.get("CONDA_BROKER_RUNTIME_DIR")
                or _conda_context_value("broker_runtime_dir")
                or default_runtime_dir()
            )
        )
        logs = (
            Path(log_dir)
            if log_dir is not None
            else Path(
                os.environ.get("CONDA_BROKER_LOG_DIR")
                or _conda_context_value("broker_log_dir")
                or default_log_dir()
            )
        )
        return cls(runtime_dir=runtime, log_dir=logs)

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
    def enabled_file(self) -> Path:
        return self.runtime_dir / "enabled.json"

    @property
    def events_file(self) -> Path:
        return self.runtime_dir / "events.jsonl"

    @property
    def state_lock_file(self) -> Path:
        return self.runtime_dir / "state.lock"

    @property
    def broker_log_file(self) -> Path:
        return self.log_dir / "broker.log"

    def ensure(self) -> None:
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
