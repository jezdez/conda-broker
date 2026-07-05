# Integrate Conda Plugins

Use broker when a conda plugin benefits from preserving expensive runtime
state between commands. Keep ordinary validation, parsing, and one-shot
commands inline.

The [conda plugin docs](https://docs.conda.io/projects/conda/en/stable/dev-guide/plugins/index.html)
describe the host plugin system: packages register a module under
`[project.entry-points.conda]`, then expose hooks such as
`conda_subcommands()` and `conda_settings()`. The
[conda-plugins catalogue](https://github.com/conda-incubator/conda-plugins)
shows the common shapes: subcommands, solver hooks, pre/post command hooks,
health checks, package extractors, shell completion, and channel tooling.

## Choose the Integration Shape

Broker is a good fit when the plugin has one of these properties:

- It starts a local API server or subprocess from conda hooks.
- It repeatedly builds the same package, channel, solver, or metadata cache.
- It has a background watcher or indexer that users should be able to inspect.
- It needs a shared local endpoint that several CLI commands can reuse.

Broker is usually not worth it when the plugin is just a pure subcommand, a
small guardrail hook, or a fast formatter.

From the current catalogue, these are the useful patterns:

| Plugin shape | Catalogue examples | Broker opportunity |
| --- | --- | --- |
| Local server started by hooks | `conda-pypi-channel` | Replace ad hoc `Popen` lifecycle with a visible broker service, HTTP health check, logs, events, and a stable endpoint. |
| Metadata and conversion cache | `conda-pypi`, `conda-index`, `conda-subchannel` | Keep one-shot commands, but optionally reuse a warm local cache or index service when it is already ready. |
| Solver or repoquery backend | `conda-libmamba-solver`, `conda-rattler-solver` | Query a ready cache/helper service before rebuilding expensive in-memory state; fall back to the normal solver path. |
| Completion or manifest generation | `conda-completion` | Keep post-command regeneration safe and inline, but optionally defer heavier refresh work to a broker service. |
| UI wrapper | `conda-tui` | Display broker service checks and offer explicit user actions to start or stop plugin services. |
| Guardrail or audit hooks | `conda-protect`, `conda-checkpoints` | Keep enforcement inline. Only add broker for optional event shipping, report generation, or expensive background indexing. |
| Pure subcommands | `conda-tree`, `conda-lock` | Do nothing unless profiling shows repeated commands need a warm helper process. |
| Browser/runtime-specific plugins | `conda-wasm` | Treat broker as host-only. Do not assume it exists inside restricted runtimes such as Emscripten. |

## Keep Broker Optional

Do not make every user install or start broker just because your plugin can
use it. Keep the conda plugin entry point lean, and put broker-specific
service definitions in a separate module.

```toml
[project]
name = "conda-my-plugin"
dependencies = ["conda"]

[project.optional-dependencies]
broker = ["conda-broker"]

[project.entry-points.conda]
"conda-my-plugin" = "conda_my_plugin.plugin"

[project.entry-points.conda_broker]
"conda-my-plugin" = "conda_my_plugin.broker"
```

The conda plugin module should not import `conda_broker` at module import
time. Import it inside the function that actually wants to query broker:

```python
def broker_service():
    try:
        from conda_broker import Broker
    except ImportError:
        return None
    return Broker.current().service("conda-my-plugin.helper")
```

The broker provider module can use broker imports directly because it is only
loaded by broker discovery:

```python
from conda_broker.hookspec import hookimpl
from conda_broker.models import CondaService, EndpointSpec, HealthCheck, ProcessSpec


@hookimpl
def conda_broker_services():
    yield CondaService(
        name="conda-my-plugin.helper",
        summary="Local helper API for conda-my-plugin",
        source="conda-my-plugin",
        start_policy="manual",
        restart_policy="on-failure",
        endpoints=(EndpointSpec(protocol="http", path="/health", port_env="PORT"),),
        health_check=HealthCheck(type="http", endpoint="default"),
        process=ProcessSpec(
            argv=("python", "-m", "conda_my_plugin.helper"),
            env={"PYTHONUNBUFFERED": "1"},
        ),
    )
```

## Use a Ready Service Opportunistically

Plugin hooks that run during `conda install`, `conda create`, or `conda
update` should not silently start broker. They can query state and fall back:

```python
def maybe_use_helper(request):
    service = broker_service()
    if service is None:
        return run_inline(request)

    check = service.check()
    if check.ready and check.endpoint and check.endpoint.url:
        return call_helper_api(check.endpoint.url, request)

    service.emit_event(
        "conda-my-plugin.fallback",
        message=f"helper {check.reason or 'not ready'}; using inline path",
    )
    return run_inline(request)
```

That pattern keeps the integration invisible when it works and boring when it
does not. Users who never enabled the service still get the original plugin
behavior.

## Add Plugin CLI Status

Plugin CLIs should expose a status or doctor command when the broker service
materially affects behavior. Use `Service.check()` so the command can render
human output or JSON without starting anything:

```python
import json


def status_command(args):
    service = broker_service()
    if service is None:
        payload = {
            "broker_service": {
                "name": "conda-my-plugin.helper",
                "available": False,
                "running": False,
                "ready": False,
                "enabled": False,
                "state": "unknown",
                "health": "unknown",
                "endpoint": None,
                "reason": "conda-broker-not-installed",
            }
        }
    else:
        payload = {"broker_service": service.check().to_dict()}

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        check = payload["broker_service"]
        if check["ready"]:
            endpoint = check["endpoint"] or {}
            suffix = f" at {endpoint['url']}" if endpoint.get("url") else ""
            print(f"helper ready{suffix}")
        elif check["available"]:
            print(f"helper {check['state']}; inline fallback active")
        else:
            print(f"helper unavailable: {check['reason']}")
```

Use explicit startup from user-visible commands only:

```python
def start_helper_command(args):
    service = broker_service()
    if service is None:
        raise SystemExit("Install conda-my-plugin[broker] to enable the helper service.")
    service.start(timeout_s=args.timeout)
    if args.wait:
        service.wait(timeout_s=args.timeout)
```

For plugins with rich output, show the service check beside the plugin's own
checks. Keep the JSON field stable, for example `broker_service`, so users
can script against it.

## Use `configure_parser` for Plugin-Owned Commands

Conda subcommand plugins can pass `configure_parser` to `CondaSubcommand`.
That hook receives the plugin's `argparse.ArgumentParser`, so a plugin can
own commands such as `conda my-plugin status` without adding another global
CLI.

Use this when the plugin already has a `conda_subcommands()` hook, or when a
mostly hook-based plugin needs a small user-facing control surface for its
optional broker service.

For the common case, use `BrokerServiceCommands`. It installs broker
subcommands scoped to the service names supplied by the plugin:

```python
from conda import plugins
from conda_broker.plugin_commands import BrokerServiceCommands


broker_commands = BrokerServiceCommands(
    services=("conda-my-plugin.helper",),
    source="conda-my-plugin",
)


@plugins.hookimpl
def conda_subcommands():
    yield plugins.CondaSubcommand(
        name="my-plugin",
        summary="Run conda-my-plugin commands.",
        action=broker_commands.execute,
        configure_parser=broker_commands.configure_parser,
    )
```

That gives users plugin-owned broker controls:

```bash
conda my-plugin status
conda my-plugin start
conda my-plugin stop
conda my-plugin restart
conda my-plugin enable
conda my-plugin disable
conda my-plugin wait --start
conda my-plugin logs
```

All generated service arguments are restricted to the plugin's service list.
For a single-service plugin, `start`, `stop`, `restart`, `enable`, `disable`,
`status`, `wait`, and `logs` can omit the service name. For a multi-service
plugin, commands that can sensibly target many services default to all plugin
services, while `wait` and `logs` ask for one.

If the plugin already has its own nested commands, add broker controls to the
same subparser collection:

```python
from conda import plugins
from conda_broker.plugin_commands import BrokerServiceCommands


broker_commands = BrokerServiceCommands(
    services=("conda-my-plugin.helper", "conda-my-plugin.worker"),
    source="conda-my-plugin",
)


def configure_parser(parser):
    subcommands = parser.add_subparsers(dest="command")

    run = subcommands.add_parser("run")
    run.set_defaults(handler=run_command)

    broker_commands.add_to_subparsers(subcommands)


def execute(args):
    if not hasattr(args, "handler"):
        raise SystemExit("Choose a subcommand.")
    return args.handler(args)


@plugins.hookimpl
def conda_subcommands():
    yield plugins.CondaSubcommand(
        name="my-plugin",
        summary="Run conda-my-plugin commands.",
        action=execute,
        configure_parser=configure_parser,
    )
```

That makes plugin-specific commands such as these available:

- `conda my-plugin run`: plugin-owned behavior.
- `conda my-plugin status`: broker status for only this plugin's services.
- `conda my-plugin start`: start all services declared by this plugin.
- `conda my-plugin stop conda-my-plugin.worker`: stop one declared service.
- `conda my-plugin doctor`: include broker readiness beside the plugin's own
  diagnostics if the plugin provides a custom doctor command.
- `conda my-plugin logs`: either point users to `cb logs SERVICE` or wrap it
  with the helper if the plugin has a strong reason to keep users inside one
  CLI.

Avoid starting broker from `conda_pre_commands()` or `conda_post_commands()`.
Those hooks run during ordinary conda operations and should keep using the
opportunistic query-and-fallback pattern.

## Document It for Users

User docs for optional broker integration should answer these questions:

- What improves when the service is ready?
- What happens when broker or the service is not installed?
- Which command shows status?
- Which explicit command starts, enables, disables, or stops the service?
- Where are logs and events stored?
- What data does the service keep locally?

Suggested wording:

```md
The helper service is optional. When it is ready, this plugin reuses the
local service for faster repeated commands. When it is stopped, unavailable,
or unhealthy, the plugin uses the normal inline implementation.

Check service state with:

    conda my-plugin status

Manage the service with:

    cb start conda-my-plugin.helper
    cb enable conda-my-plugin.helper
    cb logs conda-my-plugin.helper
```

## Avoid Surprises

Follow these rules for seamless integration:

- Query methods are safe in conda hooks: `service.check()`,
  `service.status()`, `service.running()`, `service.ready()`, and
  `service.endpoint(ready=True)`.
- Startup methods belong in explicit commands: `service.start()`,
  `service.wait(start=True)`, `service.started()`, and `Broker.start()`.
- Always keep the original inline path unless the plugin is explicitly a
  service-only plugin.
- Emit broker events for observability, but do not fail conda commands if the
  event cannot be delivered.
- Prefer localhost HTTP or TCP endpoints with health checks over implicit
  files or inherited process state.
