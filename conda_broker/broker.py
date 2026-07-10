"""Broker entry point and JSON-RPC method dispatch."""

from __future__ import annotations

import argparse
import json
import os
import secrets
import signal
import socketserver
import sys
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, cast

from .exceptions import (
    CondaBrokerError,
    IpcAuthError,
    ServiceValidationError,
)
from .ipc import HOST, MAX_MESSAGE_BYTES, ServerInfo
from .paths import ServicePaths
from .registry import ServiceRegistry
from .state import StateStore
from .supervisor import ServiceSupervisor

if TYPE_CHECKING:
    from typing import Any

    from .files import FileLock


class _RpcServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    broker_ref: BrokerServer


class _RpcHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            self.connection.settimeout(5.0)
            line = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
            if len(line) > MAX_MESSAGE_BYTES:
                raise ValueError("IPC request is too large")
            request = json.loads(line.decode("utf-8"))
            if not isinstance(request, dict):
                raise ValueError("IPC request must be a JSON object")
            server = cast("_RpcServer", self.server)
            result = server.broker_ref.dispatch(request)
            response = {"ok": True, "result": result}
        except Exception as exc:
            response = {
                "ok": False,
                "error": {
                    "code": (
                        exc.code if isinstance(exc, CondaBrokerError) else "error"
                    ),
                    "message": str(exc),
                },
            }
        payload = json.dumps(response).encode("utf-8") + b"\n"
        if len(payload) > MAX_MESSAGE_BYTES:
            payload = (
                json.dumps(
                    {
                        "ok": False,
                        "error": {
                            "code": "error",
                            "message": "IPC response is too large",
                        },
                    }
                ).encode("utf-8")
                + b"\n"
            )
        self.wfile.write(payload)


@dataclass(frozen=True)
class BrokerRequest:
    """One authenticated and normalized broker RPC request."""

    method: str
    params: dict[str, Any]

    @classmethod
    def authenticate(
        cls,
        payload: dict[str, Any],
        token: str,
    ) -> BrokerRequest:
        supplied_token = payload.get("token")
        if not isinstance(supplied_token, str) or not secrets.compare_digest(
            supplied_token, token
        ):
            raise IpcAuthError("Invalid broker token")
        params = payload.get("params") or {}
        return cls(
            method=str(payload.get("method", "")),
            params=params if isinstance(params, dict) else {},
        )

    def service_names(self, *, optional: bool = False) -> list[str] | None:
        value = self.params.get("services")
        if value is None and optional:
            return None
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(item) for item in value]
        return []


@dataclass
class BrokerLease:
    """Single-instance lock and ownership-tagged broker metadata."""

    paths: ServicePaths
    instance_id: str
    lock: FileLock | None = field(default=None, init=False)

    def acquire(self) -> BrokerLease:
        lock = self.paths.lock(self.paths.lock_file, blocking=False)
        try:
            lock.acquire()
        except BlockingIOError:
            raise SystemExit("conda-broker broker is already running") from None
        try:
            stream = lock.stream
            stream.seek(0)
            stream.truncate()
            json.dump(
                {
                    "pid": os.getpid(),
                    "instance_id": self.instance_id,
                    "runtime_dir": str(self.paths.runtime_dir),
                },
                stream,
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            lock.release()
            raise
        self.lock = lock
        return self

    def release(self) -> None:
        for path in (self.paths.server_file, self.paths.pid_file):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("instance_id") == self.instance_id:
                    path.unlink()
            except (AttributeError, FileNotFoundError, json.JSONDecodeError, OSError):
                continue
        if self.lock is not None:
            self.lock.release()
            self.lock = None

    def __enter__(self) -> BrokerLease:
        return self.acquire()

    def __exit__(self, *exc_info: object) -> None:
        self.release()


class BrokerServer:
    """Owns the service registry, supervisor, and JSON-RPC server."""

    def __init__(self, paths: ServicePaths) -> None:
        self.paths = paths
        self.registry = ServiceRegistry.discover()
        self.state = StateStore(paths)
        for error in self.registry.provider_errors:
            self.state.emit("provider.failed", data=error)
        self.state.seed_enabled_defaults(self.registry.enabled_defaults())
        self.instance_id = uuid.uuid4().hex
        self.supervisor = ServiceSupervisor(
            self.registry,
            self.state,
            paths,
            instance_id=self.instance_id,
        )
        self.token = secrets.token_urlsafe(32)
        self.server: _RpcServer | None = None
        self.lease = BrokerLease(paths, self.instance_id)
        self._stopping = threading.Event()

    def run(self) -> int:
        self.paths.ensure()
        started = False
        signal_handlers: dict[int, Any] = {}
        with self.lease:
            try:
                self.paths.write_json(
                    self.paths.pid_file,
                    {"pid": os.getpid(), "instance_id": self.instance_id},
                )
                self.supervisor.reconcile_stale_processes()
                with _RpcServer((HOST, 0), _RpcHandler) as server:
                    self.server = server
                    server.broker_ref = self
                    for signum in (signal.SIGINT, signal.SIGTERM):
                        try:
                            signal_handlers[signum] = signal.getsignal(signum)
                            signal.signal(signum, self.stop)
                        except (OSError, ValueError):
                            continue
                    port = int(server.server_address[1])
                    ServerInfo(
                        host=HOST,
                        port=port,
                        token=self.token,
                        pid=os.getpid(),
                        instance_id=self.instance_id,
                    ).write(self.paths)
                    self.state.emit(
                        "broker.started",
                        data={
                            "pid": os.getpid(),
                            "port": port,
                            "instance_id": self.instance_id,
                        },
                    )
                    started = True
                    self.supervisor.start_monitor()
                    self.supervisor.start_enabled_services()
                    server.serve_forever(poll_interval=0.5)
            finally:
                for signum, handler in signal_handlers.items():
                    try:
                        signal.signal(signum, handler)
                    except (OSError, ValueError):
                        continue
                self.supervisor.shutdown()
                if started:
                    self.state.emit(
                        "broker.stopped",
                        data={
                            "pid": os.getpid(),
                            "instance_id": self.instance_id,
                        },
                    )
        return 0

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        rpc = BrokerRequest.authenticate(request, self.token)
        method = rpc.method
        params = rpc.params

        if method == "ping":
            return {"status": "ok"}
        if method == "status":
            return self.supervisor.status(params.get("service"))
        if method == "wait_service":
            service = str(params.get("service", ""))
            timeout_s = float(params.get("timeout_s", 30.0))
            status = self.supervisor.wait_until_ready(service, timeout_s=timeout_s)
            return {"services": [status.to_dict()]}
        if method == "endpoint":
            service = str(params.get("service", ""))
            endpoint = str(params.get("endpoint", "default"))
            status = self.supervisor.status_many([service])[0].to_dict()
            endpoints = status.get("endpoints")
            selected = None
            if isinstance(endpoints, dict):
                value = endpoints.get(endpoint)
                if isinstance(value, dict):
                    selected = value
            return {
                "service": service,
                "endpoint": selected,
                "endpoints": endpoints if isinstance(endpoints, dict) else {},
            }
        if method == "list_services":
            return {
                "services": [service.to_dict() for service in self.registry.all()],
                "enabled": sorted(self.state.enabled_services()),
                "provider_errors": list(self.registry.provider_errors),
            }
        if method == "start_services":
            names = rpc.service_names()
            if not names:
                raise ServiceValidationError("Choose at least one service to start")
            statuses, started = self.supervisor.start_services_with_ownership(names)
            return {
                "services": [status.to_dict() for status in statuses],
                "started": started,
            }
        if method == "stop_services":
            names = rpc.service_names(optional=True)
            statuses = self.supervisor.stop_services(names)
            return {"services": [status.to_dict() for status in statuses]}
        if method == "restart_services":
            names = rpc.service_names(optional=True)
            statuses = self.supervisor.restart_services(names)
            return {"services": [status.to_dict() for status in statuses]}
        if method == "set_enabled":
            services = rpc.service_names() or []
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
            self.stop()
            return {"stopping": True}
        raise ValueError(f"Unknown broker method: {method}")

    def stop(self, *_signal_args: object) -> None:
        if not self._stopping.is_set() and self.server is not None:
            self._stopping.set()
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def main(args: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the conda-broker broker.")
    parser.add_argument("--runtime-dir", type=Path, default=None)
    parser.add_argument("--log-dir", type=Path, default=None)
    parsed = parser.parse_args(args)
    paths = ServicePaths.resolve(parsed.runtime_dir, parsed.log_dir)
    return BrokerServer(paths).run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
