"""Tests for provider conformance helpers."""

from __future__ import annotations

import sys

from conda_broker import conformance
from conda_broker.models import CondaService, HealthCheck, ProcessSpec
from conda_broker.registry import ServiceRegistry


def _sleeping_service(name: str, *, restart_policy: str = "on-failure") -> CondaService:
    return CondaService(
        name=name,
        summary=f"{name} service",
        source="tests",
        restart_policy=restart_policy,
        process=ProcessSpec(
            argv=(
                sys.executable,
                "-c",
                "import time; print('ready', flush=True); time.sleep(30)",
            ),
            grace_period_s=1,
        ),
        health_check=HealthCheck(type="process", interval_s=0.01),
    )


def test_validate_service_spec_passes() -> None:
    service = _sleeping_service("sleeper")
    registry = ServiceRegistry([service])

    result = conformance.validate("sleeper", registry=registry)

    assert result.ok is True
    assert {check.name for check in result.checks} >= {
        "service.discovered",
        "runtime.process",
        "process.argv",
        "health.type",
    }


def test_run_service_start_stop_captures_logs() -> None:
    service = _sleeping_service("runner")
    registry = ServiceRegistry([service])

    result = conformance.run(
        "runner",
        registry=registry,
        duration_s=0.1,
        timeout_s=3,
    )

    assert result.ok is True
    assert "ready" in result.logs
    assert {event["type"] for event in result.events} >= {
        "service.started",
        "service.stopped",
    }


def test_run_service_reports_start_failure() -> None:
    service = CondaService(
        name="missing-command",
        summary="Missing command",
        source="tests",
        process=ProcessSpec(argv=("conda-broker-missing-command-for-tests",)),
    )
    registry = ServiceRegistry([service])

    result = conformance.run(
        "missing-command",
        registry=registry,
        duration_s=0.1,
        timeout_s=1,
    )

    assert result.ok is False
    assert any(
        check.name == "runtime.start" and check.status == "fail"
        for check in result.checks
    )


def test_health_scenario_observes_healthy_service() -> None:
    service = _sleeping_service("healthy")
    registry = ServiceRegistry([service])

    result = conformance.test(
        "healthy",
        registry=registry,
        scenario="health",
        timeout_s=3,
    )

    assert result.ok is True
    assert result.status is not None
    assert result.status["health"] == "healthy"


def test_crash_scenario_verifies_restart_policy() -> None:
    service = _sleeping_service("crashy")
    registry = ServiceRegistry([service])

    result = conformance.test(
        "crashy",
        registry=registry,
        scenario="crash",
        timeout_s=4,
    )

    assert result.ok is True
    assert result.status is not None
    assert result.status["running"] is True
    assert result.status["restart_count"] == 1
    assert any(event["type"] == "service.restart_scheduled" for event in result.events)


def test_report_runs_all_scenarios() -> None:
    service = _sleeping_service("reported")
    registry = ServiceRegistry([service])

    payload = conformance.report("reported", registry=registry, timeout_s=4)

    assert payload["ok"] is True
    assert [result["command"] for result in payload["results"]] == [
        "validate",
        "run",
        "test",
        "test",
    ]
