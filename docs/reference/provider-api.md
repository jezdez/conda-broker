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

## Registry

```{eval-rst}
.. automodule:: conda_broker.registry
   :members:
```
