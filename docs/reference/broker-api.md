# Broker API

The `Broker` API is for provider plugins and user-facing commands that need
to inspect or manage broker state.

Query methods do not start the broker:

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
running on exit.

Plugin status commands can render a compact service report without starting
anything:

```python
from conda_broker import Broker

check = Broker.current().service("package-cache").check()
print(check.to_dict())
```

For plugin-owned `conda my-plugin services start|stop|status` commands, use the
[Plugin Command API](plugin-command-api.md).

```{eval-rst}
.. automodule:: conda_broker.api
   :members:
```
