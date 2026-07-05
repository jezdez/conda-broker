# Create a Package Cache Service

Package metadata is a good broker example because a local cache can stay
warm between conda commands without making every command responsible for
starting or supervising a helper process.

## Service Spec

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="package-cache",
        summary="Local conda package metadata cache",
        source="conda-package-cache",
        start_policy="manual",
        restart_policy="on-failure",
        endpoints=(
            EndpointSpec(
                protocol="http",
                path="/health",
                port_env="CONDA_PACKAGE_CACHE_PORT",
            ),
        ),
        health_check=HealthCheck(
            type="http",
            endpoint="default",
            interval_s=10,
            timeout_s=2,
        ),
        process=ProcessSpec(
            argv=("python", "-m", "conda_package_cache", "--serve"),
            env={"PYTHONUNBUFFERED": "1"},
            grace_period_s=15,
        ),
    )
```

## User Workflow

```bash
cb enable package-cache
cb start package-cache
cb wait package-cache
cb status package-cache
cb endpoint package-cache
```

If a conda plugin wants to use the service opportunistically, it should use
the `Broker` API:

```python
from conda_broker import Broker

service = Broker.current().service("package-cache")

if endpoint := service.endpoint(ready=True):
    query_local_metadata(endpoint.url, "numpy")
else:
    query_repodata_directly("numpy")
```

This preserves user control: conda commands can benefit from a running
service but do not silently launch one.
