# Events

Events are append-only JSON Lines records with these fields:

- `timestamp`: UTC ISO timestamp
- `type`: event type
- `service`: optional service name
- `message`: optional human-readable message
- `data`: event-specific object

## Broker Events

- `broker.started`
- `broker.stopped`

## Service Events

- `service.started`
- `service.stopped`
- `service.exited`
- `service.restart_scheduled`
- `service.unhealthy`
- `service.enabled`
- `service.disabled`

## Provider Events

Providers can emit any namespaced event type:

```python
emit_event(
    "solver.cache_warmed",
    service="presto",
    message="repodata cache is ready",
    data={"records": 425000},
)
```
