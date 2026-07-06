"""Tests for path, state, and log helpers."""

from __future__ import annotations

import json
import os

import pytest

from conda_broker import logs as logs_module
from conda_broker.files import (
    atomic_write_json,
    atomic_write_text,
    ensure_private_dir,
    file_lock,
)
from conda_broker.logs import LogManager
from conda_broker.paths import ServicePaths, default_log_dir, default_runtime_dir
from conda_broker.state import StateStore


def test_default_paths_use_conda_broker_namespace() -> None:
    paths = ServicePaths.resolve()

    assert paths.runtime_dir == default_runtime_dir()
    assert paths.log_dir == default_log_dir()
    assert paths.runtime_dir.name == "broker"
    assert paths.log_dir.name == "broker"
    assert "conda" in paths.runtime_dir.parts
    assert "conda" in paths.log_dir.parts


def test_ensure_private_dir_restricts_directory_permissions(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not stable on Windows")
    path = tmp_path / "runtime"

    ensure_private_dir(path)

    assert path.stat().st_mode & 0o777 == 0o700


def test_service_paths_ensure_restricts_state_directories(
    service_paths: ServicePaths,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not stable on Windows")

    assert service_paths.runtime_dir.stat().st_mode & 0o777 == 0o700
    assert service_paths.log_dir.stat().st_mode & 0o777 == 0o700


def test_broker_runtime_file_names(service_paths: ServicePaths) -> None:
    assert service_paths.pid_file.name == "broker.pid"
    assert service_paths.lock_file.name == "broker.lock"
    assert service_paths.state_lock_file.name == "state.lock"
    assert service_paths.broker_log_file.name == "broker.log"


def test_atomic_write_helpers_restrict_file_permissions(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not stable on Windows")
    data_file = tmp_path / "runtime" / "state.json"
    text_file = tmp_path / "runtime" / "broker.pid"

    atomic_write_json(data_file, {"enabled": ["package-cache"]})
    atomic_write_text(text_file, "123\n")

    assert json.loads(data_file.read_text(encoding="utf-8")) == {
        "enabled": ["package-cache"]
    }
    assert text_file.read_text(encoding="utf-8") == "123\n"
    assert data_file.stat().st_mode & 0o777 == 0o600
    assert text_file.stat().st_mode & 0o777 == 0o600


def test_file_lock_restricts_lock_file_permissions(tmp_path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not stable on Windows")
    lock_file = tmp_path / "runtime" / "state.lock"

    with file_lock(lock_file):
        assert lock_file.exists()

    assert lock_file.stat().st_mode & 0o777 == 0o600


def test_enabled_services_round_trip(service_paths: ServicePaths) -> None:
    state = StateStore(service_paths)

    assert state.set_enabled(["package-cache"], True) == {"package-cache"}
    assert state.enabled_services() == {"package-cache"}
    assert state.set_enabled(["package-cache"], False) == set()
    assert state.enabled_services() == set()


def test_events_round_trip(service_paths: ServicePaths) -> None:
    state = StateStore(service_paths)

    event = state.emit("plugin.event", service="package-cache", message="hello")

    events = state.read_events(limit=1)
    assert events == [event.to_dict()]


def test_events_rotate_and_read_previous_file(service_paths: ServicePaths) -> None:
    state = StateStore(service_paths, max_event_bytes=1)

    first = state.emit("plugin.first", service="package-cache")
    second = state.emit("plugin.second", service="package-cache")

    assert service_paths.events_file.with_name("events.jsonl.1").exists()
    assert state.read_events() == [first.to_dict(), second.to_dict()]
    assert state.read_events(limit=1) == [second.to_dict()]


def test_events_restrict_active_and_rotated_file_permissions(
    service_paths: ServicePaths,
) -> None:
    if os.name == "nt":
        pytest.skip("POSIX permission bits are not stable on Windows")
    state = StateStore(service_paths, max_event_bytes=1)

    state.emit("plugin.first", service="package-cache")
    state.emit("plugin.second", service="package-cache")

    assert service_paths.events_file.stat().st_mode & 0o777 == 0o600
    assert (
        service_paths.events_file.with_name("events.jsonl.1").stat().st_mode & 0o777
        == 0o600
    )


def test_non_positive_event_limit_returns_no_events(
    service_paths: ServicePaths,
) -> None:
    state = StateStore(service_paths)
    state.emit("plugin.event", service="package-cache")

    assert state.read_events(limit=0) == []
    assert state.read_events(limit=-1) == []


def test_log_lines(service_paths: ServicePaths) -> None:
    logs = LogManager(service_paths)
    with logs.open_for_service("package-cache") as stream:
        stream.write("one\n")
        stream.write("two\n")

    assert logs.read_lines("package-cache", lines=1) == ["two"]


def test_log_rotation_reads_previous_file(service_paths: ServicePaths) -> None:
    logs = LogManager(service_paths, max_bytes=1)
    with logs.open_for_service("package-cache") as stream:
        stream.write("one\n")
    with logs.open_for_service("package-cache") as stream:
        stream.write("two\n")

    assert logs.read_lines("package-cache", lines=5, include_previous=True) == [
        "one",
        "two",
    ]


def test_log_follow_reopens_after_rotation(
    service_paths: ServicePaths,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if os.name == "nt":
        pytest.skip("Windows does not allow replacing a log file held open")
    logs = LogManager(service_paths)
    path = logs.path_for("package-cache")
    with logs.open_for_service("package-cache") as stream:
        stream.write("old\n")
    follower = logs.follow("package-cache")
    calls = {"count": 0}

    def rotate_once(_seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] > 1:
            raise AssertionError("log follower did not reopen the active file")
        path.replace(path.with_name(f"{path.name}.1"))
        path.write_text("new\n", encoding="utf-8")

    monkeypatch.setattr(logs_module.time, "sleep", rotate_once)
    try:
        assert next(follower) == "new"
    finally:
        follower.close()


def test_non_positive_log_line_count_returns_no_lines(
    service_paths: ServicePaths,
) -> None:
    logs = LogManager(service_paths)
    with logs.open_for_service("package-cache") as stream:
        stream.write("one\n")

    assert logs.read_lines("package-cache", lines=0) == []
    assert logs.read_lines("package-cache", lines=-1) == []
