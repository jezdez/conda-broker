# Plugin Discovery

`conda-broker` owns its provider API. Providers register under the
`conda_broker` entry point group, not under conda's hook namespace.

```toml
[project.entry-points.conda_broker]
"my-provider" = "my_provider.broker"
```

`ServiceRegistry` subclasses `pluggy.PluginManager`. It installs the broker
hookspecs, loads provider entry points, calls `conda_broker_services()`, and
stores validated `CondaService` objects keyed by service name.

That shape keeps the pluggy mechanics available where they are useful while
also giving the rest of the broker a direct service catalog:

```python
registry.names()
registry.get("package-cache")
registry.enabled_defaults()
```

Providers are called independently. A provider that fails to import, raises
from its hook, returns invalid objects, or conflicts with an earlier service
does not prevent healthy providers from loading. Services with missing or
cyclic dependencies are removed from the usable registry. Details remain
visible through `provider_errors` in `cb list --json` and `cb doctor`.

Provider order is deterministic by entry-point name. The first provider for
a service name wins; the conflicting provider is quarantined so users can
address the surviving service predictably.
