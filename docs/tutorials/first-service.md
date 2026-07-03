# Register Your First Service

This tutorial creates a tiny provider module that exposes a long-running
Python process.

## Create the Provider Module

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="hello",
        summary="Example service that prints a heartbeat",
        source="example-provider",
        process=ProcessSpec(
            argv=(
                "python",
                "-c",
                "import time; print('ready', flush=True); time.sleep(3600)",
            ),
        ),
    )
```

The hook belongs to `conda-broker`, not conda. It is loaded by the
broker's own `ServiceRegistry`, which is also the pluggy manager.

## Register the Entry Point

```toml
[project.entry-points.conda_broker]
"example-provider" = "example_provider.broker"
```

After installation, the service appears in `cb list`.

## Start It

```bash
cb enable hello --start
cb status hello
cb logs hello
```

The process runs in its own session or process group where the operating
system supports it. `cb stop hello` sends the configured graceful stop
signal, waits for the grace period, and kills the process if needed.
