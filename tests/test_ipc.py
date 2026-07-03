"""Tests for IPC server metadata handling."""

from __future__ import annotations

import pytest

from conda_broker.exceptions import BrokerNotRunningError
from conda_broker.ipc import ServerInfo, read_server_info, write_server_info


def test_read_server_info_accepts_loopback_hosts(tmp_path) -> None:
    server_file = tmp_path / "server.json"

    write_server_info(
        server_file,
        ServerInfo(host="127.0.0.1", port=12345, token="secret", pid=1),
    )

    assert read_server_info(server_file).host == "127.0.0.1"


@pytest.mark.parametrize("host", ["example.com", "192.0.2.1"])
def test_read_server_info_rejects_non_loopback_hosts(tmp_path, host: str) -> None:
    server_file = tmp_path / "server.json"
    write_server_info(
        server_file,
        ServerInfo(host=host, port=12345, token="secret", pid=1),
    )

    with pytest.raises(BrokerNotRunningError):
        read_server_info(server_file)


@pytest.mark.parametrize("port", [0, 65536])
def test_read_server_info_rejects_invalid_ports(tmp_path, port: int) -> None:
    server_file = tmp_path / "server.json"
    write_server_info(
        server_file,
        ServerInfo(host="127.0.0.1", port=port, token="secret", pid=1),
    )

    with pytest.raises(BrokerNotRunningError):
        read_server_info(server_file)
