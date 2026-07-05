---
orphan: true
---

# How-to Guides

Task-focused guides for operating and integrating `conda-broker`.

::::{grid} 1 1 2 2
:gutter: 3

:::{grid-item-card} {octicon}`tools` Manage services
:link: manage-services
:link-type: doc

List, enable, start, restart, and stop broker-managed services.
:::

:::{grid-item-card} {octicon}`code` Query status from plugins
:link: plugin-status-checks
:link-type: doc

Use the `Broker` API to make runtime decisions without starting the broker.
:::

:::{grid-item-card} {octicon}`log` Inspect logs and events
:link: logs-and-events
:link-type: doc

Read service logs, follow JSON Lines output, and inspect event records.
:::

:::{grid-item-card} {octicon}`file-directory` Configure paths
:link: paths
:link-type: doc

Override runtime and log locations through CLI flags, environment, or conda settings.
:::

:::{grid-item-card} {octicon}`heart` Configure health checks
:link: health-checks
:link-type: doc

Choose process, TCP, HTTP, or exec checks for service health.
:::

:::{grid-item-card} {octicon}`plug` Expose service endpoints
:link: service-endpoints
:link-type: doc

Declare local TCP or HTTP endpoints, wait for readiness, and query URLs.
:::

:::{grid-item-card} {octicon}`checklist` Validate provider services
:link: validate-provider-services
:link-type: doc

Run isolated conformance checks before shipping a provider plugin.
:::

::::
