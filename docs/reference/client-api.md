# Client API

The client API is for provider plugins and user-facing commands that need
to inspect or manage broker state.

Query helpers do not start the broker:

- `broker_running()`
- `status()`
- `service_status()`
- `is_service_running()`
- `list_services()`
- `events()`
- `emit_event()`

Startup helpers are explicit:

- `start_broker()`
- `start()`
- `restart()`

```{eval-rst}
.. automodule:: conda_broker.client
   :members:
```
