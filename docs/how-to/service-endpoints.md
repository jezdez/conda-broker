# Expose Service Endpoints

Endpoint declarations tell users and other plugins how to talk to a running
service. They also give the broker a concrete readiness contract: the process
is not merely alive, it has become usable.

## Declare an Endpoint

Use `EndpointSpec` on the service:

```python
import sys

from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec

CondaService(
    name="my-provider.api",
    summary="Local API used by conda-my-provider",
    source="conda-my-provider",
    endpoints=(
        EndpointSpec(
            protocol="http",
            host="127.0.0.1",
            path="/health",
            port_env="PORT",
            url_env="SERVICE_URL",
        ),
    ),
    health_check=HealthCheck(type="http", endpoint="default"),
    process=ProcessSpec(
        argv=(sys.executable, "-m", "conda_my_provider.server"),
        env={"PYTHONUNBUFFERED": "1"},
    ),
)
```

When `port` is omitted, the broker allocates a free local port when the
service starts. It injects that port into the child process before launch.

## Read Endpoint Environment Variables

Every endpoint receives automatic environment variables:

- `CONDA_BROKER_SERVICE_NAME`
- `CONDA_BROKER_ENDPOINT_DEFAULT_PROTOCOL`
- `CONDA_BROKER_ENDPOINT_DEFAULT_HOST`
- `CONDA_BROKER_ENDPOINT_DEFAULT_PORT`
- `CONDA_BROKER_ENDPOINT_DEFAULT_URL`

For non-default endpoint names, the endpoint name is uppercased and
non-alphanumeric characters become underscores. Names that collide after
normalization are rejected, as are duplicate custom variable names or custom
names that overwrite broker variables.

If `port_env` or `url_env` is configured, the broker also sets those custom
variables. The example above sets `PORT` and `SERVICE_URL`.

IPv6 endpoint URLs use bracketed hosts, for example
`http://[::1]:8765/health`.

## Bind Health Checks to Endpoints

Endpoint-bound health checks avoid duplicating host and port values:

```python
HealthCheck(type="http", endpoint="default", interval_s=2, timeout_s=1)
HealthCheck(type="tcp", endpoint="control", interval_s=2, timeout_s=1)
```

Failed health checks remain `unknown` during `start_period_s`, which defaults
to five seconds. That gives a process time to bind a dynamically assigned port
before failed probes become restart triggers.

Use `start_period_s=0` for services where an immediate failed health check
should restart the process.

## Wait for Readiness

`cb start` starts processes; it is not a readiness gate. Use `cb wait` when a
script needs the service to be usable:

```bash
cb start my-provider.api
cb wait my-provider.api --timeout 15
```

To combine explicit startup and readiness waiting:

```bash
cb wait my-provider.api --start --timeout 15
```

`cb wait` exits with status code zero when the service reports
`ready=true`. It exits non-zero if the service stops, fails, or never becomes
ready before the timeout.

## Inspect Endpoints

Use `cb endpoint` to see the resolved endpoint:

```bash
cb endpoint my-provider.api
cb endpoint my-provider.api default --json
```

Stopped services with static ports can still show endpoint URLs. Stopped
services with broker-allocated ports show unresolved endpoint fields until
the service starts.

For one launch, the broker holds socket reservations while allocating all
dynamic endpoints, which prevents two endpoints from receiving the same
port. It must release those sockets before the child can bind. Another process
can still claim a port in that short interval, so services should exit on bind
failure and let restart policy retry with a new allocation.

## Query from Another Plugin

Runtime decisions should use query helpers. They do not start the broker.

```python
from conda_broker import Broker

service = Broker.current().service("my-provider.api")

if endpoint := service.endpoint(ready=True):
    use_api(endpoint.url)
else:
    use_inline_fallback()
```

Use `service.wait(start=True)` only from user-visible commands where
starting the broker and service is an explicit action.
