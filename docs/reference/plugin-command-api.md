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

Use `configure_parser()` when the plugin command is entirely broker service
management. Use `add_to_subparsers()` to mix broker controls directly into an
existing subcommand tree. Use `add_group_to_subparsers()` when the plugin
already owns names such as `status` or `start`, producing commands like
`conda my-plugin services status`.

```{eval-rst}
.. automodule:: conda_broker.plugin_commands
   :members:
```
