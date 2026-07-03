# Create a Presto-Style Solver Service

Solver services are a natural broker use case: the initial process startup
can be expensive, but repeated solves can reuse warmed caches and in-memory
state.

## Service Spec

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="presto",
        summary="Local long-running conda solver API",
        source="conda-presto",
        start_policy="manual",
        restart_policy="on-failure",
        health_check=HealthCheck(
            type="http",
            url="http://127.0.0.1:17654/health",
            interval_s=10,
            timeout_s=2,
        ),
        process=ProcessSpec(
            argv=("conda", "presto", "--serve", "--host", "127.0.0.1", "--port", "17654"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=15,
        ),
    )
```

## User Workflow

```bash
cb enable presto
cb start presto
cb status presto
```

If a conda plugin wants to use the service opportunistically, it should use
the client API:

```python
from conda_broker.client import is_service_running

if is_service_running("presto"):
    use_presto_api()
else:
    run_regular_solver()
```

This preserves user control: conda commands can benefit from a running
service but do not silently launch one.
