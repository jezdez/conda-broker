# Events

Events are append-only JSON Lines records with these fields:

- `timestamp`: UTC ISO timestamp
- `type`: event type
- `service`: optional service name
- `message`: optional human-readable message
- `data`: event-specific object

## Broker Events

- `broker.started`: broker process is accepting IPC. `data.pid` and
  `data.port` identify the local broker instance; `data.instance_id` prevents
  stale-instance confusion.
- `broker.stopped`: broker process shut down. `data.pid` identifies the
  stopped instance.
- `broker.monitor_error`: one monitor pass raised unexpectedly; the monitor
  remains alive for later passes.
- `provider.failed`: provider import, hook, service, or dependency validation
  failed. Error details are in `data`.

## Service Events

- `service.started`: process launched. `data.pid` is the child PID,
  `data.restart_count` is the restart generation, and `data.endpoints`
  contains resolved endpoint metadata for declared endpoints.
- `service.stopped`: user-requested stop completed.
- `service.stop_failed`: a user-requested stop could not terminate the process
  tree; other selected services are still stopped before the error is returned.
- `service.exited`: process exited without a user stop request.
  `data.exit_code` records the child return code.
- `service.restart_scheduled`: restart backoff was scheduled. `data.delay_s`
  is the wait time and `data.reason` is `exit` or `health`.
- `service.start_failed`: an automatic relaunch or enabled-service autostart
  failed. Relaunch failures are rescheduled; one failed autostart does not
  prevent other enabled services or the broker from starting.
- `service.healthy`: health transitioned into the healthy state.
- `service.unhealthy`: health transitioned into the unhealthy state.
- `service.orphan_reaped`: a successor broker terminated a process recorded by
  an earlier broker instance.
- `service.enabled`: user enabled the service for broker startup.
- `service.disabled`: user disabled the service for broker startup.

## Provider Events

Providers can emit any namespaced event type:

```python
from conda_broker import Broker

Broker.current().service("package-cache").emit_event(
    "package_cache.warmed",
    message="repodata cache is ready",
    data={"records": 425000},
)
```

Health events are transition events, not one event per polling interval.
Provider events are written locally when the broker is stopped; emitting an
event never starts it.
