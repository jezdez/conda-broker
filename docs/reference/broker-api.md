# Broker API

The `Broker` API is for provider plugins and user-facing commands that need
to inspect or manage broker state.

These methods do not start the broker:

- `Broker.current()`
- `Broker.running()`
- `Broker.status()`
- `Broker.service(NAME).check()`
- `Broker.service(NAME).status()`
- `Broker.service(NAME).running()`
- `Broker.service(NAME).ready()`
- `Broker.service(NAME).endpoint(ready=True)`
- `Broker.events()`
- `Broker.emit_event()`

Startup methods are explicit:

- `Broker.start()`
- `Broker.start_services()`
- `Broker.service(NAME).start()`
- `Broker.service(NAME).wait(start=True)`
- `Broker.restart()`
- `Broker.service(NAME).restart()`

`Broker.start()` starts the broker process and any services enabled for
broker startup. `Broker.start_services()` and `Broker.service(NAME).start()`
start named services explicitly. `Broker.start_services()` and
`Broker.restart_services()` require at least one service name; they never
interpret an empty list as "all services."

A multi-service start preflights service names, dependencies, and runtime
availability. If a later process launch still fails, the supervisor stops
processes and dependencies newly launched by that call while leaving
pre-existing services alone.

`Broker.service(NAME).wait(start=False)` waits on an already running broker
and does not start a process by itself.

Context managers are explicit lifecycle helpers:

```python
from conda_broker import Broker

with Broker.current().started() as broker:
    print(broker.status().to_dict())
```

```python
from conda_broker import Broker

with Broker.current().service("package-cache").started(wait=True) as service:
    endpoint = service.endpoint(ready=True)
```

`started()` context managers clean up only what they started. If the broker
or service was already running before entering the `with` block, it is left
running on exit. `service.started(wait=True)` raises
`ServiceNotReadyError` if readiness is not reached, then cleans up anything
the context started.

Plugin status commands can render a compact service report without starting
anything:

```python
from conda_broker import Broker

check = Broker.current().service("package-cache").check()
print(check.to_dict())
```

Service-handle queries take a fast path when the broker is stopped: they do
not import provider entry points just to answer a runtime question.
`Service.check()` then reports `reason="broker-unavailable"`, while
`Service.status()`, `running()`, `ready()`, and `endpoint()` return an absent
or false result. `Broker.status()` is the strict, discovery-aware query.

`Broker.emit_event()` and `Service.emit_event()` return a typed
`ServiceEvent`. They append directly to local state when no broker is
running and retry that local path if the broker disappears during IPC.

For plugin-owned `conda my-plugin services start|stop|status` commands, use the
[Plugin Command API](plugin-command-api.md).

```{eval-rst}
.. automodule:: conda_broker.api
   :members:
```
