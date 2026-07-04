"""Host process runtime backend."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import TextIO

    from ..models import CondaService


def _signal_number(name: str) -> int:
    upper = name.upper()
    if not upper.startswith("SIG"):
        upper = f"SIG{upper}"
    value = getattr(signal, upper, None)
    if isinstance(value, signal.Signals):
        return int(value)
    if isinstance(value, int):
        return value
    return int(signal.SIGTERM)


class ProcessRuntime:
    """Start and stop services as local child processes."""

    def start(
        self,
        service: CondaService,
        log_file: TextIO,
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        spec = service.merged_process()
        env: Mapping[str, str] = {**os.environ, **spec.env, **(extra_env or {})}
        if os.name != "nt":
            return subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                start_new_session=True,
            )
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(
            spec.argv,
            cwd=spec.cwd,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            creationflags=creationflags,
        )

    def stop(self, process: subprocess.Popen[str], service: CondaService) -> None:
        if process.poll() is not None:
            return
        spec = service.merged_process()
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), _signal_number(spec.stop_signal))
                return
            except ProcessLookupError:
                return
        if spec.stop_signal.upper() in {"BREAK", "CTRL_BREAK_EVENT", "SIGBREAK"}:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
                return
            except (AttributeError, ValueError, OSError):
                pass
        process.terminate()

    def kill(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        if os.name != "nt":
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                return
            except ProcessLookupError:
                return
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if process.poll() is None:
            process.kill()
