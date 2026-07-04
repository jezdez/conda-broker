# Create a Presto-Style Solver Service

Solver services are a natural broker use case: the initial process startup
can be expensive, but repeated solves can reuse warmed caches and in-memory
state.

## Service Spec

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="presto",
        summary="Local long-running conda solver API",
        source="conda-presto",
        start_policy="manual",
        restart_policy="on-failure",
        endpoints=(
            EndpointSpec(
                protocol="http",
                path="/health",
                port_env="CONDA_PRESTO_PORT",
            ),
        ),
        health_check=HealthCheck(
            type="http",
            endpoint="default",
            interval_s=10,
            timeout_s=2,
        ),
        process=ProcessSpec(
            argv=("conda", "presto", "--serve", "--host", "127.0.0.1"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=15,
        ),
    )
```

## User Workflow

```bash
cb enable presto
cb start presto
cb wait presto
cb status presto
cb endpoint presto
```

If a conda plugin wants to use the service opportunistically, it should use
the client API:

```python
from conda_broker.client import get_service_endpoint, is_service_ready

if is_service_ready("presto"):
    endpoint = get_service_endpoint("presto")
    use_presto_api(endpoint["url"])
else:
    run_regular_solver()
```

This preserves user control: conda commands can benefit from a running
service but do not silently launch one.
