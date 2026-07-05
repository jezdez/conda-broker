# Plugin Command API

`BrokerServiceCommands` helps conda plugins expose plugin-owned broker
commands such as `conda my-plugin services start`,
`conda my-plugin services stop`, and `conda my-plugin services status`.

The helper is intentionally scoped: plugin authors pass the broker service
names that belong to their plugin, and generated positional service arguments
are restricted to that set.

```python
from conda_broker.plugin_commands import BrokerServiceCommands

broker_commands = BrokerServiceCommands(("conda-my-plugin.helper",))
```

Use `conda_subcommand()` when the plugin does not already have a conda
subcommand. Use `add_group_to_subparsers()` when the plugin has an existing
subcommand tree and needs a `services` subcommand inside it. Use
`configure_commands_parser()` when the plugin has already created a parser
that should contain direct broker service commands. `add_commands_to_subparsers()`
is a lower-level escape hatch for unusual argparse layouts.

```{eval-rst}
.. automodule:: conda_broker.plugin_commands
   :members:
```
