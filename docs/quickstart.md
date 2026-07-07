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
cb enable package-cache
```

Enabled services start when the broker starts. Providers may recommend
autostart with `start_policy="enabled"`, but the local enabled state is
owned by the user.

## Start the Broker

```bash
cb start
```

`start` launches the broker process and starts services that are enabled for
broker startup. To start selected services explicitly:

```bash
cb start package-cache
```

## Check Status

```bash
cb status
cb status package-cache
cb status --json
```

Human output uses compact Rich tables. JSON output is stable and intended
for tools.

## Read Logs and Events

```bash
cb logs package-cache --lines 100
cb events
```

Follow modes stream output:

```bash
cb logs package-cache --follow
cb events --follow --json
```

## Stop

```bash
cb stop package-cache
cb stop
```

Stopping without service names asks the broker to shut down.
