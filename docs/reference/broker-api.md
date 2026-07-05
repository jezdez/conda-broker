# Broker API

The `Broker` API is for provider plugins and user-facing commands that need
to inspect or manage broker state.

Query methods do not start the broker:

- `Broker.current()`
- `Broker.running()`
- `Broker.status()`
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

`Broker.service(NAME).wait(start=False)` waits on an already running broker
and does not start a process by itself.

```{eval-rst}
.. automodule:: conda_broker.api
   :members:
```
