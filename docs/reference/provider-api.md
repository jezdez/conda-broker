# Provider API

Provider plugins implement `conda_broker_services()` and return
`CondaService` objects. `ServiceRegistry` is a pluggy manager and the
validated service catalog.

## Hookspec

```{eval-rst}
.. automodule:: conda_broker.hookspec
   :members:
```

## Models

```{eval-rst}
.. automodule:: conda_broker.models
   :members:
```

### Health Checks

`HealthCheck` supports four `type` values:

- `process`: child process is still alive.
- `tcp`: broker can open a TCP connection to `host` and `port`.
- `http`: broker can fetch `url`; status codes from 200 through 399 are
  healthy.
- `exec`: command exits with status code zero before `timeout_s`.

Each check runs every `interval_s` seconds while the service is running.
Failed checks during `start_period_s` keep the service in the `starting`
state. After that startup period, failed checks are restart triggers for
services with `restart_policy` set to `on-failure` or `always`.

TCP and HTTP health checks can reference a declared endpoint instead of
duplicating host and port values:

```python
HealthCheck(type="http", endpoint="default")
```

### Endpoints

`EndpointSpec` describes a local TCP or HTTP endpoint exposed by a service.
Static ports are allowed, but omitting `port` lets the broker allocate a free
local port at process start.

The supervisor injects automatic endpoint variables into the process
environment:

- `CONDA_BROKER_SERVICE_NAME`
- `CONDA_BROKER_ENDPOINT_<NAME>_PROTOCOL`
- `CONDA_BROKER_ENDPOINT_<NAME>_HOST`
- `CONDA_BROKER_ENDPOINT_<NAME>_PORT`
- `CONDA_BROKER_ENDPOINT_<NAME>_URL`

`port_env` and `url_env` add provider-chosen variable names for services that
already expect simple variables such as `PORT`.

Endpoint names must remain unique after conversion to their uppercase
environment-variable form. Custom endpoint variable names must also be
portable, unique, and distinct from broker-owned names.

### Runtimes and Processes

Runtime names are open identifiers so future provider models remain
discoverable. The installed broker currently activates only
`runtime="process"`; starting any other runtime raises
`RuntimeUnavailableError`.

Process services validate their argv, environment names and values, stop
signal, and grace period when providers are collected. Exec health checks use
the same merged environment and working directory as the service, plus
resolved endpoint variables.

## Registry

```{eval-rst}
.. automodule:: conda_broker.registry
   :members:
```
