# Client API

The client API is for provider plugins and user-facing commands that need
to inspect or manage broker state.

Query helpers do not start the broker:

- `broker_running()`
- `status()`
- `service_status()`
- `is_service_running()`
- `is_service_ready()`
- `get_service_endpoint()`
- `list_services()`
- `events()`
- `emit_event()`

Startup helpers are explicit:

- `start_broker()`
- `start()`
- `wait(..., start_service=True)`
- `restart()`

`wait(..., start_service=False)` waits on an already running broker and does
not start a process by itself.

```{eval-rst}
.. automodule:: conda_broker.client
   :members:
```
