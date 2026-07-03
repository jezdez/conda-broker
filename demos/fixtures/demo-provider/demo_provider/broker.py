"""Demo service specs for conda-broker."""

from __future__ import annotations

import sys

from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="heartbeat",
        summary="Demo service that writes heartbeat logs",
        source="demo-provider",
        process=ProcessSpec(
            argv=(sys.executable, "-m", "demo_provider.heartbeat"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=2,
        ),
        health_check=HealthCheck(type="process", interval_s=2),
    )
    yield CondaService(
        name="flaky",
        summary="Demo service that exits once, then stays up",
        source="demo-provider",
        restart_policy="on-failure",
        process=ProcessSpec(
            argv=(sys.executable, "-m", "demo_provider.flaky"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=2,
        ),
        health_check=HealthCheck(type="process", interval_s=2),
    )
