"""Tests for IPC server metadata handling."""

from __future__ import annotations

import pytest

from conda_broker.exceptions import BrokerNotRunningError, IpcError
from conda_broker.ipc import MAX_MESSAGE_BYTES, IpcClient, ServerInfo


def test_read_server_info_accepts_loopback_hosts(service_paths) -> None:
    server_file = service_paths.server_file
    ServerInfo(host="127.0.0.1", port=12345, token="secret", pid=1).write(service_paths)

    assert ServerInfo.read(server_file).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["example.com", "192.0.2.1"])
def test_read_server_info_rejects_non_loopback_hosts(service_paths, host: str) -> None:
    server_file = service_paths.server_file
    ServerInfo(host=host, port=12345, token="secret", pid=1).write(service_paths)

    with pytest.raises(BrokerNotRunningError):
        ServerInfo.read(server_file)


@pytest.mark.parametrize("port", [0, 65536])
def test_read_server_info_rejects_invalid_ports(service_paths, port: int) -> None:
    server_file = service_paths.server_file
    ServerInfo(host="127.0.0.1", port=port, token="secret", pid=1).write(service_paths)

    with pytest.raises(BrokerNotRunningError):
        ServerInfo.read(server_file)


def test_call_rejects_oversized_request_before_connecting(service_paths) -> None:
    server_file = service_paths.server_file
    ServerInfo(host="127.0.0.1", port=1, token="secret", pid=1).write(service_paths)

    with pytest.raises(IpcError, match="request is too large"):
        IpcClient(server_file).call(
            "emit_event",
            {"payload": "x" * MAX_MESSAGE_BYTES},
        )
