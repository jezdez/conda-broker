# Quickstart

This quickstart uses the short `cb` command. The same subcommands are
available as `conda broker`.

![quickstart demo](../demos/quickstart.gif)

## Inspect Discovered Services

```bash
cb list
```

The broker discovers provider plugins through the `conda_broker` entry
point group. Listing services does not start the broker process.

## Enable a Service

```bash
cb enable presto
```

Enabled services start when the broker starts. Providers may recommend
autostart with `start_policy="enabled"`, but the local enabled state is
owned by the user.

## Start the Broker

```bash
cb start
```

`start` launches the broker process and starts enabled services. To start
only selected services:

```bash
cb start presto
```

## Check Status

```bash
cb status
cb status presto
cb status --json
```

Human output uses compact Rich tables. JSON output is stable and intended
for tools.

## Read Logs and Events

```bash
cb logs presto --lines 100
cb events
```

Follow modes stream output:

```bash
cb logs presto --follow
cb events --follow --json
```

## Stop

```bash
cb stop presto
cb stop
```

Stopping without service names asks the broker to shut down.
