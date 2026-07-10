# Query Status from Plugins

Other conda plugins can use `Broker` to make runtime decisions. Query
methods do not start the broker.

```python
from conda_broker import Broker

service = Broker.current().service("package-cache")
check = service.check()

if check.ready:
    query_local_metadata()
else:
    query_repodata_directly()

status = check.status
```

`Service.check()` returns a compact report for plugin CLIs and JSON output.
When the broker is running, it distinguishes a known stopped service from an
unknown service:

```python
check = Broker.current().service("package-cache").check()

if check.available:
    print(check.to_dict())
else:
    use_inline_fallback(reason=check.reason)
```

When the broker is stopped, `check()` returns
`reason="broker-unavailable"` without loading provider entry points. That
keeps hot-path conda hooks cheap even when many providers are installed.

`Service.status()` returns `None` when the service or broker is unavailable,
so optional integrations can safely fall back. Use
`Broker.current().status("service-name")` when you explicitly want provider
discovery and a strict query that errors for unknown services.

For services that expose a local API, check readiness and read the endpoint:

```python
from conda_broker import Broker

service = Broker.current().service("package-cache")

if endpoint := service.endpoint(ready=True):
    query_local_metadata(endpoint.url)
else:
    query_repodata_directly()
```

`Service.endpoint(ready=True)` never starts the broker. It returns `None`
unless the service is already ready and the endpoint has a resolved URL.

Only explicit startup calls can start the broker:

```python
from conda_broker import Broker

broker = Broker.current()
broker.start()
broker.service("package-cache").start()
broker.service("package-cache").wait(start=True)
```

For scripts that need a temporary service and want automatic cleanup, use a
context manager:

```python
from conda_broker import Broker

with Broker.current().service("package-cache").started(wait=True) as service:
    if endpoint := service.endpoint(ready=True):
        query_local_metadata(endpoint.url)
```

The context manager stops the service on exit only when it started the
service on entry. If it had to start the broker too, it stops that broker on
exit as well. With `wait=True`, failure to reach readiness raises
`ServiceNotReadyError` after cleanup.

Use startup calls in user-visible commands, not in hooks that run for every
conda invocation.
