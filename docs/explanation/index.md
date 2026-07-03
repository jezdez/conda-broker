---
orphan: true
---

# Explanation

Background and design notes for `conda-broker`.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} {octicon}`gear` Architecture
:link: architecture
:link-type: doc

How the broker, registry, supervisor, IPC, logs, and providers fit together.
:::

:::{grid-item-card} {octicon}`cpu` Process management
:link: process-management
:link-type: doc

How local child processes are started, stopped, monitored, and restarted.
:::

:::{grid-item-card} {octicon}`package` Plugin discovery
:link: plugin-discovery
:link-type: doc

How provider packages register services through the broker-owned pluggy API.
:::

:::{grid-item-card} {octicon}`shield-lock` Security
:link: security
:link-type: doc

Local IPC, auth tokens, provider trust, and process permissions.
:::

:::{grid-item-card} {octicon}`history` Prior art
:link: prior-art
:link-type: doc

Why the broker does not wrap Honcho, Circus, Supervisor, or Mirakuru.
:::

::::
