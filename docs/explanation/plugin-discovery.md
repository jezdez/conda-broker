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

Duplicate names are rejected so users can address services predictably.
