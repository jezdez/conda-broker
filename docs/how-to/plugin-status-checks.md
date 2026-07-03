# Query Status from Plugins

Other conda plugins can use `conda_broker.client` to make runtime decisions.
Query helpers do not start the broker.

```python
from conda_broker.client import broker_running, is_service_running, service_status

if broker_running() and is_service_running("presto"):
    use_presto()
else:
    use_inline_solver()

status = service_status("presto")
```

Only explicit startup calls can start the broker:

```python
from conda_broker.client import start, start_broker

start_broker()
start(("presto",))
```

Use startup calls in user-visible commands, not in hooks that run for every
conda invocation.
