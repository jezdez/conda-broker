# Manage Services

## List Services

```bash
cb list
cb list --json
```

Discovered services are visible even when the broker is not running.

## Enable or Disable Autostart

```bash
cb enable package-cache
cb disable package-cache
```

`enable` and `disable` validate names against discovered services. If a
provider package is removed later, its stale enabled entry is ignored during
broker startup instead of preventing other services from starting.

Use `--start` or `--stop` to combine the state change with process action:

```bash
cb enable package-cache --start
cb disable package-cache --stop
```

## Start and Stop

```bash
cb start
cb start package-cache
cb stop package-cache
cb stop
```

`cb start` starts the broker and services enabled for broker startup.
`cb start SERVICE` starts selected services explicitly. `cb stop` without
names shuts the broker down.

For Python scripts that need temporary lifecycle ownership, use the `Broker`
API context managers:

```python
from conda_broker import Broker

with Broker.current().started() as broker:
    broker.service("package-cache").start()
```

```python
from conda_broker import Broker

with Broker.current().service("package-cache").started(wait=True) as service:
    endpoint = service.endpoint(ready=True)
```

Context managers leave pre-existing brokers and services running. They stop
only the broker or service they started on entry.

## Wait for Readiness

```bash
cb wait package-cache --timeout 15
cb wait package-cache --start --timeout 15
```

`cb wait` exits successfully only when the service reports `ready=true`.
Use `--start` when startup itself should be part of the user-visible action.

## Show Endpoints

```bash
cb endpoint package-cache
cb endpoint package-cache default --json
```

Endpoint output shows the resolved URL for services that declare local TCP or
HTTP endpoints.

## Restart

```bash
cb restart package-cache
cb restart
```

Restarting a named service keeps the broker running. Restarting without
names stops and starts the broker process.
