# conda-broker

`conda-broker` is a conda plugin and short `cb` command for supervising
long-running conda-adjacent services. It provides a user-visible broker
process, a private pluggy provider API, local process supervision, logs,
events, health checks, and a small `Broker` API for other plugins.

Use it for tools that should not restart from scratch on every conda
command: package metadata caches, package recommendation workers,
telemetry clients, local LLM helpers, and other opt-in services that users
need to inspect and control.

![quickstart demo](../demos/quickstart.gif)

## Install

```bash
conda install -c conda-forge conda-broker
```

During development, run it from the repository:

```bash
pixi install
pixi run cb status
```

## Quick Use

```bash
cb list
cb enable package-cache
cb start package-cache
cb status
cb logs package-cache --follow
cb events
```

Providers expose services with the `conda_broker_services()` hook in the
`conda_broker` entry point group. Users decide which services are enabled;
discovery alone does not start a process.

---

::::{grid} 2
:gutter: 3

:::{grid-item-card} {octicon}`rocket` Quickstart
:link: quickstart
:link-type: doc

Start the broker, inspect state, and stop it again.
:::

:::{grid-item-card} {octicon}`mortar-board` Tutorials
:link: tutorials/index
:link-type: doc

Build a first service provider and a package cache service.
:::

:::{grid-item-card} {octicon}`tools` How-to Guides
:link: how-to/index
:link-type: doc

Manage services, query status from plugins, inspect logs, and configure paths.
:::

:::{grid-item-card} {octicon}`terminal` CLI Reference
:link: reference/cli
:link-type: doc

Generated command-line reference for `cb` and `conda broker`.
:::

:::{grid-item-card} {octicon}`code` Provider API
:link: reference/provider-api
:link-type: doc

Service models, hookspecs, runtime fields, and health checks.
:::

:::{grid-item-card} {octicon}`gear` Architecture
:link: explanation/architecture
:link-type: doc

How the broker, registry, supervisor, IPC, logs, and provider plugins fit together.
:::

::::

```{toctree}
:hidden:
:caption: Getting started

quickstart
```

```{toctree}
:hidden:
:caption: Tutorials

Register your first service <tutorials/first-service>
Build a provider plugin <tutorials/provider-plugin>
Create a package cache service <tutorials/package-cache-service>
```

```{toctree}
:hidden:
:caption: How-to guides

Manage services <how-to/manage-services>
Query status from plugins <how-to/plugin-status-checks>
Inspect logs and events <how-to/logs-and-events>
Configure paths <how-to/paths>
Configure health checks <how-to/health-checks>
Expose service endpoints <how-to/service-endpoints>
Validate provider services <how-to/validate-provider-services>
```

```{toctree}
:hidden:
:caption: Reference

CLI <reference/cli>
Provider API <reference/provider-api>
Broker API <reference/broker-api>
JSON output <reference/json-output>
Events <reference/events>
Filesystem layout <reference/filesystem>
Settings <reference/settings>
Development harness <reference/dev-harness>
```

```{toctree}
:hidden:
:caption: Explanation

Architecture <explanation/architecture>
Process management <explanation/process-management>
Plugin discovery <explanation/plugin-discovery>
Security <explanation/security>
Prior art <explanation/prior-art>
```
