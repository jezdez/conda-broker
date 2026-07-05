# Plugin Command API

`BrokerServiceCommands` helps conda plugins expose plugin-owned broker
commands such as `conda my-plugin start`, `conda my-plugin stop`, and
`conda my-plugin status`.

The helper is intentionally scoped: plugin authors pass the broker service
names that belong to their plugin, and generated positional service arguments
are restricted to that set.

```python
from conda_broker.plugin_commands import BrokerServiceCommands

broker_commands = BrokerServiceCommands(("conda-my-plugin.helper",))
```

```{eval-rst}
.. automodule:: conda_broker.plugin_commands
   :members:
```
