"""Tests for broker dispatch behavior."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING

import pytest

from conda_broker.broker import BrokerServer
from conda_broker.exceptions import IpcAuthError

if TYPE_CHECKING:
    from conda_broker.paths import ServicePaths


def test_dispatch_rejects_bad_token(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    with pytest.raises(IpcAuthError):
        broker.dispatch({"token": "bad", "method": "ping", "params": {}})


def test_dispatch_ping(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    assert broker.dispatch({"token": broker.token, "method": "ping"}) == {
        "status": "ok"
    }


def test_dispatch_status_uses_broker_payload(service_paths: ServicePaths) -> None:
    broker = BrokerServer(service_paths)

    payload = broker.dispatch({"token": broker.token, "method": "status"})

    assert payload["broker"] == {"running": True}
    assert payload["services"] == []


def test_stale_pid_lock_is_recovered(service_paths: ServicePaths) -> None:
    service_paths.pid_file.write_text("999999999\n", encoding="utf-8")
    service_paths.lock_file.write_text("999999999\n", encoding="utf-8")
    broker = BrokerServer(service_paths)

    try:
        broker._acquire_lock()

        assert service_paths.lock_file.exists()
        assert service_paths.lock_file.read_text(encoding="utf-8").strip()
    finally:
        broker._cleanup_files()


def test_live_non_broker_stale_lock_is_recovered(service_paths: ServicePaths) -> None:
    service_paths.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    service_paths.lock_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    old = time.time() - 60
    os.utime(service_paths.lock_file, (old, old))
    broker = BrokerServer(service_paths)

    try:
        broker._acquire_lock()

        assert service_paths.lock_file.exists()
        assert "runtime_dir" in service_paths.lock_file.read_text(encoding="utf-8")
    finally:
        broker._cleanup_files()


def test_fresh_live_lock_is_treated_as_starting_broker(
    service_paths: ServicePaths,
) -> None:
    service_paths.pid_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    service_paths.lock_file.write_text(f"{os.getpid()}\n", encoding="utf-8")
    broker = BrokerServer(service_paths)

    try:
        with pytest.raises(SystemExit):
            broker._acquire_lock()
    finally:
        broker._cleanup_files()
