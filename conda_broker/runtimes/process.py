"""Host process runtime backend."""

from __future__ import annotations

import os
import signal
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ..models import CondaService


class ProcessRuntime:
    """Start and stop services as local child processes."""

    def start(
        self,
        service: CondaService,
        *,
        extra_env: Mapping[str, str] | None = None,
    ) -> subprocess.Popen[bytes]:
        spec = service.merged_process()
        env: Mapping[str, str] = {**os.environ, **spec.env, **(extra_env or {})}
        if os.name != "nt":
            return subprocess.Popen(
                spec.argv,
                cwd=spec.cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        return subprocess.Popen(
            spec.argv,
            cwd=spec.cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
        )

    def stop(self, process: subprocess.Popen[bytes], service: CondaService) -> None:
        spec = service.merged_process()
        if os.name != "nt":
            try:
                os.killpg(process.pid, spec.signal_number)
                return
            except ProcessLookupError:
                return
        if process.poll() is not None:
            return
        if spec.stop_signal.upper() in {"BREAK", "CTRL_BREAK_EVENT", "SIGBREAK"}:
            try:
                process.send_signal(spec.signal_number)
                return
            except (AttributeError, ValueError, OSError):
                pass
        if self.taskkill(process.pid, force=False):
            return
        process.terminate()

    def kill(self, process: subprocess.Popen[bytes]) -> None:
        if os.name != "nt":
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except ProcessLookupError:
                return
        if process.poll() is not None:
            return
        self.taskkill(process.pid, force=True)
        if process.poll() is None:
            process.kill()

    def is_active(self, process: subprocess.Popen[bytes]) -> bool:
        """Return whether the managed process tree is still present."""
        if os.name == "nt":
            return process.poll() is None
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True

    @staticmethod
    def taskkill(pid: int, *, force: bool) -> bool:
        command = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            command.append("/F")
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return result.returncode == 0
