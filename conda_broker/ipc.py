"""Authenticated localhost JSON-RPC helpers."""

from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from typing import TYPE_CHECKING

from .exceptions import (
    BrokerNotRunningError,
    IpcAuthError,
    IpcError,
    RuntimeUnavailableError,
    ServiceValidationError,
    UnknownServiceError,
)

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

    from .paths import ServicePaths

HOST = "127.0.0.1"
MAX_MESSAGE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ServerInfo:
    """Connection details written by the broker."""

    host: str
    port: int
    token: str
    pid: int
    instance_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "token": self.token,
            "pid": self.pid,
            "instance_id": self.instance_id,
        }

    @classmethod
    def read(cls, path: Path) -> ServerInfo:
        if not path.exists():
            raise BrokerNotRunningError("conda-broker broker is not running")
        data = json.loads(path.read_text(encoding="utf-8"))
        host = str(data["host"])
        try:
            loopback = host == "localhost" or ip_address(host).is_loopback
        except ValueError:
            loopback = False
        if not loopback:
            raise BrokerNotRunningError(
                "conda-broker broker server file does not point to localhost"
            )
        port = int(data["port"])
        if not 0 < port <= 65535:
            raise BrokerNotRunningError(
                "conda-broker broker server file contains an invalid port"
            )
        return cls(
            host=host,
            port=port,
            token=str(data["token"]),
            pid=int(data["pid"]),
            instance_id=str(data.get("instance_id", "")),
        )

    def write(self, paths: ServicePaths) -> None:
        paths.write_json(paths.server_file, self.to_dict())


@dataclass(frozen=True)
class IpcClient:
    """Authenticated JSON-RPC client for one broker server file."""

    server_file: Path

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = 2.0,
    ) -> dict[str, Any]:
        try:
            info = ServerInfo.read(self.server_file)
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            raise BrokerNotRunningError("conda-broker broker is not reachable") from exc

        request = {
            "token": info.token,
            "method": method,
            "params": params or {},
        }
        payload = json.dumps(request).encode("utf-8") + b"\n"
        if len(payload) > MAX_MESSAGE_BYTES:
            raise IpcError("IPC request is too large")
        try:
            with socket.create_connection(
                (info.host, info.port),
                timeout=timeout,
            ) as connection:
                connection.sendall(payload)
                with connection.makefile("r", encoding="utf-8") as stream:
                    line = stream.readline(MAX_MESSAGE_BYTES + 1)
                    if len(line) > MAX_MESSAGE_BYTES:
                        raise IpcError("IPC response is too large")
                    response = json.loads(line)
        except OSError as exc:
            raise BrokerNotRunningError("conda-broker broker is not reachable") from exc
        except (json.JSONDecodeError, UnicodeError) as exc:
            raise IpcError("conda-broker broker returned invalid JSON") from exc

        if not isinstance(response, dict):
            raise IpcError("conda-broker broker returned an invalid response")
        if response.get("ok"):
            result = response.get("result", {})
            return result if isinstance(result, dict) else {"result": result}

        error = response.get("error", {})
        code = error.get("code", "error") if isinstance(error, dict) else "error"
        message = (
            error.get("message", "IPC request failed")
            if isinstance(error, dict)
            else str(error)
        )
        errors = {
            "unauthorized": IpcAuthError,
            "unknown-service": UnknownServiceError,
            "runtime-unavailable": RuntimeUnavailableError,
            "service-validation": ServiceValidationError,
        }
        raise errors.get(code, IpcError)(message)

    def ping(self) -> bool:
        try:
            self.call("ping", timeout=0.5)
        except (BrokerNotRunningError, IpcAuthError, IpcError):
            return False
        return True
