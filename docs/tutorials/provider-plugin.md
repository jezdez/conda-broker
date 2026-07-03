# Build a Provider Plugin

A provider plugin is any installed Python package that publishes
`conda_broker_services()` under the `conda_broker` entry point group.

## Project Metadata

```toml
[project]
name = "conda-my-provider"
dependencies = ["conda-broker"]

[project.entry-points.conda_broker]
"conda-my-provider" = "conda_my_provider.broker"
```

## Service Definition

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="my-provider.api",
        summary="Local API used by conda-my-provider",
        source="conda-my-provider",
        start_policy="manual",
        restart_policy="on-failure",
        health_check=HealthCheck(type="tcp", host="127.0.0.1", port=8765),
        process=ProcessSpec(
            argv=("python", "-m", "conda_my_provider.server", "--port", "8765"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=10,
        ),
    )
```

## Query Status from the Provider

Provider code can decide whether to use the long-running path:

```python
from conda_broker.client import is_service_running


def solve(request):
    if is_service_running("my-provider.api"):
        return solve_with_local_api(request)
    return solve_inline(request)
```

Status helpers never start the broker. Use `start()` or `start_broker()`
only for explicit user-driven startup.
