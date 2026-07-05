"""Tests for path, state, and log helpers."""

from __future__ import annotations

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


def test_broker_runtime_file_names(service_paths: ServicePaths) -> None:
    assert service_paths.pid_file.name == "broker.pid"
    assert service_paths.lock_file.name == "broker.lock"
    assert service_paths.state_lock_file.name == "state.lock"
    assert service_paths.broker_log_file.name == "broker.log"


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


def test_non_positive_log_line_count_returns_no_lines(
    service_paths: ServicePaths,
) -> None:
    logs = LogManager(service_paths)
    with logs.open_for_service("package-cache") as stream:
        stream.write("one\n")

    assert logs.read_lines("package-cache", lines=0) == []
    assert logs.read_lines("package-cache", lines=-1) == []
