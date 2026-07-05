# Query Status from Plugins

Other conda plugins can use `conda_broker.client` to make runtime decisions.
Query helpers do not start the broker.

```python
from conda_broker.client import broker_running, is_service_running, service_status

if broker_running() and is_service_running("package-cache"):
    query_local_metadata()
else:
    query_repodata_directly()

status = service_status("package-cache")
```

`is_service_running()` returns `False` when the named service is not
discovered, so optional integrations can safely fall back. Use
`status("service-name")` when you want a strict state query that errors for
unknown services.

For services that expose a local API, check readiness and read the endpoint:

```python
from conda_broker.client import get_service_endpoint, is_service_ready

if is_service_ready("package-cache"):
    endpoint = get_service_endpoint("package-cache")
    query_local_metadata(endpoint["url"])
else:
    query_repodata_directly()
```

`is_service_ready()` and `get_service_endpoint()` are query helpers. They
never start the broker.

Only explicit startup calls can start the broker:

```python
from conda_broker.client import start, start_broker, wait

start_broker()
start(("package-cache",))
wait("package-cache", start_service=True)
```

Use startup calls in user-visible commands, not in hooks that run for every
conda invocation.
