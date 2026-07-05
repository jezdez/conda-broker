# Events

Events are append-only JSON Lines records with these fields:

- `timestamp`: UTC ISO timestamp
- `type`: event type
- `service`: optional service name
- `message`: optional human-readable message
- `data`: event-specific object

## Broker Events

- `broker.started`: broker process is accepting IPC. `data.pid` and
  `data.port` identify the local broker instance.
- `broker.stopped`: broker process shut down. `data.pid` identifies the
  stopped instance.

## Service Events

- `service.started`: process launched. `data.pid` is the child PID,
  `data.restart_count` is the restart generation, and `data.endpoints`
  contains resolved endpoint metadata for declared endpoints.
- `service.stopped`: user-requested stop completed.
- `service.exited`: process exited without a user stop request.
  `data.exit_code` records the child return code.
- `service.restart_scheduled`: restart backoff was scheduled. `data.delay_s`
  is the wait time and `data.reason` is `exit` or `health`.
- `service.unhealthy`: a health check failed.
- `service.enabled`: user enabled the service for broker startup.
- `service.disabled`: user disabled the service for broker startup.

## Provider Events

Providers can emit any namespaced event type:

```python
emit_event(
    "package_cache.warmed",
    service="package-cache",
    message="repodata cache is ready",
    data={"records": 425000},
)
```
