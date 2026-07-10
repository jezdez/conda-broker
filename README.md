# conda-broker

`conda-broker` is a conda plugin that supervises user-visible,
opt-in long-running services for conda-adjacent workflows.

It provides:

- `conda broker` and `cb` CLI entry points
- a local user-scoped broker process
- process supervision with restart policies, health checks, logs, and events
- a private pluggy broker-provider API owned by this package
- a lightweight `Broker` API for other plugins to check service state without
  starting the broker

## Install

Add `conda-broker` as a PyPI dependency with Pixi:

```bash
pixi add --pypi conda-broker
pixi run cb --help
```

Or, in a conda installation, use `conda-pypi` from the base environment:

```bash
conda activate base
conda install conda-pypi
conda pypi install conda-broker
conda broker --help
```

See the [documentation](https://jezdez.github.io/conda-broker/) for a
quickstart, tutorials, task-focused guides, API and CLI reference, and
architecture explanations.

## Provider API

Broker providers expose services through the `conda_broker` pluggy project,
not through conda's own hook API:

```python
import sys

from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="package-cache",
        summary="Local conda package metadata cache",
        source="conda-package-cache",
        process=ProcessSpec(
            argv=(sys.executable, "-m", "conda_package_cache", "--serve")
        ),
    )
```

Register the provider module under:

```toml
[project.entry-points.conda_broker]
"my-provider" = "my_provider.broker"
```

Plugins can make runtime decisions without starting the broker:

```python
from conda_broker import Broker

if endpoint := Broker.current().service("package-cache").endpoint(ready=True):
    use_package_cache(endpoint.url)
```

## Development

```bash
pixi install
pixi run cb status
pixi run -e test test
pixi run -e dev check
pixi run -e dev demo-check
pixi run -e docs docs
```
