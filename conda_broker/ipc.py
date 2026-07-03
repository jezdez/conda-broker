"""Authenticated localhost JSON-RPC helpers."""

from __future__ import annotations

import json
import secrets
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from typing import TYPE_CHECKING

from .exceptions import BrokerNotRunningError, IpcAuthError, IpcError
from .files import atomic_write_json

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Any

HOST = "127.0.0.1"


@dataclass(frozen=True)
class ServerInfo:
    """Connection details written by the broker."""

    host: str
    port: int
    token: str
    pid: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "host": self.host,
            "port": self.port,
            "token": self.token,
            "pid": self.pid,
        }


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def write_server_info(path: Path, info: ServerInfo) -> None:
    atomic_write_json(path, info.to_dict())


def read_server_info(path: Path) -> ServerInfo:
    if not path.exists():
        raise BrokerNotRunningError("conda-broker broker is not running")
    data = json.loads(path.read_text(encoding="utf-8"))
    host = str(data["host"])
    if not _is_loopback_host(host):
        raise BrokerNotRunningError(
            "conda-broker broker server file does not point to localhost"
        )
    port = int(data["port"])
    if not 0 < port <= 65535:
        raise BrokerNotRunningError(
            "conda-broker broker server file contains an invalid port"
        )
    return ServerInfo(
        host=host,
        port=port,
        token=str(data["token"]),
        pid=int(data["pid"]),
    )


def _is_loopback_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def call(
    server_file: Path,
    method: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: float = 2.0,
) -> dict[str, Any]:
    """Call the broker and return the result payload."""
    try:
        info = read_server_info(server_file)
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
        raise BrokerNotRunningError("conda-broker broker is not reachable") from exc

    request = {
        "token": info.token,
        "method": method,
        "params": params or {},
    }
    try:
        with socket.create_connection((info.host, info.port), timeout=timeout) as sock:
            sock.sendall(json.dumps(request).encode("utf-8") + b"\n")
            with sock.makefile("r", encoding="utf-8") as stream:
                response = json.loads(stream.readline())
    except OSError as exc:
        raise BrokerNotRunningError("conda-broker broker is not reachable") from exc
    except json.JSONDecodeError as exc:
        raise IpcError("conda-broker broker returned invalid JSON") from exc

    if response.get("ok"):
        result = response.get("result", {})
        if isinstance(result, dict):
            return result
        return {"result": result}

    error = response.get("error", {})
    code = error.get("code", "error") if isinstance(error, dict) else "error"
    message = (
        error.get("message", "IPC request failed")
        if isinstance(error, dict)
        else str(error)
    )
    if code == "unauthorized":
        raise IpcAuthError(message)
    raise IpcError(message)


def ping(server_file: Path) -> bool:
    try:
        call(server_file, "ping")
    except (BrokerNotRunningError, IpcError):
        return False
    return True
