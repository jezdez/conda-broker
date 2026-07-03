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
- `http`: broker can fetch `url`; status codes below 500 are healthy.
- `exec`: command exits with status code zero before `timeout_s`.

Each check runs every `interval_s` seconds while the service is running.
Failed checks are restart triggers for services with `restart_policy` set to
`on-failure` or `always`.

## Registry

```{eval-rst}
.. automodule:: conda_broker.registry
   :members:
```
