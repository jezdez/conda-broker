# Query Status from Plugins

Other conda plugins can use `Broker` to make runtime decisions. Query
methods do not start the broker.

```python
from conda_broker import Broker

service = Broker.current().service("package-cache")

if service.running():
    query_local_metadata()
else:
    query_repodata_directly()

status = service.status()
```

`Service.status()` returns `None` when the named service is not discovered,
so optional integrations can safely fall back. Use
`Broker.current().status("service-name")` when you want a strict state query
that errors for unknown services.

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

Use startup calls in user-visible commands, not in hooks that run for every
conda invocation.
