# conda-broker

`conda-broker` is a conda plugin that supervises user-visible,
opt-in long-running services for conda-adjacent workflows.

It provides:

- `conda broker` and `cb` CLI entry points
- a local user-scoped broker process
- process supervision with restart policies, health checks, logs, and events
- a private pluggy broker-provider API owned by this package
- a lightweight client API for other plugins to check service state without
  starting the broker

## Provider API

Broker providers expose specs through the `conda_broker` pluggy project,
not through conda's own hook API:

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="package-cache",
        summary="Local conda package metadata cache",
        source="conda-package-cache",
        process=ProcessSpec(argv=("python", "-m", "conda_package_cache", "--serve")),
    )
```

Register the provider module under:

```toml
[project.entry-points.conda_broker]
"my-provider" = "my_provider.broker"
```

Plugins can make runtime decisions without starting the broker:

```python
from conda_broker.client import is_service_running

if is_service_running("package-cache"):
    ...
```

## Development

```bash
pixi install
pixi run cb status
pixi run -e test pytest
pixi run ruff check
pixi run ruff format --check
pixi run ty check
```
