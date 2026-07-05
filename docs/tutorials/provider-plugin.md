# Build a Provider Plugin

A provider plugin is any installed Python package that publishes
`conda_broker_services()` under the `conda_broker` entry point group.

![provider plugin demo](../../demos/provider-plugin.gif)

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
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="my-provider.api",
        summary="Local API used by conda-my-provider",
        source="conda-my-provider",
        start_policy="manual",
        restart_policy="on-failure",
        endpoints=(
            EndpointSpec(
                protocol="http",
                path="/health",
                port_env="PORT",
                url_env="SERVICE_URL",
            ),
        ),
        health_check=HealthCheck(type="http", endpoint="default"),
        process=ProcessSpec(
            argv=("python", "-m", "conda_my_provider.server"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=10,
        ),
    )
```

## Query Status from the Provider

Provider code can decide whether to use the long-running path:

```python
from conda_broker import Broker


def solve(request):
    service = Broker.current().service("my-provider.api")
    check = service.check()
    if check.ready and check.endpoint and check.endpoint.url:
        return solve_with_local_api(request, check.endpoint.url)
    log_fallback(check.reason)
    return solve_inline(request)
```

Readiness and endpoint queries never start the broker. Use
`Broker.start()`, `service.start()`, or `service.wait(start=True)` only for
explicit user-driven startup.

## Validate the Provider Service

Run the conformance harness before relying on the service from another
plugin:

```bash
cb dev validate my-provider.api
cb dev test my-provider.api --scenario health
cb dev test my-provider.api --scenario crash
```

Use `cb dev report my-provider.api --json` in CI to catch missing
commands, unhealthy services, broken stop behavior, and restart-policy
regressions.
