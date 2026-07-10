# Integrate Conda Plugins

Use broker when a conda plugin benefits from preserving expensive runtime
state between commands. Keep ordinary validation, parsing, and one-shot
commands inline.

The [conda plugin docs](https://docs.conda.io/projects/conda/en/stable/dev-guide/plugins/index.html)
describe the host plugin system: packages register a module under
`[project.entry-points.conda]`, then expose hooks such as
`conda_subcommands()` and `conda_settings()`. The
[conda-plugins catalogue](https://github.com/conda-incubator/conda-plugins)
shows the common shapes: subcommands, solver hooks, auth helpers, telemetry,
channel tooling, environment specs, and environment/project helpers.

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
| Local channel or repodata helpers | `conda-pypi-channel`, `conda-repodata` | Replace ad hoc `Popen` or hidden cache lifecycles with a visible broker service, HTTP health check, logs, events, and a stable endpoint. |
| Metadata and conversion cache | `conda-pypi`, `conda_index` | Keep one-shot commands, but optionally reuse a warm local cache or index service when it is already ready. |
| Solver or repoquery backend | `conda-libmamba-solver`, `conda-random-solver` | Query a ready cache/helper service before rebuilding expensive in-memory state; fall back to the normal solver path. |
| Completion, history, or environment metadata | `conda-completion`, `conda-history-d`, `conda-env-spec-v2`, `conda-lockfiles` | Keep lightweight hook work inline, but optionally defer heavier refresh or indexing work to a broker service. |
| Environment or project helpers | `conda-spawn`, `conda-global`, `conda-ops`, `conda-declarative` | Keep command execution explicit, but expose optional status and service controls if a plugin adds a persistent helper. |
| UI or assistant wrapper | `conda-tui`, `anaconda-assistant-mcp` | Display broker service checks and offer explicit user actions to start or stop plugin services. |
| Auth, telemetry, or request hooks | `anaconda-auth`, `conda-anaconda-telemetry`, `conda-dev-request-headers` | Keep credential and request decisions inline. Only add broker for optional event batching, report generation, or expensive background refresh work users can inspect. |
| Pure example or tree subcommands | `conda-tree`, `random-walk`, `conda-random-subcommand` | Do nothing unless profiling shows repeated commands need a warm helper process. |
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
import sys

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
            argv=(sys.executable, "-m", "conda_my_plugin.helper"),
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

    from conda_broker.exceptions import CondaBrokerError

    try:
        service.emit_event(
            "conda-my-plugin.fallback",
            message=f"helper {check.reason or 'not ready'}; using inline path",
        )
    except (OSError, CondaBrokerError):
        pass
    return run_inline(request)
```

Observability must not turn an optional fast path into a failed conda command
when the runtime directory is unavailable.

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

Use `BrokerServiceCommands` to install broker subcommands scoped to the
service names supplied by the plugin. Pick the mounting shape that matches
the plugin.

### Hook-Only Plugins

If the plugin does not already publish a `conda_subcommands()` hook, use
`conda_subcommand()` to create a small service-management command:

```python
from conda import plugins
from conda_broker.plugin_commands import BrokerServiceCommands


broker_commands = BrokerServiceCommands(
    services=("conda-my-plugin.helper",),
    source="conda-my-plugin",
)


@plugins.hookimpl
def conda_subcommands():
    yield broker_commands.conda_subcommand(
        "my-plugin",
        summary="Manage conda-my-plugin services.",
    )
```

That creates one stable command shape:

```bash
conda my-plugin services status
conda my-plugin services start
conda my-plugin services stop
conda my-plugin services restart
conda my-plugin services enable
conda my-plugin services disable
conda my-plugin services wait --start
conda my-plugin services logs
```

### Plugins With Existing Subcommands

If the plugin already has its own nested commands, mount the same `services`
group beside those commands:

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

    broker_commands.add_group_to_subparsers(subcommands)


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
- `conda my-plugin services status`: broker status for this plugin's services.
- `conda my-plugin services start`: start all services declared by this plugin.
- `conda my-plugin services stop conda-my-plugin.worker`: stop one declared
  service.
- `conda my-plugin services logs conda-my-plugin.helper`: show one service log.

### Plugins With a Custom `services` Parser

If the plugin already creates its own `services` parser and only wants broker
controls inside that parser, configure that parser directly:

```python
def configure_parser(parser):
    subcommands = parser.add_subparsers(dest="command")
    services = subcommands.add_parser("services")
    services.set_defaults(handler=broker_commands.execute)
    broker_commands.configure_commands_parser(services)
```

The lower-level `add_commands_to_subparsers()` method exists for advanced
argparse layouts, but prefer the `services` group unless there is a strong
reason not to.

All generated service arguments are restricted to the plugin's service list.
For a single-service plugin, `start`, `stop`, `restart`, `enable`, `disable`,
`status`, `wait`, and `logs` can omit the service name. For a multi-service
plugin, commands that can sensibly target many services default to all plugin
services, while `wait` and `logs` ask for one.

Keep the group name stable unless the plugin has a strong domain-specific
reason to use another word. `services` is the default because users can learn
one shape across plugins.

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

    conda my-plugin services status

Manage the service with:

    conda my-plugin services start
    conda my-plugin services enable
    conda my-plugin services logs
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
  event cannot be delivered; catch `CondaBrokerError` and `OSError` around
  optional event writes.
- Prefer localhost HTTP or TCP endpoints with health checks over implicit
  files or inherited process state.
