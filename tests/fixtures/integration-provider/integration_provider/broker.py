"""Broker service declared by the integration-test provider."""

from __future__ import annotations

import sys

from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="integration-heartbeat",
        summary="Integration-test heartbeat",
        source="integration-provider",
        process=ProcessSpec(
            argv=(sys.executable, "-m", "integration_provider.service"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=1,
        ),
        health_check=HealthCheck(interval_s=0.05, start_period_s=0),
    )
