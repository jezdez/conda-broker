"""Broker entry point and JSON-RPC method dispatch."""

from __future__ import annotations

import argparse
import json
import os
import socketserver
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .ipc import HOST, ServerInfo, generate_token, ping, write_server_info
from .paths import ServicePaths
from .registry import discover_services
from .state import StateStore
from .supervisor import ServiceSupervisor

if TYPE_CHECKING:
    from typing import Any

LOCK_STARTUP_GRACE_S = 10.0


class _RpcServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    broker_ref: BrokerServer


class _RpcHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(1_000_000)
        try:
            request = json.loads(line.decode("utf-8"))
            server = cast("_RpcServer", self.server)
            result = server.broker_ref.dispatch(request)
            response = {"ok": True, "result": result}
        except Exception as exc:
            code = "error"
            if exc.__class__.__name__ == "IpcAuthError":
                code = "unauthorized"
            response = {
                "ok": False,
                "error": {"code": code, "message": str(exc)},
            }
        self.wfile.write(json.dumps(response).encode("utf-8") + b"\n")


class BrokerServer:
    """Owns the service registry, supervisor, and JSON-RPC server."""

    def __init__(self, paths: ServicePaths) -> None:
        self.paths = paths
        self.registry = discover_services()
        self.state = StateStore(paths)
        self.state.seed_enabled_defaults(self.registry.enabled_defaults())
        self.supervisor = ServiceSupervisor(self.registry, self.state, paths)
        self.token = generate_token()
        self.server: _RpcServer | None = None
        self._lock_fd: int | None = None

    def run(self) -> int:
        self.paths.ensure()
        self._acquire_lock()
        self.paths.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
        self.supervisor.start_monitor()

        try:
            with _RpcServer((HOST, 0), _RpcHandler) as server:
                self.server = server
                server.broker_ref = self
                port = int(server.server_address[1])
                write_server_info(
                    self.paths.server_file,
                    ServerInfo(host=HOST, port=port, token=self.token, pid=os.getpid()),
                )
                self.state.emit(
                    "broker.started",
                    data={"pid": os.getpid(), "port": port},
                )
                self.supervisor.start_enabled_services()
                server.serve_forever(poll_interval=0.5)
        finally:
            self.supervisor.shutdown()
            self.state.emit("broker.stopped", data={"pid": os.getpid()})
            self._cleanup_files()
        return 0

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("token") != self.token:
            from .exceptions import IpcAuthError

            raise IpcAuthError("Invalid broker token")

        method = str(request.get("method", ""))
        params = request.get("params") or {}
        if not isinstance(params, dict):
            params = {}

        if method == "ping":
            return {"status": "ok"}
        if method == "status":
            return self.supervisor.status(params.get("service"))
        if method == "list_services":
            return {
                "services": [service.to_dict() for service in self.registry.all()],
                "enabled": sorted(self.state.enabled_services()),
            }
        if method == "start_services":
            names = _optional_service_names(params.get("services"))
            statuses = self.supervisor.start_services(names)
            return {"services": [status.to_dict() for status in statuses]}
        if method == "stop_services":
            names = _optional_service_names(params.get("services"))
            statuses = self.supervisor.stop_services(names)
            return {"services": [status.to_dict() for status in statuses]}
        if method == "restart_services":
            names = _optional_service_names(params.get("services"))
            statuses = self.supervisor.restart_services(names)
            return {"services": [status.to_dict() for status in statuses]}
        if method == "set_enabled":
            services = _service_names(params.get("services") or [])
            for service in services:
                self.registry.get(service)
            enabled = bool(params.get("enabled"))
            self.state.set_enabled(services, enabled)
            for service in services:
                self.state.emit(
                    "service.enabled" if enabled else "service.disabled",
                    service=service,
                )
            return {"enabled": sorted(self.state.enabled_services())}
        if method == "events":
            return {"events": self.state.read_events(limit=params.get("limit"))}
        if method == "emit_event":
            event = self.state.emit(
                str(params.get("type", "plugin.event")),
                service=params.get("service"),
                message=str(params.get("message", "")),
                data=params.get("data") if isinstance(params.get("data"), dict) else {},
            )
            return {"event": event.to_dict()}
        if method == "shutdown":
            threading.Thread(target=self.stop, daemon=True).start()
            return {"stopping": True}
        raise ValueError(f"Unknown broker method: {method}")

    def stop(self) -> None:
        if self.server is not None:
            self.server.shutdown()

    def _acquire_lock(self) -> None:
        self.paths.runtime_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(
                self.paths.lock_file,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            if self._existing_broker_active():
                raise SystemExit("conda-broker broker is already running")
            self._cleanup_files()
            fd = os.open(
                self.paths.lock_file,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        os.write(
            fd,
            json.dumps(
                {
                    "pid": os.getpid(),
                    "created_at": time.time(),
                    "runtime_dir": str(self.paths.runtime_dir),
                },
                sort_keys=True,
            ).encode()
            + b"\n",
        )
        self._lock_fd = fd

    def _existing_broker_active(self) -> bool:
        pid = self._existing_pid()
        if pid is None or not self._pid_alive(pid):
            return False
        if ping(self.paths.server_file):
            return True
        return self._lock_file_is_fresh()

    def _existing_pid(self) -> int | None:
        for path in (self.paths.lock_file, self.paths.pid_file):
            try:
                text = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = text
            try:
                pid = int(data["pid"] if isinstance(data, dict) else data)
            except (KeyError, TypeError, ValueError):
                continue
            if pid > 0:
                return pid
        return None

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == "nt":
            return _windows_pid_alive(pid)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _lock_file_is_fresh(self) -> bool:
        try:
            age_s = time.time() - self.paths.lock_file.stat().st_mtime
        except OSError:
            return False
        return age_s < LOCK_STARTUP_GRACE_S

    def _cleanup_files(self) -> None:
        if self._lock_fd is not None:
            try:
                os.close(self._lock_fd)
            except OSError:
                pass
            self._lock_fd = None
        for path in (self.paths.server_file, self.paths.pid_file, self.paths.lock_file):
            try:
                path.unlink()
            except FileNotFoundError:
                pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the conda-broker broker.")
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    return parser


def _optional_service_names(value: object) -> list[str] | None:
    if value is None:
        return None
    return _service_names(value)


def _service_names(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def main(args: list[str] | None = None) -> int:
    parser = build_parser()
    parsed = parser.parse_args(args)
    paths = ServicePaths.resolve(parsed.runtime_dir, parsed.log_dir)
    return BrokerServer(paths).run()


def _windows_pid_alive(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    error_access_denied = 5
    process_query_limited_information = 0x1000
    still_active = 259

    kernel32 = getattr(ctypes, "WinDLL")("kernel32", use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    open_process.restype = wintypes.HANDLE
    get_exit_code_process = kernel32.GetExitCodeProcess
    get_exit_code_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    get_exit_code_process.restype = wintypes.BOOL
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = [wintypes.HANDLE]
    close_handle.restype = wintypes.BOOL
    get_last_error = getattr(ctypes, "get_last_error")

    handle = open_process(process_query_limited_information, False, pid)
    if not handle:
        return get_last_error() == error_access_denied
    try:
        exit_code = wintypes.DWORD()
        if not get_exit_code_process(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        close_handle(handle)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
